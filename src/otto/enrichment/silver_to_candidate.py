from __future__ import annotations

from pathlib import Path
from typing import Any

from ..features.feature_vector import feature_vectors_path
from ..governance_utils import find_jsonl, make_id, public_result, read_jsonl, state_root
from ..corridor import ensure_jsonl_row


def candidate_insights_path() -> Path:
    return state_root() / "enrichment" / "candidate_insights.jsonl"


def load_feature_vector_by_event(event_id: str) -> dict[str, Any] | None:
    rows = [row for row in read_jsonl(feature_vectors_path()) if row.get("from_event_id") == event_id]
    return rows[-1] if rows else None


def create_candidate_from_event(event_id: str, *, dry_run: bool = True) -> dict[str, Any]:
    from ..normalize.source_normalizer import silver_events_path

    event = find_jsonl(silver_events_path(), "event_id", event_id)
    vector = load_feature_vector_by_event(event_id)
    if not event:
        return public_result(False, reason="event-id-not-found", event_id=event_id)
    if not vector:
        return public_result(False, reason="feature-vector-missing", event_id=event_id)
    text = str((event.get("content_unit") or {}).get("text") or "")
    dimensions = vector.get("dimensions") or {}
    kind = "research_onboarding_seed" if float(dimensions.get("artifact_affinity_paper", 0.0)) >= float(dimensions.get("artifact_affinity_song", 0.0)) else "song_seed"
    claim = (
        "This note is suitable for a paper onboarding pack about the concept it names."
        if kind == "research_onboarding_seed"
        else "This note contains a viable song seed if developed through chord-first translation."
    )
    payload = {
        "candidate_id": make_id("cand"),
        "state": "CANDIDATE_INSIGHT",
        "kind": kind,
        "claim": claim,
        "why_it_matters": "It can be routed into a durable artifact instead of remaining a raw fragment.",
        "source_vectors": [vector["feature_vector_id"]],
        "evidence_refs": [event_id],
        "review_required": True,
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "source_event": event,
        "vector_dimensions": dimensions,
        "raw_text": text,
    }
    if not dry_run:
        ensure_jsonl_row(candidate_insights_path(), payload)
    return public_result(True, dry_run=dry_run, candidate_insight=payload)
