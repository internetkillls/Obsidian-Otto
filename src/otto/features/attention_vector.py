from __future__ import annotations


def attention_metrics(text: str) -> dict[str, float]:
    lowered = text.lower()
    reentry = 0.25 + 0.15 * sum(token in lowered for token in ["next", "resume", "anchor", "continue"])
    memento = 0.2 + 0.15 * sum(token in lowered for token in ["remember", "recall", "quiz", "flashcard"])
    return {
        "attention_reentry_value": min(reentry, 0.95),
        "memento_value": min(memento, 0.95),
    }
