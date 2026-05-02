from __future__ import annotations


def research_onboarding_fit(text: str, entities: list[str]) -> float:
    lowered = text.lower()
    score = 0.3
    score += 0.2 * sum(token in lowered for token in ["research", "school", "seminar", "framework", "method"])
    score += 0.05 * len([entity for entity in entities if entity.startswith("concept:") or entity.startswith("method:")])
    return min(score, 0.99)
