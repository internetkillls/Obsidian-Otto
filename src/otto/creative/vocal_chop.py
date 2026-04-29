from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_VOCAL_CHOP_POLICY: dict[str, Any] = {
    "version": 1,
    "vocal_chop_policy": {
        "youtube_download_allowed": False,
        "youtube_reference_search_allowed": True,
        "licensed_sample_allowed": True,
        "own_recording_allowed": True,
        "creative_commons_allowed_if_verified": True,
        "release_candidate_requires_clearance": True,
        "outputs": ["query", "reference_url", "license_status", "clearance_required"],
    },
}


def vocal_chop_policy_path() -> Path:
    return state_root() / "creative" / "vocal_chop_policy.json"


def load_vocal_chop_policy() -> dict[str, Any]:
    return ensure_json(vocal_chop_policy_path(), DEFAULT_VOCAL_CHOP_POLICY)


def vocal_chop_query(topic: str = "intimate vocal chop") -> dict[str, Any]:
    policy = load_vocal_chop_policy()["vocal_chop_policy"]
    return {
        "ok": True,
        "query": f"{topic} licensed sample creative commons verified",
        "youtube_download_allowed": policy["youtube_download_allowed"],
        "clearance_required": True,
    }
