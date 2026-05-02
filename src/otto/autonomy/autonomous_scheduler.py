from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..governance_utils import state_root
from ..state import now_iso, read_json
from .generation_policy import load_autonomous_generation_policy


def autonomous_generation_last_path() -> Path:
    return state_root() / "autonomy" / "autonomous_generation_last.json"


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _last_run(kind: str) -> datetime | None:
    last = read_json(autonomous_generation_last_path(), default={}) or {}
    by_kind = last.get("by_kind") if isinstance(last, dict) else {}
    if not isinstance(by_kind, dict):
        return None
    return _parse_iso((by_kind.get(kind) or {}).get("created_at") if isinstance(by_kind.get(kind), dict) else None)


def next_due_autonomous_jobs(*, now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.fromisoformat(now_iso())
    policy = load_autonomous_generation_policy()
    cadence = policy.get("cadence") or {}
    specs = [
        ("autonomous_song_skeleton", "song", float(cadence.get("song_skeleton_every_hours") or 4)),
        ("autonomous_paper_onboarding", "paper", float(cadence.get("paper_onboarding_every_hours_min") or 4)),
    ]
    jobs: list[dict[str, Any]] = []
    due: list[dict[str, Any]] = []
    for job_name, kind, every_hours in specs:
        last_run_at = _last_run(kind)
        due_now = last_run_at is None or (current - last_run_at) >= timedelta(hours=every_hours)
        next_due_at = current if last_run_at is None else last_run_at + timedelta(hours=every_hours)
        job = {
            "job": job_name,
            "kind": kind,
            "last_run_at": last_run_at.isoformat(timespec="seconds") if last_run_at else None,
            "due_now": due_now,
            "next_due_at": next_due_at.isoformat(timespec="seconds"),
            "reason": "last run missing or cadence elapsed" if due_now else "not_due_yet",
            "source": "note_vector + steering_vector",
            "review_required": True,
        }
        jobs.append(job)
        if due_now:
            due.append(job)
    return {"ok": True, "checked_at": now_iso(), "due_count": len(due), "due": due, "jobs": jobs}

