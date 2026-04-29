from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, state_root
from ..state import now_iso


def release_candidates_path() -> Path:
    return state_root() / "artifacts" / "release_candidates.jsonl"


def create_release_candidate(artifact_id: str, *, reviewed: bool = False) -> dict[str, Any]:
    candidate = {
        "release_candidate_id": make_id("rel"),
        "state": "RELEASE_CANDIDATE",
        "artifact_id": artifact_id,
        "review_required": True,
        "publication_allowed": bool(reviewed),
        "blocked_reason": None if reviewed else "review_required_before_publication",
        "created_at": now_iso(),
    }
    append_jsonl(release_candidates_path(), candidate)
    return candidate
