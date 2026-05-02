from __future__ import annotations


def ladder_state(readiness: dict[str, object]) -> str:
    note_class = str(readiness.get("class") or "")
    if note_class == "mechanically_incomplete_but_semantically_valuable":
        return "G1_MECHANICALLY_REPAIRED"
    if note_class == "sensitive_needs_review":
        return "G4_REVIEW_READY"
    if note_class == "candidate_gold_after_enrichment":
        return "G3_ENRICHED_CANDIDATE"
    return "G2_SEMANTICALLY_NORMALIZED"
