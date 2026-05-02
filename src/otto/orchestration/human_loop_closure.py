from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import public_result, state_root
from ..state import now_iso, write_json
from .action_state import select_action
from .outcome_capture import capture_outcome
from .reflection import create_reflection_candidate


def loop_closure_last_path() -> Path:
    return state_root() / "human" / "loop_closure_last.json"


def close_human_loop(action_id: str, *, dry_run: bool = True) -> dict[str, Any]:
    selected = select_action(action_id)
    if not selected.get("ok"):
        return selected
    outcome = capture_outcome(action_id, result="completed", note="Dry-run closure captured.")
    if not outcome.get("ok"):
        return outcome
    reflection = create_reflection_candidate(outcome["outcome"]["outcome_id"])
    result = public_result(
        True,
        dry_run=dry_run,
        state="HL2_OUTCOME_REFLECTION_LOOP_READY",
        selected_action=selected["selected_action"],
        outcome=outcome["outcome"],
        reflection=reflection.get("reflection"),
        unsafe_side_effects="blocked",
        updated_at=now_iso(),
    )
    write_json(loop_closure_last_path(), result)
    return result
