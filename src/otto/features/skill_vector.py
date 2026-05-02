from __future__ import annotations


def skill_gap_relevance(text: str) -> float:
    lowered = text.lower()
    hits = sum(token in lowered for token in ["skill", "learn", "practice", "blocker", "drill", "study"])
    return min(0.2 + hits * 0.12, 0.95)
