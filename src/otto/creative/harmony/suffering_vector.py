from __future__ import annotations


def derive_suffering_vector(text: str) -> dict[str, float]:
    lowered = text.lower()
    return {
        "longing": 0.84 if any(word in lowered for word in ["cinta", "love", "rindu"]) else 0.42,
        "tenderness": 0.61,
        "resentment": 0.58 if any(word in lowered for word in ["benci", "hate"]) else 0.22,
        "awe": 0.33,
        "fatigue": 0.49,
        "shame": 0.18,
        "hope": 0.52,
        "revolt": 0.27,
        "acceptance": 0.46,
    }
