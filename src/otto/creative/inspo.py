from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_VISUAL_INSPO_POLICY: dict[str, Any] = {
    "version": 1,
    "visual_inspo_policy": {
        "enabled": True,
        "sources": ["e-flux", "artforum", "moma", "tate", "mousse magazine", "frieze", "kunstkritikk", "ubuweb metadata only"],
        "output_type": "query_and_reference_pointer",
        "download_image_by_default": False,
        "required_for": ["song_skeleton", "prose_draft"],
        "fields": ["visual_query", "why_this_represents_the_text", "source_url", "artist", "work_title", "license_or_usage_note"],
    },
}


def visual_inspo_policy_path() -> Path:
    return state_root() / "creative" / "visual_inspo_policy.json"


def load_visual_inspo_policy() -> dict[str, Any]:
    return ensure_json(visual_inspo_policy_path(), DEFAULT_VISUAL_INSPO_POLICY)


def build_visual_inspo_query(artifact_id: str) -> dict[str, Any]:
    policy = load_visual_inspo_policy()["visual_inspo_policy"]
    return {
        "ok": True,
        "artifact_id": artifact_id,
        "visual_query": "contemporary art domestic trace grief smell clothing absence e-flux",
        "why": "The text centers on residue, absence, and time as body-memory.",
        "source_preference": policy["sources"],
        "attachment_status": "reference_pointer_only",
        "download_image": False,
    }
