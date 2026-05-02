from __future__ import annotations

from ..state import now_iso


def normalize_observed_at(observed_at: str | None) -> tuple[str, float]:
    if observed_at and observed_at.strip():
        return observed_at.strip(), 0.9
    return now_iso(), 0.5
