from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, state_root
from ..state import now_iso
from .artifact_router import load_route_for_idea
from .artifact_types import load_artifact_type_policy


def production_briefs_path() -> Path:
    return state_root() / "artifacts" / "production_briefs.jsonl"


def create_production_brief(idea_id: str, *, artifact_type: str | None = None) -> dict[str, Any]:
    policy = load_artifact_type_policy()
    route = load_route_for_idea(idea_id)
    if not route:
        return {"ok": False, "reason": "idea-id-not-found", "idea_id": idea_id}
    artifact_type = artifact_type or route["recommended_route"]["primary"]
    required = policy["artifact_types"][artifact_type]["required_parts"]
    brief = {
        "brief_id": make_id("brief"),
        "state": "PRODUCTION_BRIEF_CREATED",
        "artifact_type": artifact_type,
        "title_working": "Continuity Prosthesis",
        "intent": "Turn a raw idea into a meaningful artifact without auto-publication.",
        "audience": "people who build systems to survive complexity",
        "mood": ["intimate", "mechanical", "late-night", "hopeful but tired"],
        "required_parts": required,
        "music_spec": {
            "tempo": 82,
            "meter": "4/4",
            "mode": "D dorian or A minor",
            "sections": ["intro", "verse", "pre", "chorus", "bridge", "outro"],
        },
        "lyric_spec": {
            "voice": "first-person but not confessional cliche",
            "key_images": ["lantern", "tunnel", "archive", "wire", "return"],
            "avoid": ["therapy cliche", "AI buzzwords", "generic self-help"],
        },
        "done_signal": "A typed production spec exists.",
        "evidence_refs": [route["route_id"]],
        "review_required": True,
        "created_at": now_iso(),
    }
    append_jsonl(production_briefs_path(), brief)
    return {"ok": True, "brief": brief}
