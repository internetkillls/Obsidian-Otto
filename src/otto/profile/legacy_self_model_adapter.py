from __future__ import annotations

from typing import Any

from .functional_patterns import build_profile_hypothesis


def adapt_legacy_self_model(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for dimension, value in (payload.get("observed_patterns") or {}).items():
        pattern = {
            "pattern_id": f"legacy:{dimension}",
            "dimension": str(dimension),
        }
        candidates.append(
            build_profile_hypothesis(
                pattern,
                claim=str(value),
                support_context=[],
            )
        )
    return candidates
