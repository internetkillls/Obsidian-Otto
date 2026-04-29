from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..openclaw_guardrails import live_openclaw_jobs_path, openclaw_cron_contract_path
from ..state import now_iso, read_json, write_json

DEFAULT_ESSAY_CONTROL: dict[str, Any] = {
    "mode": "normal",
    "paper_now_force": False,
    "paper_now_requested_at": "",
    "paper_now_reason": "",
    "max_completion_window_hours": 6,
    "last_started_at": "",
    "last_completed_at": "",
    "next_allowed_completion_at": "",
    "active_collection": "",
    "active_draft_path": "",
    "last_completed_title": "",
    "last_completed_source": "",
    "focus_topic": "",
    "focus_scope": "",
    "focus_until": "",
    "focus_started_at": "",
    "focus_requested_at": "",
    "focus_reason": "",
    "focus_source": "",
    "focus_window_days": 0,
}

_FOCUS_MODES = {"normal", "paper_topics", "paper_now"}


def essay_control_path(paths: Any | None = None) -> Path:
    base = paths or load_paths()
    return base.state_root / "handoff" / "essay_control.json"


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _parse_iso(value: Any) -> datetime | None:
    text = _coerce_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def _ensure_defaults(raw: dict[str, Any] | None) -> dict[str, Any]:
    control = dict(DEFAULT_ESSAY_CONTROL)
    if isinstance(raw, dict):
        control.update(raw)
    control["mode"] = _coerce_text(control.get("mode"), "normal")
    if control["mode"] not in _FOCUS_MODES:
        control["mode"] = "normal"
    control["paper_now_force"] = bool(control.get("paper_now_force", False))
    control["paper_now_requested_at"] = _coerce_text(control.get("paper_now_requested_at"))
    control["paper_now_reason"] = _coerce_text(control.get("paper_now_reason"))
    control["max_completion_window_hours"] = _coerce_int(control.get("max_completion_window_hours"), 6)
    control["last_started_at"] = _coerce_text(control.get("last_started_at"))
    control["last_completed_at"] = _coerce_text(control.get("last_completed_at"))
    control["next_allowed_completion_at"] = _coerce_text(control.get("next_allowed_completion_at"))
    control["active_collection"] = _coerce_text(control.get("active_collection"))
    control["active_draft_path"] = _coerce_text(control.get("active_draft_path"))
    control["last_completed_title"] = _coerce_text(control.get("last_completed_title"))
    control["last_completed_source"] = _coerce_text(control.get("last_completed_source"))
    control["focus_topic"] = _coerce_text(control.get("focus_topic"))
    control["focus_scope"] = _coerce_text(control.get("focus_scope"))
    control["focus_until"] = _coerce_text(control.get("focus_until"))
    control["focus_started_at"] = _coerce_text(control.get("focus_started_at"))
    control["focus_requested_at"] = _coerce_text(control.get("focus_requested_at"))
    control["focus_reason"] = _coerce_text(control.get("focus_reason"))
    control["focus_source"] = _coerce_text(control.get("focus_source"))
    control["focus_window_days"] = _coerce_int(control.get("focus_window_days"), 0)
    return control


def load_essay_control(paths: Any | None = None) -> dict[str, Any]:
    control_path = essay_control_path(paths)
    raw = read_json(control_path, default={}) or {}
    return _ensure_defaults(raw if isinstance(raw, dict) else {})


def write_essay_control(control: dict[str, Any], paths: Any | None = None) -> Path:
    control_path = essay_control_path(paths)
    write_json(control_path, _ensure_defaults(control))
    return control_path


def is_focus_active(control: dict[str, Any], *, now: datetime | None = None) -> bool:
    mode = _coerce_text(control.get("mode"), "normal")
    if mode == "paper_now":
        return True
    if mode != "paper_topics":
        return False
    current = now or datetime.now(timezone.utc).astimezone()
    until = _parse_iso(control.get("focus_until"))
    if until is None:
        return True
    return current < until


def _clear_focus_fields(control: dict[str, Any]) -> None:
    control["focus_topic"] = ""
    control["focus_scope"] = ""
    control["focus_until"] = ""
    control["focus_started_at"] = ""
    control["focus_requested_at"] = ""
    control["focus_reason"] = ""
    control["focus_source"] = ""
    control["focus_window_days"] = 0


