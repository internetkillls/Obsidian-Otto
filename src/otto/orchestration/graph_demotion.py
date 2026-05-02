from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..config import AppPaths, load_paths
from ..openclaw_support import build_openclaw_health, probe_openclaw_gateway
from ..state import now_iso, read_json, write_json

GRAPH_DEMOTION_REVIEW_MAX_AGE_HOURS = 24
GRAPH_CONTROLLER_FALLBACK_GOAL = "Maintain a stable Obsidian-Otto retrieval core"


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def graph_demotion_review_path(paths: AppPaths | None = None) -> Path:
    active_paths = paths or load_paths()
    return active_paths.state_root / "run_journal" / "graph_demotion_review_latest.json"


def load_graph_demotion_review(
    paths: AppPaths | None = None,
    *,
    max_age_hours: int = GRAPH_DEMOTION_REVIEW_MAX_AGE_HOURS,
    require_fresh: bool = True,
) -> dict[str, Any] | None:
    active_paths = paths or load_paths()
    path = graph_demotion_review_path(active_paths)
    data = read_json(path, default={}) or {}
    if not isinstance(data, dict) or not data:
        return None

    updated_at = str(data.get("updated_at") or data.get("ts") or "").strip()
    ts = _parse_ts(updated_at)
    age_hours: float | None = None
    fresh = False
    if ts is not None:
        age_hours = max(
            0.0,
            (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0,
        )
        fresh = age_hours <= max(max_age_hours, 0)

    payload = dict(data)
    payload["source_path"] = str(path)
    payload["fresh"] = fresh
    if age_hours is not None:
        payload["age_hours"] = round(age_hours, 3)

    if require_fresh and not fresh:
        return None
    return payload


def graph_action_candidates(review: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not review:
        return []
    action = str(review.get("recommended_next_action") or "").strip()
    if not action:
        return []
    mode = str(review.get("recommended_next_apply_mode") or "mixed-family").strip() or "mixed-family"
    family = str(review.get("primary_hotspot_family") or "unknown").strip() or "unknown"
    verdict = str(review.get("graph_readability_verdict") or "inconclusive").strip() or "inconclusive"
    return [
        {
            "action": action,
            "priority": 100,
            "source": "graph_demotion_review",
            "reason": f"{mode} via {family} ({verdict})",
            "context": {
                "recommended_next_apply_mode": mode,
                "primary_hotspot_family": family,
                "graph_readability_verdict": verdict,
                "reviewed_note_count": int(review.get("reviewed_note_count") or 0),
                "source_path": review.get("source_path"),
            },
        }
    ]


def graph_controller_goal(review: dict[str, Any] | None) -> str:
    if not review:
        return GRAPH_CONTROLLER_FALLBACK_GOAL
    mode = str(review.get("recommended_next_apply_mode") or "mixed-family").strip() or "mixed-family"
    family = str(review.get("primary_hotspot_family") or "graph-demotion").strip() or "graph-demotion"
    return f"Advance graph-demotion cleanup via {mode} follow-up on {family}"


def _dedupe_text(items: list[str], *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        cleaned = str(item or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def graph_handoff_is_active(review: dict[str, Any] | None, handoff: dict[str, Any] | None = None) -> bool:
    if not review:
        return False
    payload = handoff or {}
    review_path = str(review.get("source_path") or "").strip()
    graph_path = str(payload.get("graph_demotion_review_path") or "").strip()
    goal = str(payload.get("goal") or "").strip()
    review_action = str(review.get("recommended_next_action") or "").strip()
    next_actions = [str(item).strip() for item in (payload.get("next_actions") or []) if str(item).strip()]
    if review_path and graph_path and Path(review_path) == Path(graph_path):
        return True
    if goal and goal == graph_controller_goal(review):
        return True
    if review_action and review_action in next_actions:
        return True
    return False


def graph_controller_next_actions(
    review: dict[str, Any] | None,
    *,
    handoff: dict[str, Any] | None = None,
    fallback_actions: list[str] | None = None,
) -> list[str]:
    review_action = str((review or {}).get("recommended_next_action") or "").strip()
    handoff_actions = [str(item).strip() for item in ((handoff or {}).get("next_actions") or []) if str(item).strip()]
    if review and graph_handoff_is_active(review, handoff) and handoff_actions:
        return _dedupe_text(([review_action] if review_action else []) + handoff_actions + list(fallback_actions or []))
    if review_action:
        return _dedupe_text([review_action] + handoff_actions + list(fallback_actions or []))
    return _dedupe_text(handoff_actions + list(fallback_actions or []))


def graph_controller_handoff_fields(
    review: dict[str, Any] | None,
    *,
    handoff: dict[str, Any] | None = None,
    fallback_actions: list[str] | None = None,
) -> dict[str, Any]:
    if not review:
        return {
            "goal": str((handoff or {}).get("goal") or GRAPH_CONTROLLER_FALLBACK_GOAL),
            "next_actions": _dedupe_text(
                [str(item).strip() for item in ((handoff or {}).get("next_actions") or []) if str(item).strip()]
                + list(fallback_actions or [])
            ),
            "graph_demotion_review_path": None,
            "graph_demotion_next_apply_mode": None,
            "graph_demotion_hotspot_family": None,
            "graph_demotion_next_action": None,
            "graph_demotion_quality_verdict": None,
            "graph_demotion_graph_readability_verdict": None,
            "graph_demotion_reviewed_note_count": 0,
        }
    return {
        "goal": graph_controller_goal(review),
        "next_actions": graph_controller_next_actions(review, handoff=handoff, fallback_actions=fallback_actions),
        "graph_demotion_review_path": review.get("source_path"),
        "graph_demotion_next_apply_mode": review.get("recommended_next_apply_mode"),
        "graph_demotion_hotspot_family": review.get("primary_hotspot_family"),
        "graph_demotion_next_action": review.get("recommended_next_action"),
        "graph_demotion_quality_verdict": review.get("quality_verdict"),
        "graph_demotion_graph_readability_verdict": review.get("graph_readability_verdict"),
        "graph_demotion_reviewed_note_count": review.get("reviewed_note_count") or 0,
    }


def graph_research_topic(review: dict[str, Any] | None) -> str:
    if not review:
        return ""
    existing = str(review.get("openclaw_topic") or "").strip()
    if existing:
        return existing
    mode = str(review.get("recommended_next_apply_mode") or "mixed-family").strip() or "mixed-family"
    family = str(review.get("primary_hotspot_family") or "graph-demotion").strip() or "graph-demotion"
    return f"{mode} graph demotion follow-up for {family} after reviewed bounded apply"


def graph_ready_for_fetch(review: dict[str, Any] | None) -> bool:
    if not review:
        return False
    if "ready_for_openclaw_fetch" in review:
        return bool(review.get("ready_for_openclaw_fetch"))
    return str(review.get("quality_verdict") or "").strip().lower() in {"ready", "good"}


def _ensure_checkpoint_dir(paths: AppPaths) -> Path:
    checkpoint_dir = paths.state_root / "run_journal" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir


def _write_operator_summary(paths: AppPaths, payload: dict[str, Any]) -> Path:
    report_dir = paths.repo_root / "artifacts" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "graph_demotion_followup.md"
    lines = [
        "# Graph Demotion Follow-Up",
        "",
        f"- ts: `{payload['ts']}`",
        f"- status: `{payload['status']}`",
        f"- review_path: `{payload.get('graph_demotion_review_path') or 'n/a'}`",
        f"- hotspot_family: `{payload.get('graph_demotion_hotspot_family') or 'n/a'}`",
        f"- apply_mode: `{payload.get('graph_demotion_next_apply_mode') or 'n/a'}`",
        f"- gateway_ok: `{payload.get('gateway_ok')}`",
        f"- gateway_reason: `{payload.get('gateway_reason')}`",
        f"- fetched_or_applied: `{payload.get('applied_count', 0)}`",
        f"- blocked_count: `{payload.get('blocked_count', 0)}`",
        "",
        "## Notes",
    ]
    notes = payload.get("notes") or []
    lines.extend([f"- {item}" for item in notes] or ["- none"])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def run_graph_demotion_followup(
    *,
    max_demotion_writes: int = 6,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    paths = load_paths()
    review = load_graph_demotion_review(paths, require_fresh=False)
    review_path = graph_demotion_review_path(paths)
    ts = now_iso()
    base_result: dict[str, Any] = {
        "ts": ts,
        "review_path": str(review_path),
        "graph_demotion_review_path": str(review_path),
        "graph_demotion_next_apply_mode": None,
        "graph_demotion_hotspot_family": None,
        "graph_demotion_next_action": None,
        "gateway_ok": False,
        "gateway_reason": "review-unavailable",
        "status": "blocked",
        "applied_count": 0,
        "blocked_count": 0,
        "notes": [],
    }

    if not review:
        base_result["notes"] = ["Latest graph review is missing or stale."]
        base_result["blocked_count"] = 1
        checkpoint_dir = _ensure_checkpoint_dir(paths)
        checkpoint_path = checkpoint_dir / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_graph_demotion_followup.json"
        write_json(checkpoint_path, base_result)
        base_result["checkpoint_path"] = str(checkpoint_path)
        base_result["report_path"] = str(_write_operator_summary(paths, base_result))
        return base_result

    base_result.update(
        {
            "graph_demotion_next_apply_mode": review.get("recommended_next_apply_mode"),
            "graph_demotion_hotspot_family": review.get("primary_hotspot_family"),
            "graph_demotion_next_action": review.get("recommended_next_action"),
            "reviewed_note_count": int(review.get("reviewed_note_count") or 0),
            "quality_verdict": review.get("quality_verdict"),
            "graph_readability_verdict": review.get("graph_readability_verdict"),
            "review_fresh": bool(review.get("fresh", False)),
            "review_age_hours": review.get("age_hours"),
        }
    )

    health = build_openclaw_health()
    gateway_probe = probe_openclaw_gateway(timeout_seconds=min(max(timeout_seconds, 1), 10))
    gateway_ok = bool(gateway_probe.get("ok")) and bool(health.get("managed_hashes_match"))
    gateway_reason = gateway_probe.get("reason") or "gateway-preflight-failed"
    base_result["gateway_ok"] = gateway_ok
    base_result["gateway_reason"] = gateway_reason
    base_result["openclaw_health"] = health
    base_result["gateway_probe"] = gateway_probe

    notes: list[str] = []
    blocked_count = 0
    applied_count = 0

    if not graph_ready_for_fetch(review):
        notes.append("Reviewed graph is not ready for fetch/apply.")
        blocked_count += 1
    if str(review.get("recommended_next_apply_mode") or "").strip() != "ALLO-only":
        notes.append("Review is not ALLO-only, so the follow-up stays blocked.")
        blocked_count += 1
    if str(review.get("primary_hotspot_family") or "").strip() != "ALLOCATION-FAMILY":
        notes.append("Hotspot family is not ALLOCATION-FAMILY, so the follow-up stays blocked.")
        blocked_count += 1
    if not gateway_ok:
        notes.append(f"OpenClaw gateway preflight failed: {gateway_reason}.")
        blocked_count += 1
    if not bool(review.get("fresh", False)):
        notes.append("Latest graph review is stale; refresh it before applying the follow-up.")
        blocked_count += 1

    if blocked_count == 0:
        script = paths.repo_root / "scripts" / "c4_graph_rollup_audit.py"
        cmd = [
            sys.executable,
            str(script),
            "--apply-demotion-plan",
            "--max-demotion-writes",
            str(max_demotion_writes),
            "--family-prefix",
            "ALLO",
            "--only-action",
            "demote frontmatter",
        ]
        proc = subprocess.run(cmd, cwd=paths.repo_root, capture_output=True, text=True, check=False)
        base_result["apply_exit_code"] = proc.returncode
        base_result["apply_stdout"] = (proc.stdout or "").strip()
        base_result["apply_stderr"] = (proc.stderr or "").strip()
        if proc.returncode == 0:
            applied_count = int(review.get("reviewed_note_count") or 0)
            notes.append(
                f"Applied bounded ALLOCATION-FAMILY follow-up with max_demotion_writes={max_demotion_writes}."
            )
            base_result["status"] = "applied"
        else:
            blocked_count += 1
            notes.append("Bounded apply command failed.")
            base_result["status"] = "blocked"

    base_result["applied_count"] = applied_count
    base_result["blocked_count"] = blocked_count
    base_result["notes"] = notes
    checkpoint_dir = _ensure_checkpoint_dir(paths)
    checkpoint_path = checkpoint_dir / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_graph_demotion_followup.json"
    write_json(checkpoint_path, base_result)
    base_result["checkpoint_path"] = str(checkpoint_path)
    base_result["report_path"] = str(_write_operator_summary(paths, base_result))
    return base_result
