from __future__ import annotations

from typing import Any

from ..governance_utils import make_id


def build_functional_pattern_candidate(dimension: str, observation: str, evidence_refs: list[str]) -> dict[str, Any]:
    return {
        "pattern_id": make_id("fp"),
        "state": "FUNCTIONAL_SIGNAL",
        "dimension": dimension,
        "observation": observation,
        "evidence_refs": evidence_refs,
        "confidence": 0.68,
        "not_diagnostic": True,
    }


def build_profile_hypothesis(pattern: dict[str, Any], claim: str, support_context: list[str] | None = None) -> dict[str, Any]:
    return {
        "hypothesis_id": make_id("ph"),
        "state": "PROFILE_HYPOTHESIS",
        "dimension": pattern.get("dimension"),
        "claim": claim,
        "support_context": support_context or [],
        "confidence": 0.72,
        "evidence_refs": [pattern.get("pattern_id")],
        "review_required": True,
        "blocked_outputs_before_review": ["vault", "qmd", "openclaw_context"],
    }
