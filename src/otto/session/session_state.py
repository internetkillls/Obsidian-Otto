from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import state_root
from ..state import write_json


def session_state_path() -> Path:
    return state_root() / "session" / "session_state.json"


def active_memory_lens_path() -> Path:
    return state_root() / "session" / "active_memory_lens.json"


def ritual_prompt_path() -> Path:
    return state_root() / "session" / "ritual_prompt.json"


def write_session_state() -> dict[str, Any]:
    session = {
        "version": 1,
        "state": "SESSION_SUMMARY_READY",
        "mode": "bounded_system_build",
        "active_project": "Obsidian-Otto",
        "current_phase": "HL2_OUTCOME_REFLECTION_LOOP_READY",
        "recommended_surface": "daily_handoff",
        "attention_support": {
            "recommended_chunk_size": "one_bounded_commit",
            "reentry_anchor_required": True,
            "avoid_unbounded_branching": True,
        },
        "energy_scope_guardrail": {
            "avoid_scope_expansion": True,
            "stop_rule": "Stop after dry-run loop passes tests.",
        },
    }
    write_json(session_state_path(), session)
    return {"ok": True, "path": str(session_state_path()), "session_state": session}


def write_active_memory_lens() -> dict[str, Any]:
    lens = {
        "version": 1,
        "active_lenses": [
            "qmd_bridge_ready",
            "openclaw_shadow_ready",
            "profile_council_governance",
            "human_loop_next",
            "creative_forge_next",
        ],
        "excluded_lenses_for_now": [
            "instagram_production_ingest",
            "telegram_canary",
            "prediction_model_training",
        ],
    }
    write_json(active_memory_lens_path(), lens)
    return {"ok": True, "path": str(active_memory_lens_path()), "active_memory_lens": lens}


def write_ritual_prompt() -> dict[str, Any]:
    ritual = {
        "version": 1,
        "ritual_id": "ritual_daily_reentry",
        "prompt": "Start with: what changed, why it matters, one bounded next action.",
        "done_signal": "A handoff or action outcome is captured.",
        "avoid": ["open-ended refactor", "new integration before loop closure"],
    }
    write_json(ritual_prompt_path(), ritual)
    return {"ok": True, "path": str(ritual_prompt_path()), "ritual_prompt": ritual}
