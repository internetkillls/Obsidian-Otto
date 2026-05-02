from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..council.statement import build_council_statement_candidate
from ..creative.inspo import build_visual_inspo_query
from ..creative.songforge import build_song_skeleton
from ..governance_utils import append_jsonl, read_jsonl, state_root
from ..memento.scheduler_bridge import build_due_queue
from ..state import now_iso, write_json
from ..skills.blocker_map import skill_review
from ..autonomy.autonomous_scheduler import next_due_autonomous_jobs
from .creative_heartbeat import run_creative_heartbeat
from .cron_plan import build_planned_jobs
from ..research.paper_onboarding import create_onboarding_pack


PAPER_INTENTS = ("paper cron", "cron paper", "paper now", "bikin paper", "paper onboarding", "kasih paper")
SONG_INTENTS = ("bikin lagu", "lagu sekarang", "song now", "song skeleton", "bikin midi")
WEAKNESS_INTENTS = ("weakness point", "cari blocker", "psychometric support", "audhd support", "bd support", "council weakness")
MEMENTO_INTENTS = ("memento", "quiz me", "apa yang harus kuingat")
VISUAL_INTENTS = ("visual inspo", "gambar referensi", "art inspo")
HEARTBEAT_INTENTS = ("heartbeat now", "creative heartbeat", "run heartbeat")


def heartbeat_router_last_path() -> Path:
    return state_root() / "runtime" / "heartbeat_router_last.json"


def heartbeat_router_runs_path() -> Path:
    return state_root() / "runtime" / "heartbeat_router_runs.jsonl"


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.fromisoformat(now_iso())


def _looks_like_immediate_paper_request(message: str) -> bool:
    msg = message.lower()
    return ("paper now" in msg) or ("sekarang" in msg) or ("bikin paper" in msg) or ("kasih paper" in msg)


def _extract_song_seed(message: str) -> str:
    text = message.strip()
    hash_index = text.find("#")
    if hash_index >= 0:
        seed = text[hash_index:]
        seed = seed.replace(" @", "\n@")
        seed = seed.replace("\t@", "\n@")
        return seed
    return "# Cinta Fana\n@ Penderitaan dan cinta tak kenal waktu."


def _last_success_by_job_name(job_name: str) -> datetime | None:
    rows = read_jsonl(heartbeat_router_runs_path())
    for row in reversed(rows):
        if str(row.get("job_name", "")).strip() != job_name:
            continue
        if not bool(row.get("ok")):
            continue
        dt = _parse_iso(row.get("timestamp"))
        if dt:
            return dt
    return None


def next_due_jobs(*, now: datetime | None = None) -> dict[str, Any]:
    current = now or _now()
    due: list[dict[str, Any]] = []
    all_jobs: list[dict[str, Any]] = []
    for job in build_planned_jobs():
        cadence = job.get("cadence") or {}
        name = str(job.get("name") or "")
        last_run_at = _last_success_by_job_name(name)
        min_hours: float | None = None
        max_hours: float | None = None
        if "every_hours" in cadence:
            min_hours = float(cadence["every_hours"])
            max_hours = float(cadence["every_hours"])
        if "policy_window_hours" in cadence:
            window = cadence.get("policy_window_hours") or []
            if len(window) >= 2:
                min_hours = float(window[0])
                max_hours = float(window[1])
        elapsed_hours = None
        due_now = False
        overdue = False
        next_due_at = current.isoformat(timespec="seconds")
        if last_run_at is None:
            due_now = True
        elif min_hours is not None:
            elapsed_hours = max(0.0, (current - last_run_at).total_seconds() / 3600.0)
            due_now = elapsed_hours >= min_hours
            if max_hours is not None:
                overdue = elapsed_hours >= max_hours
                next_due_at = (last_run_at + timedelta(hours=min_hours)).isoformat(timespec="seconds")
        status = {
            "job_name": name,
            "last_run_at": last_run_at.isoformat(timespec="seconds") if last_run_at else None,
            "elapsed_hours": round(elapsed_hours, 2) if elapsed_hours is not None else None,
            "due_now": due_now,
            "overdue": overdue,
            "next_due_at": next_due_at,
            "cadence": cadence,
            "command": job.get("command"),
            "expected_output": job.get("expected_output"),
        }
        all_jobs.append(status)
        if due_now:
            due.append(status)
    return {
        "ok": True,
        "checked_at": now_iso(),
        "job_count": len(all_jobs),
        "due_count": len(due),
        "due_jobs": due,
        "autonomous": next_due_autonomous_jobs(now=current),
        "jobs": all_jobs,
    }


