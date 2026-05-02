from __future__ import annotations

from pathlib import Path
from typing import Any

from ..corridor import ensure_jsonl_row
from ..governance_utils import find_jsonl, public_result, state_root
from .contradiction_check import contradiction_status
from .council_enrichment import build_council_lenses
from .novelty_check import novelty_report
from .usefulness_score import compute_usefulness


def enriched_candidates_path() -> Path:
    return state_root() / "enrichment" / "enriched_candidates.jsonl"


def contradiction_log_path() -> Path:
    return state_root() / "enrichment" / "contradiction_log.jsonl"


def novelty_log_path() -> Path:
    return state_root() / "enrichment" / "novelty_log.jsonl"


def enrich_candidate(candidate_id: str, *, dry_run: bool = True) -> dict[str, Any]:
    from .silver_to_candidate import candidate_insights_path

    candidate = find_jsonl(candidate_insights_path(), "candidate_id", candidate_id)
    if not candidate:
        return public_result(False, reason="candidate-id-not-found", candidate_id=candidate_id)
    dimensions = dict(candidate.get("vector_dimensions") or {})
    usefulness = compute_usefulness(dimensions)
    durability = round((float(dimensions.get("meaning_density", 0.0)) + float(dimensions.get("attention_reentry_value", 0.0))) / 2.0, 4)
    contradiction = contradiction_status(str(candidate.get("claim") or ""))
    novelty = novelty_report(str(candidate.get("claim") or ""))
    safety = 0.0 if float(dimensions.get("sensitivity_risk", 0.0)) > 0.8 else 1.0
    readiness = round((usefulness + durability + max(0.0, 1.0 - novelty["duplicate_score"]) + safety) / 4.0, 4)
    payload = {
        **candidate,
        "state": "ENRICHED_CANDIDATE",
        "enrichment": {
            "council_lenses": build_council_lenses(str(candidate.get("claim") or "")),
            "contradiction_check": contradiction,
            "novelty_check": novelty,
            "usefulness_score": usefulness,
            "durability_score": durability,
            "safety_clearance": safety,
            "gold_readiness_score": readiness,
        },
        "recommended_next_state": "REVIEW_REQUIRED",
    }
    if not dry_run:
        ensure_jsonl_row(enriched_candidates_path(), payload)
        ensure_jsonl_row(contradiction_log_path(), {"candidate_id": candidate_id, **contradiction})
        ensure_jsonl_row(novelty_log_path(), {"candidate_id": candidate_id, **novelty})
    return public_result(True, dry_run=dry_run, enriched_candidate=payload)
