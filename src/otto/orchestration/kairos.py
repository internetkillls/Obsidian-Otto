from __future__ import annotations

from datetime import datetime, timezone
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

    council_result = CouncilEngine().run(
        gold_result=gold_result,
        unresolved=base_actions,
        action_candidates=graph_action_candidates(graph_review),
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

    handoff_before_mentor = read_json(state.handoff_latest, default={}) or {}
    mentor_result = MentoringEngine().run(profile=handoff_before_mentor)

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
    strategy_lines.append(
        f"- contradictions={len(gold_result.contradictions)} dynamic_thresholds={len(gold_result.dynamic_thresholds)}"
    )
    for item in gold_result.scored_signals[:3]:
        strategy_lines.append(
            f"- {item.note_path} score={item.total_score:.2f} threshold={item.threshold:.2f} promoted={item.promoted}"
        )

    strategy_lines.extend(["", "## Council"])
    strategy_lines.append(f"- trigger_count={council_result.trigger_count}")
    if council_result.debates:
        first_debate = council_result.debates[0]
        strategy_lines.append(
            f"- {first_debate.trigger_category} recurrence={first_debate.recurrence_count} next_action={first_debate.next_action}"
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
        "artifacts/reports/dream_summary.md",
        "artifacts/reports/mentor_daily.md",
    ]
    if graph_review:
        handoff_artifacts.append(str(graph_review.get("source_path")))
    write_json(
        state.handoff_latest,
        {
            **(read_json(state.handoff_latest, default={}) or {}),
            "updated_at": now_iso(),
            "status": "ready",
            "goal": graph_controller_goal(graph_review),
            "artifacts": handoff_artifacts,
            "next_actions": next_actions,
            "kairos_score": round(gold_result.kairos_score, 3),
            "gold_promoted_count": gold_result.gold_promoted_count,
            "council_triggered": council_result.triggered,
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
    )

    bus.publish(Event(type=EVENT_KAIROS, source="kairos", payload=record))
    logger.info("[kairos] heartbeat written")
    return record
