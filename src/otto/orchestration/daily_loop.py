from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, state_root
from ..state import now_iso, write_json
from .action_queue import write_action_queue
from .handoff import write_daily_handoff
from .human_loop_policy import load_daily_loop_policy, load_human_loop_policy


def daily_loop_last_path() -> Path:
    return state_root() / "runtime" / "daily_loop_last.json"


def daily_loop_runs_path() -> Path:
    return state_root() / "runtime" / "daily_loop_runs.jsonl"


def run_daily_loop(*, dry_run: bool = True) -> dict[str, Any]:
    policy = load_daily_loop_policy()
    human_policy = load_human_loop_policy()
    handoff = write_daily_handoff()
    actions = write_action_queue([handoff["handoff"]["smallest_meaningful_next_action"]])
    side_effects = {
        "vault_write": False,
        "qmd_reindex": False,
        "gold_promotion": False,
        "telegram_enabled": False,
        "openclaw_live_mutation": False,
    }
    result = {
        "ok": True,
        "state": "DL3_CANDIDATE_GENERATION_READY",
        "human_loop_state": "HL1_DAILY_HANDOFF_READY",
        "dry_run": dry_run,
        "generated_at": now_iso(),
        "policy_mode": policy.get("mode"),
        "role": human_policy.get("role"),
        "daily_handoff_path": handoff["path"],
        "action_queue_path": actions["path"],
        "side_effects": side_effects,
        "unsafe_side_effects": "blocked",
    }
    write_json(daily_loop_last_path(), result)
    append_jsonl(daily_loop_runs_path(), result)
    return result
