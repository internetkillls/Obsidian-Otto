from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_MEMENTO_POLICY: dict[str, Any] = {
    "version": 1,
    "memento_policy": {
        "enabled": True,
        "quizworthy_states": [
            "GOLD",
            "REVIEWED_ONBOARDING_PACK",
            "PROMOTED_SONG_PRINCIPLE",
            "APPROVED_SKILL_BLOCKER",
            "REVIEWED_COUNCIL_STATEMENT",
        ],
        "blocked_states": ["RAW", "CANDIDATE", "UNREVIEWED_PROFILE_HYPOTHESIS", "RAW_SOCIAL"],
        "quiz_types": ["recall", "application", "analogy", "use_in_new_artifact", "spot_the_crack", "finish_the_pattern"],
        "incentive_policy": {
            "personalized_encouragement": True,
            "diagnostic_language": False,
            "reward_action": "unlock_next_artifact_prompt",
        },
        "schedule": {"engine": "sm2_like", "daily_budget": 10, "review_windows": ["morning", "evening"]},
    },
}


def memento_policy_path() -> Path:
    return state_root() / "memento" / "memento_policy.json"


def load_memento_policy() -> dict[str, Any]:
    return ensure_json(memento_policy_path(), DEFAULT_MEMENTO_POLICY)
