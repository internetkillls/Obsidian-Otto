from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..governance_utils import ensure_jsonl, state_root
from ..state import now_iso


def planned_jobs_path() -> Path:
    return state_root() / "schedules" / "planned_jobs.jsonl"


def build_planned_jobs() -> list[dict[str, Any]]:
    launcher = "/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-cli-wsl.sh"
    return [
        {
            "job_id": "job_song_skeleton",
            "name": "song_skeleton",
            "cadence": {"every_hours": 4},
            "command": f"{launcher} autonomous-generate --kind song --dry-run",
            "expected_output": "state/creative/songforge/autonomous_song_candidates.jsonl",
            "review_gated": True,
        },
        {
            "job_id": "job_paper_onboarding",
            "name": "paper_onboarding",
            "cadence": {"every_hours": 5, "policy_window_hours": [4, 6]},
            "command": f"{launcher} autonomous-generate --kind paper --dry-run",
            "expected_output": "state/research/autonomous_paper_candidates.jsonl",
            "review_gated": True,
        },
        {
            "job_id": "job_blocker_experiment",
            "name": "blocker_experiment",
            "cadence": {"every_hours": 24},
            "command": f"{launcher} blocker-experiment --dry-run",
            "expected_output": "state/skills/training_tasks.jsonl",
            "review_gated": True,
        },
        {
            "job_id": "job_memento_due",
            "name": "memento_due",
            "cadence": {"every_hours": 8},
            "command": f"{launcher} memento-due",
            "expected_output": "state/memento/quiz_queue.jsonl",
            "review_gated": True,
        },
    ]


def write_cron_plan() -> dict[str, Any]:
    jobs = build_planned_jobs()
    target = planned_jobs_path()
    ensure_jsonl(target)
    lines = [json.dumps({**job, "planned_at": now_iso()}, ensure_ascii=False) for job in jobs]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(target), "jobs": jobs, "job_count": len(jobs)}
