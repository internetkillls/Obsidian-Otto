from __future__ import annotations


def compute_usefulness(dimensions: dict[str, float]) -> float:
    keys = [
        "meaning_density",
        "artifact_affinity_paper",
        "artifact_affinity_prose",
        "research_onboarding_fit",
        "attention_reentry_value",
    ]
    values = [float(dimensions.get(key, 0.0)) for key in keys]
    return round(sum(values) / max(len(values), 1), 4)
