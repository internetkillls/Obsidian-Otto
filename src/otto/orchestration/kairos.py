from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from pathlib import Path
from typing import Any

from ..config import load_kairos_config, load_paths
from ..events import (
    Event,
    EventBus,
    EVENT_COUNCIL_DEBATE,
    EVENT_KAIROS,
    EVENT_KAIROS_CONTRADICTION,
    EVENT_KAIROS_GOLD_SCORED,
    EVENT_META_GOV_ALERT,
    EVENT_OPENCLAW_RESEARCH,
)
from ..logging_utils import append_jsonl, get_logger
from ..models import choose_model
from ..state import OttoState, now_iso, read_json, write_json
from .brain import run_brain_predictions
from .council import CouncilEngine
from .graph_demotion import (
    graph_action_candidates,
    graph_controller_goal,
    graph_ready_for_fetch,
    graph_research_topic,
    load_graph_demotion_review,
)
from .kairos_gold import KairosGoldEngine
from .meta_gov import MetaGovObserver
from .mentor import MentoringEngine
from .openclaw_research import OpenClawResearchEngine, build_research_plan


_STARTUP_MEMORY_START = "<!-- otto:startup-memory:start -->"
_STARTUP_MEMORY_END = "<!-- otto:startup-memory:end -->"


def _latest_mtime(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_mtime
    mtimes = [p.stat().st_mtime for p in path.rglob("*") if p.is_file()]
    return max(mtimes, default=0.0)


def _choose_research_topic(top_folders: list[dict[str, Any]], council_triggered: bool, council_weakness: str | None) -> tuple[str, str]:
    if council_triggered and council_weakness:
        return council_weakness, "high"
    if top_folders:
        top = top_folders[0]
        folder = str(top.get("folder", "vault")).replace("\\", "/")
        score = top.get("risk_score", "n/a")
        return f"Metadata repair strategy for {folder} (risk={score})", "medium"
    return "Operational calibration for vault hygiene and retrieval stability", "medium"


def _dedupe(items: list[str], *, limit: int = 10) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item.strip())
        if len(output) >= limit:
            break
    return output


def _normalize_rel_path(value: str) -> str:
    return str(value or "").replace("\\", "/").strip("/")


