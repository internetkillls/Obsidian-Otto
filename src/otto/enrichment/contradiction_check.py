from __future__ import annotations


def contradiction_status(claim: str) -> dict[str, str]:
    lowered = claim.lower()
    if "not " in lowered and "always" in lowered:
        return {"status": "review_possible_contradiction"}
    return {"status": "no_blocking_contradiction"}
