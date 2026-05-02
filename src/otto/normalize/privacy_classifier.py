from __future__ import annotations


def classify_privacy(*, source_id: str, text: str = "", reviewed: bool = False) -> str:
    lowered = f"{source_id} {text}".lower()
    if any(token in lowered for token in ["secret", "password", "token"]):
        return "sensitive"
    if reviewed:
        return "private_reviewed"
    return "private"
