from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_SKILL_HIERARCHY: dict[str, Any] = {
    "version": 1,
    "domains": {
        "audio_engineering": {
            "status": "strong_existing_domain",
            "skills": {
                "mix_translation": {"level": "advanced", "blocker": None},
                "midi_composition_systematization": {
                    "level": "intermediate",
                    "blocker": "needs repeatable generative workflow",
                },
                "lyric_prosody": {"level": "developing", "blocker": "needs structured revision loop"},
            },
        },
        "music_production": {
            "status": "strong_existing_domain",
            "skills": {
                "arrangement_completion": {
                    "level": "intermediate",
                    "blocker": "fragment-to-finished pipeline",
                },
                "release_packaging": {"level": "developing", "blocker": "publication decision fatigue"},
            },
        },
        "philosophy_research": {
            "status": "trained_domain",
            "skills": {
                "conceptual_analysis": {"level": "advanced", "blocker": None},
                "public_essay_translation": {"level": "intermediate", "blocker": "needs audience framing"},
            },
        },
        "engineering": {
            "status": "interest_and_growth_domain",
            "skills": {
                "modular_architecture": {"level": "developing", "blocker": "needs implementation reps"},
                "testing_and_ci": {"level": "developing", "blocker": "needs small repeated tasks"},
                "data_pipeline_design": {"level": "intermediate", "blocker": "needs applied projects"},
            },
        },
    },
}


def skill_hierarchy_path() -> Path:
    return state_root() / "skills" / "skill_hierarchy.json"


def load_skill_hierarchy() -> dict[str, Any]:
    return ensure_json(skill_hierarchy_path(), DEFAULT_SKILL_HIERARCHY)
