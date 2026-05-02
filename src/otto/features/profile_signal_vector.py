from __future__ import annotations


def profile_signal_metrics(text: str) -> dict[str, float]:
    lowered = text.lower()
    weakness = min(0.12 + 0.14 * sum(token in lowered for token in ["weakness", "stuck", "confused", "overload"]), 0.95)
    sensitivity = min(0.1 + 0.2 * sum(token in lowered for token in ["adhd", "audhd", "bd", "bipolar", "diagnosis"]), 0.99)
    training_risk = min(0.15 + sensitivity * 0.7, 0.99)
    return {
        "weakness_relevance": weakness,
        "sensitivity_risk": sensitivity,
        "training_export_risk": training_risk,
    }
