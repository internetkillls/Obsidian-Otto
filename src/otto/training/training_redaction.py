from __future__ import annotations


def contains_secret_like_text(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ["password", "secret", "token", "api_key"])
