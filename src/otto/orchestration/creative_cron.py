from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_PRODUCTION_CRON_POLICY: dict[str, Any] = {
    "version": 1,
    "mode": "planned_not_autonomous",
    "default_safety": {
        "auto_publish": False,
        "auto_write_public": False,
        "auto_send": False,
        "review_required_before_publication": True,
    },
    "cadences": {
        "daily": [
            {
                "job": "daily_handoff",
                "command": "python3 -m otto.cli daily-loop --dry-run",
                "output": "state/human/daily_handoff.json",
            },
            {
                "job": "artifact_inbox_triage",
                "command": "python3 -m otto.cli artifact-triage --dry-run",
                "output": "state/artifacts/artifact_routes.jsonl",
            },
        ],
        "weekly": [
            {
                "job": "song_sketch_day",
                "command": "python3 -m otto.cli song-skeleton --dry-run",
                "output": "state/creative/songforge/song_skeletons.jsonl",
            }
        ],
    },
}


def production_cron_policy_path() -> Path:
    return state_root() / "schedules" / "production_cron_policy.json"


def planned_jobs_path() -> Path:
    return state_root() / "schedules" / "planned_jobs.jsonl"


def load_production_cron_policy() -> dict[str, Any]:
    return ensure_json(production_cron_policy_path(), DEFAULT_PRODUCTION_CRON_POLICY)


def production_cron_plan() -> dict[str, Any]:
    policy = load_production_cron_policy()
    jobs = [job for jobs in policy["cadences"].values() for job in jobs]
    return {
        "ok": True,
        "mode": policy["mode"],
        "auto_publish": False,
        "review_required_before_publication": True,
        "jobs": jobs,
    }
