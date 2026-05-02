from __future__ import annotations

from typing import Any


BLOCKED_QMD_STATES = {
    "RAW",
    "BRONZE",
    "SILVER_EVENT",
    "FEATURE_VECTOR",
    "CANDIDATE_INSIGHT",
    "ENRICHED_CANDIDATE",
    "G0_RAW_VALUE",
    "G1_MECHANICALLY_REPAIRED",
    "G2_SEMANTICALLY_NORMALIZED",
    "G3_ENRICHED_CANDIDATE",
    "G4_REVIEW_READY",
}


def qmd_state_allowed(state: str) -> bool:
    return state not in BLOCKED_QMD_STATES


def evaluate_gold_policy(item: dict[str, Any]) -> dict[str, Any]:
    state = str(item.get("state") or "")
    evidence_refs = list(item.get("evidence_refs") or [])
    review_id = item.get("review_id")
    contradiction_status = str(item.get("contradiction_status") or "")
    blocked: list[str] = []
    if not evidence_refs:
        blocked.append("gold_requires_evidence_refs")
    if not review_id:
        blocked.append("gold_requires_review_id")
    if contradiction_status == "blocking_contradiction":
        blocked.append("gold_has_blocking_contradiction")
    return {
        "ok": not blocked,
        "qmd_index_allowed": not blocked and qmd_state_allowed(state),
        "vault_writeback_allowed": not blocked,
        "blocked_reasons": blocked,
    }