def _vault_relative_path(paths: Any, value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = Path(raw)
    vault_path = getattr(paths, "vault_path", None)
    if candidate.is_absolute() and vault_path is not None:
        try:
            return str(candidate.relative_to(vault_path)).replace("\\", "/").strip("/")
        except ValueError:
            pass
    return _normalize_rel_path(raw)


def _manual_review_scope(path_value: str) -> tuple[str, str, bool]:
    normalized = _normalize_rel_path(path_value)
    if not normalized or normalized == ".":
        return "root", "vault", False
    if normalized.startswith(".Otto-Realm/") or normalized == ".Otto-Realm":
        remainder = normalized[len(".Otto-Realm/"):] if normalized.startswith(".Otto-Realm/") else ""
        context = remainder.split("/", 1)[0] if remainder else "Training"
        return ".Otto-Realm", context or "Training", True
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return "root", "vault", False
    moc = parts[0]
    context = parts[1] if len(parts) > 1 else parts[0]
    return moc, context or parts[0], False


def _manual_review_scope_title(moc: str, context: str, is_exception: bool) -> str:
    if is_exception:
        return f"{moc} (exception) / Context: {context}"
    return f"MOC: {moc} / Context: {context}"


def _manual_review_item_label(kind: str, *, why_now: str, focus_path: str) -> tuple[str, str]:
    if kind == "folder-repair":
        return "must-fix", why_now
    if kind == "training-probe":
        return "should-review", f"probe={focus_path or 'n/a'}"
    if kind == "gold-candidate-review":
        return "should-review", why_now
    return "optional", why_now


def _label_rank(label: str) -> int:
    return {"must-fix": 3, "should-review": 2, "optional": 1}.get(label, 0)


def _manual_review_group_id(moc: str, context: str, is_exception: bool) -> str:
    safe_moc = moc.replace("/", "_").replace("\\", "_").strip()
    safe_context = context.replace("/", "_").replace("\\", "_").strip()
    suffix = "exception" if is_exception else "standard"
    return f"{safe_moc}::{safe_context}::{suffix}"


def _manual_review_queue_groups(queue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in queue:
        focus_path = str(item.get("focus_path") or item.get("source") or "")
        moc, context, is_exception = _manual_review_scope(focus_path)
        group_id = _manual_review_group_id(moc, context, is_exception)
        group = grouped.get(group_id)
        if group is None:
            group = {
                "group_id": group_id,
                "moc": moc,
                "context": context,
                "is_exception": is_exception,
                "title": _manual_review_scope_title(moc, context, is_exception),
                "group_label": "optional",
                "priority": 0,
                "label_counts": {"must-fix": 0, "should-review": 0, "optional": 0},
                "items": [],
            }
            grouped[group_id] = group

        label = str(item.get("label") or "optional")
        group["items"].append(item)
        group["label_counts"][label] = int(group["label_counts"].get(label, 0)) + 1
        if _label_rank(label) > _label_rank(str(group.get("group_label") or "optional")):
            group["group_label"] = label
        group["priority"] = max(int(group.get("priority", 0)), int(item.get("priority", 0)))

    groups = list(grouped.values())
    for group in groups:
        group["items"] = sorted(
            group["items"],
            key=lambda item: (-int(item.get("priority", 0)), str(item.get("id", ""))),
        )
    groups.sort(key=lambda group: (-int(group.get("priority", 0)), str(group.get("title", ""))))
    return groups


def _folder_representatives(paths: Any, folder: str, *, limit: int = 3) -> list[str]:
    if not getattr(paths, "sqlite_path", None) or not paths.sqlite_path.exists():
        return []
    normalized = _normalize_rel_path(folder)
    conn = sqlite3.connect(paths.sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        if normalized == ".":
            rows = conn.execute(
                """
                SELECT path
                FROM notes
                WHERE REPLACE(path, '\\', '/') NOT LIKE '%/%'
                ORDER BY mtime DESC, path ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            like_pattern = f"{normalized}/%"
            rows = conn.execute(
                """
                SELECT path
                FROM notes
                WHERE REPLACE(path, '\\', '/') = ?
                   OR REPLACE(path, '\\', '/') LIKE ?
                ORDER BY mtime DESC, path ASC
                LIMIT ?
                """,
                (normalized, like_pattern, limit),
            ).fetchall()
    finally:
        conn.close()
    return [str(row["path"]) for row in rows]


def _manual_review_queue(
    *,
    paths: Any,
    gold_summary: dict[str, Any],
    gold_result: Any,
    mentor_result: Any,
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []

    top_folders = list((gold_summary.get("top_folders") or [])[:3])
    for idx, item in enumerate(top_folders, start=1):
        folder = str(item.get("folder", "")).strip()
        if not folder:
            continue
        representatives = _folder_representatives(paths, folder, limit=3)
        label, label_reason = _manual_review_item_label(
            "folder-repair",
            why_now="folder hygiene risk",
            focus_path=folder,
        )
        queue.append(
            {
                "id": f"folder-{idx}-{_normalize_rel_path(folder).replace('/', '__')}",
                "kind": "folder-repair",
                "priority": 1000 - (idx * 10),
                "title": f"Review folder hygiene: {folder}",
                "source": "artifacts/summaries/gold_summary.json",
                "focus_path": folder,
                "label": label,
                "label_reason": label_reason,
                "why_now": (
                    f"risk={item.get('risk_score', 'n/a')} "
                    f"missing_frontmatter={item.get('missing_frontmatter', 'n/a')} "
                    f"duplicate_titles={item.get('duplicate_titles', 'n/a')} "
                    f"note_count={item.get('note_count', 'n/a')}"
                ),
                "evidence": {
                    "representative_files": representatives,
                    "outbound_links": item.get("outbound_links"),
                },
                "next_manual_step": "Inspect the representative files, then decide whether to normalize metadata or split the folder into smaller clusters.",
            }
        )

    promoted = list(getattr(gold_result, "scored_signals", []) or [])
    promoted = [item for item in promoted if getattr(item, "promoted", False)]
    promoted.sort(key=lambda item: (item.total_score, item.consistency_hits), reverse=True)
    for idx, item in enumerate(promoted[:3], start=1):
        label, label_reason = _manual_review_item_label(
            "gold-candidate-review",
            why_now=(
                f"category={getattr(item, 'category', 'n/a')} "
                f"score={item.total_score:.3f} threshold={item.threshold:.3f} "
                f"consistency_hits={item.consistency_hits}"
            ),
            focus_path=item.note_path,
        )
        queue.append(
            {
                "id": f"gold-{idx}-{_normalize_rel_path(item.note_path).replace('/', '__')}",
                "kind": "gold-candidate-review",
                "priority": 700 - (idx * 10),
                "title": f"Review Gold candidate: {item.title}",
                "source": "state/kairos/gold_scored_latest.json",
                "focus_path": item.note_path,
                "label": label,
                "label_reason": label_reason,
                "why_now": (
                    f"category={getattr(item, 'category', 'n/a')} "
                    f"score={item.total_score:.3f} threshold={item.threshold:.3f} "
                    f"consistency_hits={item.consistency_hits}"
                ),
                "evidence": {
                    "note_path": item.note_path,
                    "category": getattr(item, "category", "n/a"),
                    "category_reason": getattr(item, "category_reason", "n/a"),
                    "notes": list(getattr(item, "notes", []) or []),
                },
                "next_manual_step": "Open the note and decide whether it should remain Gold, be revised, or be downgraded to Silver.",
            }
        )

    active_probes = list(getattr(mentor_result, "active_probes", []) or [])
    active_probes.sort(key=lambda item: (str(getattr(item, "status", "")).lower() != "pending", str(getattr(item, "title", "")).lower()))
    for idx, item in enumerate(active_probes[:2], start=1):
        focus_path = _vault_relative_path(paths, str(getattr(item, "path", "")))
        label, label_reason = _manual_review_item_label(
            "training-probe",
            why_now=f"weakness={getattr(item, 'weakness', 'n/a')} gap={getattr(item, 'gap_type', 'unknown')}",
            focus_path=focus_path,
        )
        queue.append(
            {
                "id": f"probe-{idx}-{_normalize_rel_path(str(getattr(item, 'title', 'probe'))).replace('/', '__')}",
                "kind": "training-probe",
                "priority": 500 - (idx * 10),
                "title": f"Answer training probe: {getattr(item, 'title', 'probe')}",
                "source": str(getattr(item, "path", mentor_result.report_path or "mentor_daily.md")),
                "focus_path": focus_path,
                "label": label,
                "label_reason": label_reason,
                "why_now": f"weakness={getattr(item, 'weakness', 'n/a')} gap={getattr(item, 'gap_type', 'unknown')}",
                "evidence": {
                    "probe_id": getattr(item, "probe_id", "n/a"),
                    "status": getattr(item, "status", "n/a"),
                    "gap_type": getattr(item, "gap_type", "unknown"),
                    "weakness_key": getattr(item, "weakness_key", "n/a"),
                },
                "next_manual_step": "Write the shortest truthful answer and, if needed, attach one concrete next move.",
            }
        )

    queue.sort(key=lambda item: (-int(item.get("priority", 0)), str(item.get("id", ""))))
    return queue


def _manual_review_queue_markdown(queue: list[dict[str, Any]], *, ts: str) -> str:
    groups = _manual_review_queue_groups(queue)
    lines = [
        "# Manual Review Queue",
        "",
        f"- timestamp: {ts}",
        f"- queue_count: {len(queue)}",
        f"- group_count: {len(groups)}",
        "",
    ]
    if not groups:
        lines.append("- none")
        return "\n".join(lines) + "\n"

    for group in groups:
        lines.extend(
            [
                f"## {group['title']}",
                f"- group_id: `{group['group_id']}`",
                f"- group_label: `{group['group_label']}`",
                f"- label_counts: must-fix={group['label_counts'].get('must-fix', 0)} should-review={group['label_counts'].get('should-review', 0)} optional={group['label_counts'].get('optional', 0)}",
                f"- item_count: {len(group['items'])}",
                "",
            ]
        )
        for idx, item in enumerate(group["items"], start=1):
            lines.extend(
                [
                    f"### {idx}. {item['title']}",
                    f"- id: `{item['id']}`",
                    f"- label: `{item.get('label', 'optional')}`",
                    f"- kind: `{item['kind']}`",
                    f"- priority: `{item['priority']}`",
                    f"- source: `{item['source']}`",
                    f"- focus_path: `{item.get('focus_path', '')}`",
                    f"- why_now: {item['why_now']}",
                ]
            )
            evidence = item.get("evidence") or {}
            if evidence:
                lines.append("- evidence:")
                for key, value in evidence.items():
                    if isinstance(value, list):
                        if value:
                            lines.append(f"  - {key}:")
                            for entry in value:
                                lines.append(f"    - {entry}")
                        else:
                            lines.append(f"  - {key}: []")
                    else:
                        lines.append(f"  - {key}: {value}")
            lines.append(f"- next_manual_step: {item['next_manual_step']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _extract_startup_memory_tail(memory_path: Path) -> str:
    if not memory_path.exists():
        return ""
    raw = memory_path.read_text(encoding="utf-8")
    start = raw.find(_STARTUP_MEMORY_START)
    end = raw.find(_STARTUP_MEMORY_END)
    if start != -1 and end != -1 and end > start:
        return raw[end + len(_STARTUP_MEMORY_END):].lstrip()
    return raw.strip()


def _merge_startup_memory_archive(archive_path: Path, incoming: str) -> None:
    normalized = incoming.strip()
    if not normalized:
        return
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.exists():
        archive_path.write_text(normalized + "\n", encoding="utf-8")
        return
    existing = archive_path.read_text(encoding="utf-8").strip()
    if not existing:
        archive_path.write_text(normalized + "\n", encoding="utf-8")
        return
    if normalized == existing or normalized in existing:
        return
    if existing in normalized:
        archive_path.write_text(normalized + "\n", encoding="utf-8")
        return
    archive_path.write_text(existing + "\n\n" + normalized + "\n", encoding="utf-8")


def _compact_archive_recall(line: str, *, max_chars: int = 220) -> str | None:
    stripped = line.strip()
    if stripped.startswith("- "):
        stripped = stripped[2:].strip()
    if stripped.startswith("# "):
        stripped = stripped[2:].strip()
    stripped = " ".join(stripped.split())
    if not stripped:
        return None
    lowered = stripped.lower()
    noisy_markers = (
        "session-corpus",
        "no strong patterns surfaced",
        "openclaw:dreaming",
        "candidate:",
        "status: staged",
        "recalls:",
        "confidence: 0.00",
    )
    if any(marker in lowered for marker in noisy_markers):
        return None
    if len(stripped) > max_chars:
        stripped = stripped[: max_chars - 3].rstrip() + "..."
    return stripped


def _recent_archive_recalls(archive_text: str, *, limit: int = 3) -> list[str]:
    sections: list[list[str]] = []
    current: list[str] = []
    for line in archive_text.splitlines():
        if line.startswith("## Promoted From Short-Term Memory"):
            if current:
                sections.append(current)
            current = []
            continue
        if line.startswith("- "):
            current.append(line)
    if current:
        sections.append(current)

    candidates: list[str] = []
    seen: set[str] = set()
    for section in reversed(sections):
        for line in section:
            compacted = _compact_archive_recall(line)
            if not compacted:
                continue
            key = compacted.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(compacted)
            if len(candidates) >= limit:
                return candidates
    return candidates


def _horizon_rank(value: str) -> int:
    normalized = value.strip().lower()
    mapping = {
        "today": 0,
        "24h": 0,
        "1d": 0,
        "2d": 1,
        "3d": 1,
        "7d": 2,
        "14d": 3,
        "30d": 4,
        "90d": 5,
        "unknown": 6,
        "1y+": 7,
    }
    return mapping.get(normalized, 6)


def _kind_rank(value: str) -> int:
    normalized = value.strip().lower()
    mapping = {
        "client": 0,
        "freelance": 0,
        "work": 1,
        "project": 2,
        "note": 3,
        "research": 4,
        "personal": 5,
        "unknown": 6,
    }
    return mapping.get(normalized, 6)


def _is_low_signal_cue(value: str) -> bool:
    normalized = " ".join(value.strip().lower().split())
    return normalized in {
        "",
        "general",
        "personal note",
        "basis knowledge",
        "about lemma proof #backlog/primary-skill #daily-drill/math",
    }


def _format_human_priority(item: dict[str, Any]) -> str | None:
    cue = str(item.get("cue") or "").strip()
    if not cue or _is_low_signal_cue(cue):
        return None
    kind = str(item.get("kind") or "unknown").strip()
    horizon = str(item.get("horizon") or "unknown").strip()
    parts = [cue, f"kind={kind}", f"horizon={horizon}"]
    if item.get("historical") is False:
        parts.append("currentish=yes")
    return " | ".join(parts)


def _human_priority_items(handoff: dict[str, Any], *, limit: int = 4) -> list[str]:
    candidates = []
    for item in handoff.get("profile_opportunities_to_surface") or []:
        if isinstance(item, dict):
            candidates.append(item)
    for item in handoff.get("profile_commitments_to_recall") or []:
        if isinstance(item, dict):
            candidates.append(item)

    ranked = sorted(
        candidates,
        key=lambda item: (
            _horizon_rank(str(item.get("horizon") or "unknown")),
            _kind_rank(str(item.get("kind") or "unknown")),
            0 if item.get("historical") is False else 1,
            str(item.get("cue") or "").lower(),
        ),
    )

    results: list[str] = []
    seen: set[str] = set()
    for item in ranked:
        formatted = _format_human_priority(item)
        if not formatted:
            continue
        key = str(item.get("cue") or formatted).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(formatted)
        if len(results) >= limit:
            break
    return results


def _research_run_payload(run: Any) -> dict[str, Any]:
    return {
        "ts": run.ts,
        "topic": run.topic.topic,
        "topic_class": run.topic.topic_class,
        "priority": run.topic.priority,
        "approved": run.approved,
        "budget_reason": run.budget_reason,
        "planned_cycles": run.fetch_cycles,
        "source_tiers": run.topic.source_tiers,
        "needs_freshness_check": run.topic.needs_freshness_check,
        "effect_size_required": run.topic.effect_size_required,
        "search_query": run.search_query,
        "hypothesis": run.hypothesis,
        "search_provider": run.search_provider,
        "fetch_provider": run.fetch_provider,
        "search_ok": run.search_ok,
        "fetch_ok": run.fetch_ok,
        "search_hits_count": len(run.search_hits),
        "fetched_documents_count": len(run.fetched_documents),
        "warnings": run.warnings[:10],
        "cache_path": run.cache_path,
        "plan_only": False,
        "fetch_executed": True,
    }


def run_kairos_once() -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    logger = get_logger("otto.kairos")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()
    _cfg = load_kairos_config().get("kairos", {})
    model = choose_model("kairos_daily")
    bus = EventBus()

    gold = read_json(paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
    checkpoint = read_json(state.checkpoints, default={}) or {}
    events_path = paths.state_root / "run_journal" / "events.jsonl"
    graph_review = load_graph_demotion_review(paths)

    top_folders = (gold.get("top_folders") or [])[:3]
    if graph_review:
        base_actions = [str(graph_review.get("recommended_next_action") or "").strip()]
    else:
        base_actions = [f"Repair metadata in {item['folder']}" for item in top_folders]
    base_actions = [item for item in base_actions if item]
    if not base_actions:
        base_actions = ["Run pipeline then hydrate Gold summary"]

    gold_result = KairosGoldEngine().score_signals()
    bus.publish(
        Event(
            type=EVENT_KAIROS_GOLD_SCORED,
            source="kairos",
            payload={
                "ts": gold_result.ts,
                "kairos_score": gold_result.kairos_score,
                "gold_promoted_count": gold_result.gold_promoted_count,
                "silver_count": gold_result.silver_count,
                "noise_count": gold_result.noise_count,
                "promoted_paths": gold_result.promoted_paths,
            },
        )
    )
    for contradiction in gold_result.contradictions[:10]:
        bus.publish(
            Event(
                type=EVENT_KAIROS_CONTRADICTION,
                source="kairos",
                payload=contradiction.as_dict(),
            )
        )

    handoff_before_mentor = read_json(state.handoff_latest, default={}) or {}
    mentor_result = MentoringEngine().run(profile=handoff_before_mentor)

    council_result = CouncilEngine().run(
        gold_result=gold_result,
        unresolved=base_actions,
        action_candidates=graph_action_candidates(graph_review),
        weakness_registry=mentor_result.weakness_registry or None,
    )
    for debate in council_result.debates:
        bus.publish(
            Event(
                type=EVENT_COUNCIL_DEBATE,
                source="kairos",
                payload=debate.as_dict(),
            )
        )

    council_weakness = council_result.debates[0].weakness if council_result.debates else None
    if graph_review:
        research_topic = graph_research_topic(graph_review)
        research_priority = "high"
    else:
        research_topic, research_priority = _choose_research_topic(
            top_folders=top_folders,
            council_triggered=council_result.triggered,
            council_weakness=council_weakness,
        )
    try:
        if graph_review and graph_ready_for_fetch(graph_review):
            research_plan = _research_run_payload(
                OpenClawResearchEngine().execute(
                    topic_text=research_topic,
                    priority=research_priority,
                )
            )
        else:
            research_plan = build_research_plan(topic_text=research_topic, priority=research_priority)
    except Exception:
        research_plan = build_research_plan(topic_text=research_topic, priority=research_priority)
    bus.publish(
        Event(
            type=EVENT_OPENCLAW_RESEARCH,
            source="kairos",
            payload=research_plan,
        )
    )

    meta_findings = MetaGovObserver().observe()
    if meta_findings:
        bus.publish(
            Event(
                type=EVENT_META_GOV_ALERT,
                source="kairos",
                payload={
                    "finding_count": len(meta_findings),
                    "findings": [item.as_dict() for item in meta_findings],
                },
            )
        )

    additional_actions = []
    if council_result.debates:
        additional_actions.append(council_result.debates[0].next_action)
    additional_actions.extend([item.action for item in meta_findings[:3]])
    if mentor_result.active_probes:
        additional_actions.append(f"Answer training probe: {mentor_result.active_probes[0].title}")
    if mentor_result.pending_tasks:
        additional_actions.append(f"Review training queue: {mentor_result.pending_tasks[0].title}")
    additional_actions.append("Prefer fast retrieval first; escalate only when evidence is weak")
    additional_actions.append("Keep training export gated behind reviewed Gold")
    next_actions = _dedupe(base_actions + additional_actions, limit=12)
    manual_review_queue = _manual_review_queue(
        paths=paths,
        gold_summary=gold,
        gold_result=gold_result,
        mentor_result=mentor_result,
    )
    manual_review_groups = _manual_review_queue_groups(manual_review_queue)
    manual_review_queue_path = paths.state_root / "handoff" / "manual_review_queue.json"
    manual_review_queue_report_path = paths.artifacts_root / "reports" / "manual_review_queue.md"
    manual_review_queue_path.parent.mkdir(parents=True, exist_ok=True)
    manual_review_queue_report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        manual_review_queue_path,
        {
            "ts": now_iso(),
            "queue_count": len(manual_review_queue),
            "group_count": len(manual_review_groups),
            "items": manual_review_queue,
            "groups": manual_review_groups,
            "source": "kairos",
            "source_handoff": str(state.handoff_latest),
            "source_gold_summary": str(paths.artifacts_root / "summaries" / "gold_summary.json"),
            "source_mentor_report": mentor_result.report_path,
        },
    )
    manual_review_queue_report_path.write_text(
        _manual_review_queue_markdown(manual_review_queue, ts=now_iso()),
        encoding="utf-8",
    )

    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    cycle_id = f"kairos-{now_iso()}"
    meta_flag = meta_findings[0].flag if meta_findings else None

    strategy_lines = [
        "# KAIROS Daily Strategy",
        "",
        f"- timestamp: {now_iso()}",
        f"- model_hint: {model.model}",
        f"- checkpoint_scope: {checkpoint.get('scope', 'n/a')}",
        f"- recent_events_present: {events_path.exists()}",
        f"- kairos_score: {gold_result.kairos_score:.2f}",
        f"- gold_promoted_count: {gold_result.gold_promoted_count}",
        f"- council_triggered: {council_result.triggered}",
        f"- meta_gov_flag: {meta_flag or 'none'}",
        "",
        "## Top folder risks",
    ]
    if top_folders:
        for item in top_folders:
            strategy_lines.append(
                f"- {item['folder']} risk={item['risk_score']} missing_frontmatter={item['missing_frontmatter']} duplicates={item['duplicate_titles']}"
            )
    else:
        strategy_lines.append("- no Gold data yet")

    strategy_lines.extend(["", "## Graph Demotion"])
    if graph_review:
        strategy_lines.append(f"- review_path: {graph_review.get('source_path', 'n/a')}")
        strategy_lines.append(f"- reviewed_note_count: {graph_review.get('reviewed_note_count', 0)}")
        strategy_lines.append(f"- quality_verdict: {graph_review.get('quality_verdict', 'n/a')}")
        strategy_lines.append(f"- graph_readability: {graph_review.get('graph_readability_verdict', 'n/a')}")
        strategy_lines.append(f"- next_apply_mode: {graph_review.get('recommended_next_apply_mode', 'n/a')}")
        strategy_lines.append(f"- hotspot_family: {graph_review.get('primary_hotspot_family', 'n/a')}")
        strategy_lines.append(f"- next_action: {graph_review.get('recommended_next_action', 'n/a')}")
    else:
        strategy_lines.append("- no fresh graph demotion review")

    strategy_lines.extend(["", "## Gold scoring"])
    strategy_lines.append(
        f"- promoted={gold_result.gold_promoted_count} silver={gold_result.silver_count} noise={gold_result.noise_count}"
    )
    if getattr(gold_result, "category_counts", None):
        strategy_lines.append(
            f"- categories={gold_result.category_counts} promoted_by_category={getattr(gold_result, 'category_promoted_counts', {})}"
        )
    strategy_lines.append(
        f"- contradictions={len(gold_result.contradictions)} dynamic_thresholds={len(gold_result.dynamic_thresholds)}"
    )
    for item in gold_result.scored_signals[:3]:
        strategy_lines.append(
            f"- {item.note_path} score={item.total_score:.2f} threshold={item.threshold:.2f} category={getattr(item, 'category', 'n/a')} promoted={item.promoted}"
        )

    strategy_lines.extend(["", "## Manual Review Queue"])
    strategy_lines.append(f"- queue_count={len(manual_review_queue)}")
    manual_review_groups = _manual_review_queue_groups(manual_review_queue)
    strategy_lines.append(f"- group_count={len(manual_review_groups)}")
    for group in manual_review_groups[:4]:
        strategy_lines.append(
            f"- {group['title']} | group_label={group['group_label']} | items={len(group['items'])} | must-fix={group['label_counts'].get('must-fix', 0)} should-review={group['label_counts'].get('should-review', 0)} optional={group['label_counts'].get('optional', 0)}"
        )

    strategy_lines.extend(["", "## Council"])
    strategy_lines.append(f"- trigger_count={council_result.trigger_count}")
    if council_result.debates:
        first_debate = council_result.debates[0]
        strategy_lines.append(
            f"- {first_debate.trigger_category} recurrence={first_debate.recurrence_count} next_action={first_debate.next_action}"
        )
        strategy_lines.append(
            f"- output_role={first_debate.output.role} write_target={first_debate.output.write_target or 'n/a'}"
        )
    else:
        strategy_lines.append("- no debate triggered")

    strategy_lines.extend(["", "## OpenClaw Research Plan"])
    strategy_lines.append(f"- topic={research_plan.get('topic', 'n/a')}")
    strategy_lines.append(
        f"- class={research_plan.get('topic_class', 'n/a')} approved={research_plan.get('approved', False)} cycles={research_plan.get('planned_cycles', 0)} fetch_executed={research_plan.get('fetch_executed', False)}"
    )

    strategy_lines.extend(["", "## MetaGov"])
    strategy_lines.append(f"- findings={len(meta_findings)}")
    for finding in meta_findings[:3]:
        strategy_lines.append(f"- [{finding.level}] {finding.flag}: {finding.action}")

    strategy_lines.extend(["", "## Next actions"])
    strategy_lines.extend([f"- {line}" for line in next_actions])
    strategy_lines.extend(["", "## Mentor"])
    strategy_lines.append(
        f"- probes={len(mentor_result.active_probes)} pending={len(mentor_result.pending_tasks)} done={len(mentor_result.completed_tasks)} skipped={len(mentor_result.skipped_tasks)}"
    )
    if mentor_result.active_probes:
        strategy_lines.append(
            f"- active_probe={mentor_result.active_probes[0].title} gap={mentor_result.active_probes[0].gap_type}"
        )
    if mentor_result.pending_tasks:
        strategy_lines.append(f"- active_task={mentor_result.pending_tasks[0].title}")
    else:
        strategy_lines.append("- active_task=none")
    if mentor_result.weakness_registry:
        first_registry = next(iter(mentor_result.weakness_registry.items()))
        strategy_lines.append(
            f"- latest_gap={first_registry[0]} -> {first_registry[1].get('latest_gap_type', 'unknown')}"
        )
    strategy_lines.append(f"- report_path: {mentor_result.report_path}")

    report_path = paths.artifacts_root / "reports" / "kairos_daily_strategy.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(strategy_lines) + "\n", encoding="utf-8")

    record = {
        "ts": now_iso(),
        "cycle_id": cycle_id,
        "model_hint": model.model,
        "top_folder_count": len(top_folders),
        "kairos_score": gold_result.kairos_score,
        "gold_promoted_count": gold_result.gold_promoted_count,
        "council_triggered": council_result.triggered,
        "openclaw_fetch": bool(research_plan.get("fetch_executed", False)),
        "meta_gov_flag": meta_flag,
        "duration_ms": duration_ms,
        "next_actions": next_actions,
        "graph_demotion_review_path": graph_review.get("source_path") if graph_review else None,
        "graph_demotion_next_apply_mode": graph_review.get("recommended_next_apply_mode") if graph_review else None,
        "graph_demotion_hotspot_family": graph_review.get("primary_hotspot_family") if graph_review else None,
        "graph_demotion_next_action": graph_review.get("recommended_next_action") if graph_review else None,
        "council_output_role": council_result.debates[0].output.role if council_result.debates else None,
    }
    append_jsonl(state.kairos, record)
    append_jsonl(
        state.run_journal / "events.jsonl",
        {
            "ts": record["ts"],
            "cycle_id": cycle_id,
            "phase": "B",
            "source": "kairos",
            "kairos_score": gold_result.kairos_score,
            "gold_promoted_count": gold_result.gold_promoted_count,
            "council_triggered": council_result.triggered,
            "openclaw_fetch": bool(research_plan.get("fetch_executed", False)),
            "meta_gov_flag": meta_flag,
            "next_action": next_actions[0] if next_actions else "none",
            "duration_ms": duration_ms,
            "graph_demotion_active": bool(graph_review),
            "graph_demotion_next_apply_mode": graph_review.get("recommended_next_apply_mode") if graph_review else None,
            "graph_demotion_hotspot_family": graph_review.get("primary_hotspot_family") if graph_review else None,
        },
    )

    run_brain_predictions()
    handoff_artifacts = [
        "artifacts/summaries/gold_summary.json",
        "artifacts/reports/kairos_daily_strategy.md",
        str(manual_review_queue_report_path),
        "artifacts/reports/dream_summary.md",
        "artifacts/reports/mentor_daily.md",
    ]
    if graph_review:
        handoff_artifacts.append(str(graph_review.get("source_path")))
    write_json(
        state.handoff_latest,
        {
            **(read_json(state.handoff_latest, default={}) or {}),
            **{
                "updated_at": now_iso(),
                "status": "ready",
                "goal": graph_controller_goal(graph_review),
                "artifacts": handoff_artifacts,
                "next_actions": next_actions,
                "manual_review_queue_path": str(manual_review_queue_path),
                "manual_review_queue_report_path": str(manual_review_queue_report_path),
                "manual_review_queue_count": len(manual_review_queue),
                "manual_review_queue_group_count": len(manual_review_groups),
                "manual_review_queue": manual_review_queue,
                "manual_review_queue_groups": manual_review_groups,
                "kairos_score": round(gold_result.kairos_score, 3),
                "gold_promoted_count": gold_result.gold_promoted_count,
                "council_triggered": council_result.triggered,
                "council_output": council_result.debates[0].output.as_dict() if council_result.debates else None,
                "meta_gov_findings": [item.as_dict() for item in meta_findings],
                "graph_demotion_review_path": graph_review.get("source_path") if graph_review else None,
                "graph_demotion_next_apply_mode": graph_review.get("recommended_next_apply_mode") if graph_review else None,
                "graph_demotion_hotspot_family": graph_review.get("primary_hotspot_family") if graph_review else None,
                "graph_demotion_next_action": graph_review.get("recommended_next_action") if graph_review else None,
                "graph_demotion_quality_verdict": graph_review.get("quality_verdict") if graph_review else None,
                "graph_demotion_graph_readability_verdict": graph_review.get("graph_readability_verdict") if graph_review else None,
                "graph_demotion_reviewed_note_count": graph_review.get("reviewed_note_count") if graph_review else 0,
                "mentor_report_path": mentor_result.report_path,
                "mentor_state_path": mentor_result.state_path,
                "mentor_queue_root": mentor_result.queue_root,
                "mentor_active_probes": [item.as_dict() for item in mentor_result.active_probes],
                "mentor_pending_tasks": [item.as_dict() for item in mentor_result.pending_tasks],
                "mentor_completed_count": len(mentor_result.completed_tasks),
                "mentor_skipped_count": len(mentor_result.skipped_tasks),
                "mentor_weakness_registry": mentor_result.weakness_registry,
                "mentor_feedback_loop_ready": True,
            },
        },
    )
    latest_handoff = read_json(state.handoff_latest, default={}) or {}

    bus.publish(Event(type=EVENT_KAIROS, source="kairos", payload=record))
    logger.info("[kairos] heartbeat written")
    _write_vault_briefing(paths, next_actions, gold_result, mentor_result, record)
    _write_root_memory_packet(paths, latest_handoff, record)
    return record


def _write_vault_briefing(paths: Any, next_actions: list[str], gold_result: Any, mentor_result: Any, record: dict[str, Any]) -> None:
    vault_path = getattr(paths, "vault_path", None)
    if not vault_path:
        return
    briefing_dir = Path(vault_path) / ".Otto-Realm"
    briefing_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Otto Briefing — {record['ts']}",
        "",
        "## Current Focus",
    ]
    for action in next_actions[:4]:
        lines.append(f"- {action}")

    goal = record.get("graph_demotion_next_action") or ""
    if goal:
        lines.extend([
            "",
            "## Secondary System Context",
            f"- controller_goal: {goal}",
        ])

    lines.extend([
        "",
        "## Vault Health",
        f"- kairos_score: {gold_result.kairos_score:.2f}",
        f"- gold_promoted: {gold_result.gold_promoted_count}",
        f"- silver: {gold_result.silver_count}",
        f"- council_triggered: {record.get('council_triggered', False)}",
    ])

    if mentor_result.active_probes:
        probe = mentor_result.active_probes[0]
        lines.extend([
            "",
            "## Active Training Probe",
            f"- {probe.title} (gap: {probe.gap_type})",
        ])

    if mentor_result.pending_tasks:
        lines.extend([
            "",
            "## Pending Training Task",
            f"- {mentor_result.pending_tasks[0].title}",
        ])

    (briefing_dir / "briefing.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_root_memory_packet(paths: Any, handoff: dict[str, Any], record: dict[str, Any]) -> None:
    vault_path = getattr(paths, "vault_path", None)
    if not vault_path:
        return

    memory_path = Path(vault_path) / "MEMORY.md"
    archive_path = Path(vault_path) / "memory" / "root-memory-archive.md"
    _merge_startup_memory_archive(archive_path, _extract_startup_memory_tail(memory_path))
    archive_text = archive_path.read_text(encoding="utf-8").strip() if archive_path.exists() else ""
    recent_recalls = _recent_archive_recalls(archive_text)

    support_style = [str(item).strip() for item in handoff.get("profile_support_style") or [] if str(item).strip()]
    recovery_levers = [str(item).strip() for item in handoff.get("profile_recovery_levers") or [] if str(item).strip()]
    cognitive_risks = [str(item).strip() for item in handoff.get("profile_cognitive_risks") or [] if str(item).strip()]
    commitments = handoff.get("profile_commitments_to_recall") or []
    probes = handoff.get("mentor_active_probes") or []
    human_priorities = _human_priority_items(handoff)

    lines = [
        "# Session-Start Memory Packet",
        "",
        _STARTUP_MEMORY_START,
        f"Generated: {record.get('ts', handoff.get('updated_at', 'unknown'))}",
        "",
        "Use this packet as the canonical current-state human memory for the first reply.",
        "Default to Josh's human situation, commitments, and constraints before Otto runtime concerns.",
        "If the opening prompt is vague, emotional, overloaded, or underspecified, use the packet proactively before asking broad clarification questions.",
    ]

    lines.extend([
        "",
        "## Priority Decision Lens",
        "- Prioritize nearest cash, delivery, or human consequence before new system-building.",
        "- Prefer one realistic next step, short checklist, or simple schedule over parallel plans.",
        "- Escalate to stronger models or tools quickly when delegation saves time or lowers confusion.",
    ])

    if human_priorities:
        lines.extend([
            "",
            "## Likely Near-Term Human Priorities",
        ])
        lines.extend([f"- {item}" for item in human_priorities])

    if support_style:
        lines.extend(["", "## Human Support Style"])
        lines.extend([f"- {item}" for item in support_style[:3]])

    if cognitive_risks:
        lines.extend(["", "## Overload Risks To Watch"])
        lines.extend([f"- {item}" for item in cognitive_risks[:4]])

    if recovery_levers:
        lines.extend(["", "## Recovery Levers"])
        lines.extend([f"- {item}" for item in recovery_levers[:3]])

    if commitments:
        lines.extend(["", "## Commitments To Recall Before Asking Broad Questions"])
        for item in commitments[:5]:
            cue = str(item.get("cue") or "").strip()
            kind = str(item.get("kind") or "unknown").strip()
            horizon = str(item.get("horizon") or "unknown").strip()
            if cue and not _is_low_signal_cue(cue):
                lines.append(f"- {cue} | kind={kind} | horizon={horizon}")

    if recent_recalls:
        lines.extend(["", "## Recent Durable Recalls"])
        lines.extend([f"- {item}" for item in recent_recalls])

    if probes:
        lines.extend(["", "## Active Training Probes"])
        for probe in probes[:3]:
            title = str(probe.get("title") or "").strip()
            weakness = str(probe.get("weakness") or "").strip()
            if title:
                lines.append(f"- {title}" + (f" | weakness={weakness}" if weakness else ""))

    lines.extend([
        "",
        "## Archive",
        "- Historical long-term memory promotions are preserved in `memory/root-memory-archive.md` for semantic recall.",
        "- Prefer the startup packet above when current-state cues and older archive entries diverge.",
        _STARTUP_MEMORY_END,
        "",
    ])

    memory_path.write_text("\n".join(lines), encoding="utf-8")
