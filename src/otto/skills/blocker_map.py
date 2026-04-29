from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, ensure_json, make_id, state_root
from ..state import now_iso


DEFAULT_BLOCKER_MAP: dict[str, Any] = {
    "version": 1,
    "blockers": [
        {
            "blocker_id": "blk_001",
            "domain": "music_production",
            "skill": "arrangement_completion",
            "blocker_type": "transition_gap",
            "description": "Fragment-to-finished arrangement needs a bounded pipeline.",
            "support_lens": "structure_without_killing_novelty",
            "training_task": "Convert one 8-bar loop into A/B/chorus skeleton within 45 minutes.",
            "done_signal": "Section map and bounced rough demo exist.",
        },
        {
            "blocker_id": "blk_002",
            "domain": "engineering",
            "skill": "testing_and_ci",
            "blocker_type": "practice_gap",
            "description": "Conceptual understanding exists, but repetition through small tests is needed.",
            "training_task": "Add three tests for one module per commit.",
            "done_signal": "Test file exists and passes.",
        },
    ],
}


def blocker_map_path() -> Path:
    return state_root() / "skills" / "blocker_map.json"


def training_tasks_path() -> Path:
    return state_root() / "skills" / "training_tasks.jsonl"


def load_blocker_map() -> dict[str, Any]:
    return ensure_json(blocker_map_path(), DEFAULT_BLOCKER_MAP)


def skill_review(*, dry_run: bool = True) -> dict[str, Any]:
    blockers = load_blocker_map()["blockers"]
    tasks = []
    for blocker in blockers:
        task = {
            "training_task_id": make_id("task"),
            "state": "TRAINING_TASK_READY",
            "blocker_id": blocker["blocker_id"],
            "task": blocker["training_task"],
            "done_signal": blocker["done_signal"],
            "duration_minutes": 45,
            "created_at": now_iso(),
        }
        tasks.append(task)
        if not dry_run:
            append_jsonl(training_tasks_path(), task)
    return {"ok": True, "dry_run": dry_run, "tasks": tasks}
