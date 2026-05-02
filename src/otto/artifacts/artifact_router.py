from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, find_jsonl, make_id, read_jsonl, state_root
from ..state import now_iso
from .artifact_types import VALID_ARTIFACT_TYPES, load_artifact_type_policy
from .idea_capture import idea_inbox_path


def artifact_routes_path() -> Path:
    return state_root() / "artifacts" / "artifact_routes.jsonl"


def route_idea(idea: dict[str, Any]) -> dict[str, Any]:
    load_artifact_type_policy()
    text = str(idea.get("raw_text", "")).lower()
    possible = [
        {"type": "essay", "fit": 0.88, "reason": "Strong philosophical or technical concept."},
        {"type": "song", "fit": 0.81 if any(word in text for word in ["song", "music", "cinta", "chord"]) else 0.7, "reason": "Metaphor and emotional structure are usable."},
        {"type": "prose", "fit": 0.74, "reason": "Can become an anthology fragment."},
        {"type": "skill_drill", "fit": 0.66, "reason": "Can be turned into bounded practice."},
    ]
    route = {
        "route_id": make_id("route"),
        "idea_id": idea["idea_id"],
        "state": "ARTIFACT_ROUTED",
        "meaning_summary": "The idea can become a human artifact after review-gated production.",
        "possible_artifacts": [item for item in possible if item["type"] in VALID_ARTIFACT_TYPES],
        "recommended_route": {"primary": possible[0]["type"], "secondary": possible[1]["type"], "supporting": "skill_drill"},
        "review_required": True,
        "created_at": now_iso(),
    }
    append_jsonl(artifact_routes_path(), route)
    return route


def triage_ideas(*, dry_run: bool = True) -> dict[str, Any]:
    ideas = read_jsonl(idea_inbox_path())
    routes = [route_idea(idea) for idea in ideas[-3:]]
    return {"ok": True, "dry_run": dry_run, "routes": routes}


def load_route_for_idea(idea_id: str) -> dict[str, Any] | None:
    route = find_jsonl(artifact_routes_path(), "idea_id", idea_id)
    if route:
        return route
    idea = find_jsonl(idea_inbox_path(), "idea_id", idea_id)
    return route_idea(idea) if idea else None
