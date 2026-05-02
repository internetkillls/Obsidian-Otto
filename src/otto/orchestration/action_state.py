from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import public_result, state_root
from ..state import now_iso, write_json
from .action_queue import load_action


def selected_action_path() -> Path:
    return state_root() / "human" / "selected_action.json"


def select_action(action_id: str) -> dict[str, Any]:
    action = load_action(action_id)
    if not action:
        return public_result(False, reason="action-id-not-found", action_id=action_id)
    selected = {
        **action,
        "state": "SELECTED",
        "selected_at": now_iso(),
        "selected_by": "joshu",
        "scope_guardrail": {
            "max_scope": "one bounded commit",
            "stop_rule": "Stop after tests pass and no unsafe side effects are confirmed.",
            "avoid": ["Instagram production OAuth", "Telegram canary", "profile automation"],
        },
    }
    write_json(selected_action_path(), selected)
    return public_result(True, selected_action=selected)
