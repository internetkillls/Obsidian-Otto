from __future__ import annotations


def classify_risk(*, note_class: str, text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["adhd", "audhd", "bd", "bipolar", "diagnosis", "psychometric", "weakness", "profile"]):
        return "R3_REVIEW_REQUIRED"
    if note_class in {"sensitive_needs_review", "blocked_by_policy"}:
        return "R3_REVIEW_REQUIRED"
    if "duplicate" in lowered or "merge" in lowered:
        return "R2_REVIEW_RECOMMENDED"
    if note_class == "mechanically_incomplete_but_semantically_valuable":
        return "R1_LOW_RISK_SEMANTIC"
    return "R0_SAFE_MECHANICAL"