def steer_essay_control(
    *,
    mode: str,
    topic: str = "",
    days: int = 2,
    reason: str = "",
    source: str = "cli",
    paths: Any | None = None,
) -> dict[str, Any]:
    normalized_mode = _coerce_text(mode, "normal")
    if normalized_mode not in _FOCUS_MODES:
        normalized_mode = "normal"

    control = load_essay_control(paths)
    now = datetime.now(timezone.utc).astimezone()
    now_text = now.isoformat(timespec="seconds")
    topic_text = _coerce_text(topic)
    reason_text = _coerce_text(reason)
    source_text = _coerce_text(source, "cli")
    window_days = max(_coerce_int(days, 0), 0)

    if normalized_mode == "normal":
        control["mode"] = "normal"
        control["paper_now_force"] = False
        control["paper_now_requested_at"] = ""
        control["paper_now_reason"] = ""
        _clear_focus_fields(control)
    elif normalized_mode == "paper_topics":
        control["mode"] = "paper_topics"
        control["paper_now_force"] = False
        control["paper_now_requested_at"] = ""
        control["paper_now_reason"] = ""
        control["focus_topic"] = topic_text or "paper topics"
        control["focus_scope"] = "paper topics"
        control["focus_started_at"] = now_text
        control["focus_requested_at"] = now_text
        control["focus_until"] = (now + timedelta(days=max(window_days, 1))).isoformat(timespec="seconds")
        control["focus_reason"] = reason_text or f"Paper topics focus for {max(window_days, 1)} day(s)"
        control["focus_source"] = source_text
        control["focus_window_days"] = max(window_days, 1)
    else:
        control["mode"] = "paper_now"
        control["paper_now_force"] = True
        control["paper_now_requested_at"] = now_text
        control["paper_now_reason"] = reason_text or f"Paper-now request via {source_text}"
        control["focus_topic"] = topic_text or control.get("focus_topic") or "paper now"
        control["focus_scope"] = "paper now"
        control["focus_started_at"] = now_text
        control["focus_requested_at"] = now_text
        control["focus_until"] = ""
        control["focus_reason"] = reason_text or f"Paper-now request via {source_text}"
        control["focus_source"] = source_text
        control["focus_window_days"] = 0

    write_essay_control(control, paths)
    return {
        "ok": True,
        "mode": control["mode"],
        "control_path": str(essay_control_path(paths)),
        "essay_control": control,
        "focus_active": is_focus_active(control, now=now),
        "requested_at": now_text,
        "source": source_text,
    }


def clear_essay_control(*, reason: str = "", source: str = "cli", paths: Any | None = None) -> dict[str, Any]:
    control = load_essay_control(paths)
    previous_mode = _coerce_text(control.get("mode"), "normal")
    control["mode"] = "normal"
    control["paper_now_force"] = False
    control["paper_now_requested_at"] = ""
    control["paper_now_reason"] = ""
    _clear_focus_fields(control)
    write_essay_control(control, paths)
    return {
        "ok": True,
        "mode": "normal",
        "previous_mode": previous_mode,
        "control_path": str(essay_control_path(paths)),
        "essay_control": control,
        "requested_at": now_iso(),
        "reason": _coerce_text(reason),
        "source": _coerce_text(source, "cli"),
    }


def _managed_job(job: dict[str, Any]) -> bool:
    name = _coerce_text(job.get("name") or job.get("id"))
    description = _coerce_text(job.get("description"))
    return (
        name.startswith("otto_")
        or name.startswith("Otto ")
        or "[managed-by=otto." in description
        or "[managed-by=memory-core.short-term-promotion]" in description
    )


def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
    schedule = job.get("schedule") or {}
    payload = job.get("payload") or {}
    return {
        "id": job.get("id"),
        "name": job.get("name"),
        "enabled": bool(job.get("enabled", False)),
        "schedule": {
            "kind": schedule.get("kind"),
            "expr": schedule.get("expr"),
            "tz": schedule.get("tz"),
        },
        "sessionTarget": job.get("sessionTarget"),
        "wakeMode": job.get("wakeMode"),
        "payload_kind": payload.get("kind"),
        "description": job.get("description"),
    }


def build_cron_status(*, paths: Any | None = None) -> dict[str, Any]:
    app_paths = paths or load_paths()
    control = load_essay_control(app_paths)
    current = datetime.now(timezone.utc).astimezone()
    focus_active = is_focus_active(control, now=current)
    focus_until = _parse_iso(control.get("focus_until"))

    jobs_payload = read_json(live_openclaw_jobs_path(), default={}) or {}
    jobs = jobs_payload.get("jobs") if isinstance(jobs_payload, dict) else []
    job_list = [job for job in jobs if isinstance(job, dict)]
    managed_jobs = [_job_summary(job) for job in job_list if _managed_job(job)]
    enabled_job_count = sum(1 for job in job_list if bool(job.get("enabled", False)))
    contract = read_json(openclaw_cron_contract_path(), default={}) or {}
    contract_validation = contract.get("validation") if isinstance(contract, dict) else {}
    if not isinstance(contract_validation, dict):
        contract_validation = {}

    return {
        "generated_at": now_iso(),
        "jobs_path": str(live_openclaw_jobs_path()),
        "contract_path": str(openclaw_cron_contract_path()),
        "job_count": len(job_list),
        "enabled_job_count": enabled_job_count,
        "managed_job_count": len(managed_jobs),
        "managed_jobs": managed_jobs,
        "contract_present": bool(contract),
        "contract_drift_free": contract_validation.get("drift_free"),
        "contract_issues": contract_validation.get("current_issues", []),
        "essay_control": control,
        "focus_active": focus_active,
        "focus_expired": control.get("mode") == "paper_topics" and bool(focus_until) and not focus_active,
        "steering": {
            "mode": control.get("mode"),
            "topic": control.get("focus_topic"),
            "scope": control.get("focus_scope"),
            "reason": control.get("focus_reason"),
            "source": control.get("focus_source"),
            "active": focus_active,
            "expires_at": focus_until.isoformat(timespec="seconds") if focus_until else None,
            "window_days": control.get("focus_window_days", 0),
            "paper_now_force": bool(control.get("paper_now_force", False)),
        },
    }