def _ensure_contract(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("ok", False)
    payload.setdefault("routed_to", "none")
    payload.setdefault("state_changed", False)
    payload.setdefault("created_ids", [])
    payload.setdefault("expected_outputs", [])
    payload.setdefault("actual_outputs", [])
    payload.setdefault("no_output_reason", None)
    payload.setdefault("warnings", [])
    payload.setdefault("blockers", [])
    payload.setdefault("review_required", True)
    if payload["ok"] and not payload["actual_outputs"] and not payload["no_output_reason"]:
        payload["no_output_reason"] = "no_output_generated"
        payload["warnings"] = [*payload.get("warnings", []), "auto_filled_no_output_reason"]
    return payload


def _persist(message: str, payload: dict[str, Any], *, job_name: str | None = None) -> None:
    event = {
        "timestamp": now_iso(),
        "message": message,
        "ok": bool(payload.get("ok")),
        "routed_to": payload.get("routed_to"),
        "job_name": job_name or payload.get("routed_to"),
        "state_changed": bool(payload.get("state_changed")),
        "created_ids": payload.get("created_ids", []),
        "expected_outputs": payload.get("expected_outputs", []),
        "actual_outputs": payload.get("actual_outputs", []),
        "no_output_reason": payload.get("no_output_reason"),
        "warnings": payload.get("warnings", []),
        "blockers": payload.get("blockers", []),
        "review_required": True,
    }
    append_jsonl(heartbeat_router_runs_path(), event)
    write_json(heartbeat_router_last_path(), event)


def _route_paper(message: str) -> dict[str, Any]:
    immediate = _looks_like_immediate_paper_request(message)
    if immediate:
        result = create_onboarding_pack("HCI value-sensitive design and interface constraints", dry_run=False)
        payload = _ensure_contract(
            {
                "ok": bool(result.get("ok")),
                "routed_to": "paper-onboarding --force-candidate",
                "state_changed": True,
                "created_ids": [result.get("pack", {}).get("pack_id")] if result.get("pack") else [],
                "expected_outputs": ["state/research/onboarding_packs.jsonl"],
                "actual_outputs": ["state/research/onboarding_packs.jsonl"] if result.get("pack") else [],
                "warnings": [],
                "blockers": [],
                "review_required": True,
                "result": result,
            }
        )
        _persist(message, payload, job_name="paper_onboarding")
        return payload

    due = next_due_jobs()
    paper_due = next((job for job in due.get("jobs", []) if job.get("job_name") == "paper_onboarding"), {})
    if paper_due.get("due_now"):
        result = create_onboarding_pack("HCI value-sensitive design and interface constraints", dry_run=True)
        payload = _ensure_contract(
            {
                "ok": bool(result.get("ok")),
                "routed_to": "paper-onboarding --dry-run",
                "state_changed": False,
                "created_ids": [result.get("pack", {}).get("pack_id")] if result.get("pack") else [],
                "expected_outputs": ["state/research/onboarding_packs.jsonl"],
                "actual_outputs": ["paper_onboarding_candidate_preview"] if result.get("pack") else [],
                "warnings": [],
                "blockers": [],
                "review_required": True,
                "result": result,
                "heartbeat_status": paper_due,
            }
        )
        _persist(message, payload, job_name="paper_onboarding")
        return payload

    payload = _ensure_contract(
        {
            "ok": True,
            "routed_to": "paper-heartbeat-status",
            "state_changed": False,
            "created_ids": [],
            "expected_outputs": ["state/schedules/planned_jobs.jsonl"],
            "actual_outputs": ["state/schedules/planned_jobs.jsonl"],
            "no_output_reason": "paper_onboarding_not_due_yet",
            "warnings": [],
            "blockers": [],
            "review_required": True,
            "heartbeat_status": paper_due,
            "due_jobs": due,
        }
    )
    _persist(message, payload, job_name="paper_onboarding")
    return payload


def _route_song(message: str) -> dict[str, Any]:
    result = build_song_skeleton(_extract_song_seed(message), dry_run=True)
    payload = _ensure_contract(
        {
            "ok": bool(result.get("ok")),
            "routed_to": "song-skeleton --dry-run",
            "state_changed": False,
            "created_ids": [result.get("skeleton", {}).get("song_skeleton_id")] if result.get("skeleton") else [],
            "expected_outputs": ["state/creative/songforge/song_skeletons.jsonl"],
            "actual_outputs": ["song_skeleton_candidate_preview"] if result.get("skeleton") else [],
            "warnings": [],
            "blockers": [],
            "review_required": True,
            "result": result,
        }
    )
    _persist(message, payload, job_name="song_skeleton")
    return payload


def _route_weakness(message: str) -> dict[str, Any]:
    result = skill_review(dry_run=True)
    warnings = ["support_context_only_non_diagnostic_for_audhd_bd"]
    created_ids = [item.get("training_task_id") for item in result.get("tasks", []) if item.get("training_task_id")]
    created_ids = list(dict.fromkeys(created_ids))
    extras: dict[str, Any] = {}
    if ("council" in message.lower()) or ("weakness point" in message.lower()):
        council = build_council_statement_candidate(
            {
                "source": "heartbeat_router",
                "message": message,
                "intent": "weakness_support",
            }
        )
        if council.get("statement_id"):
            created_ids.append(council["statement_id"])
            extras["council_candidate"] = council
    payload = _ensure_contract(
        {
            "ok": bool(result.get("ok")),
            "routed_to": "blocker-experiment --dry-run",
            "state_changed": bool(extras.get("council_candidate")),
            "created_ids": created_ids,
            "expected_outputs": ["state/skills/training_tasks.jsonl"],
            "actual_outputs": ["blocker_experiment_candidate_preview"] if result.get("tasks") else [],
            "warnings": warnings,
            "blockers": [],
            "review_required": True,
            "result": result,
            **extras,
        }
    )
    _persist(message, payload, job_name="blocker_experiment")
    return payload


def _route_memento(message: str) -> dict[str, Any]:
    result = build_due_queue()
    actual_outputs = ["state/memento/quiz_queue.jsonl"] if int(result.get("quiz_count", 0) or 0) > 0 else []
    payload = _ensure_contract(
        {
            "ok": bool(result.get("ok")),
            "routed_to": "memento-due",
            "state_changed": bool(actual_outputs),
            "created_ids": [item.get("quiz_id") for item in result.get("quizzes", []) if item.get("quiz_id")],
            "expected_outputs": ["state/memento/quiz_queue.jsonl"],
            "actual_outputs": actual_outputs,
            "no_output_reason": None if actual_outputs else "no_quizworthy_blocks_due",
            "warnings": [],
            "blockers": [],
            "review_required": True,
            "result": result,
        }
    )
    _persist(message, payload, job_name="memento_due")
    return payload


def _route_visual(message: str) -> dict[str, Any]:
    result = build_visual_inspo_query("manual")
    payload = _ensure_contract(
        {
            "ok": bool(result.get("ok")),
            "routed_to": "visual-inspo-query --dry-run",
            "state_changed": False,
            "created_ids": [],
            "expected_outputs": ["state/creative/inspo_packs/"],
            "actual_outputs": ["visual_inspo_query_candidate_preview"] if result.get("visual_query") else [],
            "warnings": [],
            "blockers": [],
            "review_required": True,
            "result": result,
        }
    )
    _persist(message, payload, job_name="visual_inspo")
    return payload


def _route_heartbeat(message: str) -> dict[str, Any]:
    result = run_creative_heartbeat(dry_run=True, explain=True)
    expected_outputs = [
        "state/creative/songforge/song_skeletons.jsonl",
        "state/research/onboarding_packs.jsonl",
        "state/memento/quiz_queue.jsonl",
        "state/skills/training_tasks.jsonl",
    ]
    actual_outputs: list[str] = []
    if result.get("song_skeleton"):
        actual_outputs.append("song_skeleton_candidate_preview")
    if result.get("paper_onboarding"):
        actual_outputs.append("paper_onboarding_candidate_preview")
    if result.get("blocker_experiment"):
        actual_outputs.append("blocker_experiment_candidate_preview")
    if result.get("memento_due") is not None:
        actual_outputs.append("memento_due_queue_or_reason")
    payload = _ensure_contract(
        {
            "ok": bool(result.get("ok")),
            "routed_to": "creative-heartbeat --dry-run --explain",
            "state_changed": False,
            "created_ids": [],
            "expected_outputs": expected_outputs,
            "actual_outputs": actual_outputs,
            "warnings": [],
            "blockers": [],
            "review_required": True,
            "result": result,
        }
    )
    _persist(message, payload, job_name="creative_heartbeat")
    return payload


def _route_due_jobs_fallback(message: str) -> dict[str, Any] | None:
    due = next_due_jobs()
    if int(due.get("due_count", 0) or 0) <= 0:
        return None
    result = run_creative_heartbeat(dry_run=True, explain=True)
    payload = _ensure_contract(
        {
            "ok": bool(result.get("ok")),
            "routed_to": "scheduled_due_jobs",
            "state_changed": False,
            "created_ids": [],
            "expected_outputs": ["state/schedules/planned_jobs.jsonl"],
            "actual_outputs": [f"due_jobs:{due.get('due_count', 0)}"],
            "warnings": ["legacy_no_action_bypassed_due_jobs"],
            "blockers": [],
            "review_required": True,
            "due_jobs": due,
            "result": result,
        }
    )
    _persist(message, payload, job_name="scheduled_due_jobs")
    return payload


def route_telegram_heartbeat_message(message: str, *, schedule_fallback: bool = True) -> dict[str, Any] | None:
    text = message.strip()
    msg = text.lower()
    if any(intent in msg for intent in PAPER_INTENTS):
        return _route_paper(text)
    if any(intent in msg for intent in SONG_INTENTS):
        return _route_song(text)
    if any(intent in msg for intent in WEAKNESS_INTENTS):
        return _route_weakness(text)
    if any(intent in msg for intent in MEMENTO_INTENTS):
        return _route_memento(text)
    if any(intent in msg for intent in VISUAL_INTENTS):
        return _route_visual(text)
    if any(intent in msg for intent in HEARTBEAT_INTENTS):
        return _route_heartbeat(text)
    if schedule_fallback:
        return _route_due_jobs_fallback(text)
    return None


def heartbeat_router_test(message: str) -> dict[str, Any]:
    routed = route_telegram_heartbeat_message(message, schedule_fallback=True)
    if routed:
        return routed
    payload = _ensure_contract(
        {
            "ok": True,
            "routed_to": "no_route",
            "state_changed": False,
            "created_ids": [],
            "expected_outputs": [],
            "actual_outputs": [],
            "no_output_reason": "no_matching_intent_and_no_due_jobs",
            "warnings": [],
            "blockers": [],
            "review_required": True,
        }
    )
    _persist(message, payload, job_name="no_route")
    return payload
