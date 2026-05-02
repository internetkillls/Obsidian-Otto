from __future__ import annotations

from pathlib import Path
from typing import Any

from ..corridor import ensure_jsonl_row
from ..governance_utils import find_jsonl, public_result, state_root


THRESHOLDS = {
    "review_required": 0.55,
    "gold_candidate": 0.70,
    "training_candidate": 0.80,
}


def gold_readiness_path() -> Path:
    return state_root() / "enrichment" / "gold_readiness.jsonl"


def load_enriched_candidate(candidate_id: str) -> dict[str, Any] | None:
    return find_jsonl(state_root() / "enrichment" / "enriched_candidates.jsonl", "candidate_id", candidate_id)


def build_gold_readiness_payload(enriched_candidate: dict[str, Any]) -> dict[str, Any]:
    enrichment = dict(enriched_candidate.get("enrichment") or {})
    usefulness = float(enrichment.get("usefulness_score", 0.0))
    durability = float(enrichment.get("durability_score", 0.0))
    novelty = max(0.0, 1.0 - float(((enrichment.get("novelty_check") or {}).get("duplicate_score", 0.0))))
    safety = float(enrichment.get("safety_clearance", 0.0))
    overall = round((usefulness + durability + novelty + safety) / 4.0, 4)
    return {
        "candidate_id": enriched_candidate["candidate_id"],
        "gold_readiness": {
            "evidence_strength": 0.8 if (enrichment.get("council_lenses") or {}).get("evidence_auditor", {}).get("evidence_strength") == "medium" else 0.6,
            "insight_density": usefulness,
            "actionability": usefulness,
            "durability": durability,
            "novelty": round(novelty, 4),
            "contradiction_clearance": 1.0 if ((enrichment.get("contradiction_check") or {}).get("status") == "no_blocking_contradiction") else 0.0,
            "safety_clearance": safety,
            "training_value": round(float(enriched_candidate.get("vector_dimensions", {}).get("training_value", 0.0)), 4),
            "overall": overall,
        },
        "thresholds": THRESHOLDS,
    }


def evaluate_gold_readiness(candidate_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    enriched_candidate = load_enriched_candidate(candidate_id)
    if not enriched_candidate:
        return public_result(False, reason="candidate-id-not-found", candidate_id=candidate_id)
    payload = build_gold_readiness_payload(enriched_candidate)
    if not dry_run:
        ensure_jsonl_row(gold_readiness_path(), payload)
    return public_result(True, dry_run=dry_run, gold_readiness=payload)
