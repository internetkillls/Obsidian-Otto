from __future__ import annotations


def suffering_vector_intensity(text: str) -> float:
    lowered = text.lower()
    hits = sum(token in lowered for token in ["suffer", "stuck", "pressure", "confused", "overload", "pain"])
    return min(0.15 + hits * 0.14, 0.95)
