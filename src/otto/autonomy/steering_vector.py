from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root
from ..state import now_iso, write_json


DEFAULT_STEERING_VECTOR: dict[str, Any] = {
    "version": 1,
    "vector_id": "stv_user_declared_creative_steering_v1",
    "source": "user_steering",
    "updated_at": None,
    "identity": {
        "audio_engineer": True,
        "music_producer": True,
        "philosophy_trained_researcher": True,
        "engineering_interested": True,
    },
    "creative_priorities": [
        "song_skeleton",
        "midi",
        "lyrics",
        "prose",
        "research_onboarding",
        "blocker_experiment",
        "memento",
    ],
    "song_rules": {
        "chord_first": True,
        "hash_is_context_anchor": True,
        "at_is_existential_atom": True,
        "one_atom_max_one_chord_cycle": True,
        "explicit_meaning_to_phenomena": True,
        "minimum_rhythm_routes": 4,
        "midi_human_velocity_timing": True,
    },
    "research_rules": {
        "onboarding_before_critique": True,
        "school_community_as_social_room": True,
        "top_journal_university_press_priority": True,
        "critical_mode_later": "crack_research_reversing_simon",
    },
    "cadence": {
        "song_skeleton_every_hours": 4,
        "paper_onboarding_every_hours_min": 4,
        "paper_onboarding_every_hours_max": 6,
        "blocker_experiment_daily": True,
        "memento_due_every_hours": 8,
    },
}


def steering_vector_path() -> Path:
    return state_root() / "autonomy" / "steering_vector.json"


def load_steering_vector(*, write: bool = True) -> dict[str, Any]:
    if write:
        vector = ensure_json(steering_vector_path(), {**DEFAULT_STEERING_VECTOR, "updated_at": now_iso()})
    elif steering_vector_path().exists():
        vector = ensure_json(steering_vector_path(), DEFAULT_STEERING_VECTOR)
    else:
        vector = {**DEFAULT_STEERING_VECTOR, "updated_at": now_iso()}
    return vector


def write_steering_vector() -> dict[str, Any]:
    vector = {**load_steering_vector(write=False), "updated_at": now_iso()}
    write_json(steering_vector_path(), vector)
    return {"ok": True, "path": str(steering_vector_path()), "steering_vector": vector}


def steering_vector_health(vector: dict[str, Any] | None = None) -> dict[str, Any]:
    vector = vector or load_steering_vector()
    song_rules = vector.get("song_rules") or {}
    research_rules = vector.get("research_rules") or {}
    checks = {
        "chord_first": song_rules.get("chord_first") is True,
        "hash_anchor_rule": song_rules.get("hash_is_context_anchor") is True,
        "at_atom_rule": song_rules.get("at_is_existential_atom") is True,
        "one_atom_one_cycle": song_rules.get("one_atom_max_one_chord_cycle") is True,
        "minimum_four_rhythm_routes": int(song_rules.get("minimum_rhythm_routes") or 0) >= 4,
        "midi_humanize": song_rules.get("midi_human_velocity_timing") is True,
        "onboarding_before_critique": research_rules.get("onboarding_before_critique") is True,
        "school_as_social_room": research_rules.get("school_community_as_social_room") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "steering_vector": vector}

