from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, public_result, state_root
from ..state import now_iso, read_json
from .action_state import selected_action_path


def outcome_log_path() -> Path:
    return state_root() / "human" / "outcome_log.jsonl"


def capture_outcome(action_id: str, *, result: str, note: str = "") -> dict[str, Any]:
    selected = read_json(selected_action_path(), default={}) or {}
    if selected.get("action_id") != action_id or selected.get("state") != "SELECTED":
        return public_result(False, reason="outcome_requires_selected_action", action_id=action_id)
    outcome = {
        "outcome_id": make_id("out"),
        "action_id": action_id,
        "state": "OUTCOME_CAPTURED",
        "result": result,
        "what_happened": note or selected.get("expected_outcome", ""),
        "actual_outputs": ["state/human/daily_handoff.json", "state/human/action_queue.jsonl"],
        "side_effects": {
            "vault_write": False,
            "qmd_reindex": False,
            "gold_promotion": False,
            "telegram_enabled": False,
            "openclaw_live_mutation": False,
        },
        "human_value": "Otto can connect action to outcome before making memory durable.",
        "evidence_refs": ["state/human/selected_action.json", "state/runtime/daily_loop_last.json"],
        "created_at": now_iso(),
    }
    append_jsonl(outcome_log_path(), outcome)
    return public_result(True, outcome=outcome)
