from __future__ import annotations


def build_council_lenses(claim: str) -> dict[str, object]:
    lowered = claim.lower()
    abstract = "abstract" in lowered or "theory" in lowered
    return {
        "evidence_auditor": {
            "evidence_strength": "medium",
            "missing_evidence": ["source quality check"] if abstract else [],
        },
        "mentor": {
            "training_task": "Explain the idea as if entering a seminar room." if abstract else "Ground the note in one concrete example.",
        },
        "contrarian": {
            "weakness_point": "The idea may be overabstract if not grounded in a concrete example." if abstract else "The note may still be too thin for durable promotion.",
        },
    }
