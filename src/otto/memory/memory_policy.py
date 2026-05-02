from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_MEMORY_POLICY: dict[str, Any] = {
    "version": 1,
    "default_rules": {
        "raw_qmd_index": False,
        "raw_vault_writeback": False,
        "candidate_qmd_index": False,
        "candidate_vault_writeback": False,
        "review_required_for_gold": True,
        "evidence_required_for_claim": True,
    },
    "privacy_rules": {
        "public": {"qmd_index_allowed": True, "vault_writeback_allowed": True},
        "private": {"qmd_index_allowed": True, "vault_writeback_allowed": True},
        "private_reviewed": {"qmd_index_allowed": True, "vault_writeback_allowed": True},
        "sensitive": {"qmd_index_allowed": False, "vault_writeback_allowed": False},
    },
    "kind_rules": {
        "social_raw": {"qmd_index_allowed": False, "vault_writeback_allowed": False, "review_required": True},
        "profile_claim_candidate": {
            "qmd_index_allowed": False,
            "vault_writeback_allowed": False,
            "review_required": True,
        },
        "handoff_note": {"qmd_index_allowed": True, "vault_writeback_allowed": True, "review_required": True},
        "gold_memory": {"qmd_index_allowed": True, "vault_writeback_allowed": True, "review_required": False},
    },
}


def memory_policy_path() -> Path:
    return state_root() / "memory" / "memory_policy.json"


def load_memory_policy() -> dict[str, Any]:
    return ensure_json(memory_policy_path(), DEFAULT_MEMORY_POLICY)


def evaluate_memory_export(item: dict[str, Any], *, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or load_memory_policy()
    state = str(item.get("state") or "").upper()
    kind = str(item.get("kind") or "")
    privacy = str(item.get("privacy") or "private")
    reasons: list[str] = []

    if state == "RAW":
        reasons.extend(["raw_items_cannot_export_to_qmd", "raw_items_cannot_export_to_vault"])
    if state == "CANDIDATE":
        reasons.extend(["candidate_requires_review_before_qmd", "candidate_requires_review_before_vault"])
        if policy["default_rules"]["evidence_required_for_claim"] and not item.get("evidence_refs"):
            reasons.append("candidate_requires_evidence")
    if privacy == "sensitive" and state not in {"REVIEWED", "GOLD"}:
        reasons.append("sensitive_item_requires_review_or_gold")
    if kind == "profile_claim_candidate" and not item.get("evidence_refs"):
        reasons.append("profile_claim_requires_evidence")
    if state == "GOLD" and not (item.get("reviewed_at") or item.get("approved_at") or item.get("from_review_id")):
        reasons.append("gold_requires_reviewed_or_approved_state")

    allowed = not reasons and state in {"REVIEWED", "GOLD"}
    return {
        "qmd_index_allowed": allowed,
        "vault_writeback_allowed": allowed,
        "allowed_outputs": ["qmd", "vault", "openclaw_context"] if allowed else [],
        "blocked_outputs": [] if allowed else ["qmd", "vault"],
        "reasons": reasons,
    }


def memory_policy_health() -> dict[str, Any]:
    policy = load_memory_policy()
    raw = evaluate_memory_export({"state": "RAW", "kind": "social_raw", "privacy": "sensitive"})
    candidate = evaluate_memory_export({"state": "CANDIDATE", "kind": "handoff_note", "evidence_refs": ["x"]})
    gold = evaluate_memory_export(
        {"state": "GOLD", "kind": "gold_memory", "reviewed_at": "reviewed", "privacy": "private_reviewed"}
    )
    return {
        "policy": "green" if policy.get("version") == 1 else "red",
        "raw_store": "green",
        "promotion_rules": "green" if candidate["blocked_outputs"] and gold["qmd_index_allowed"] else "red",
        "unsafe_exports_blocked": "green" if not raw["qmd_index_allowed"] and not raw["vault_writeback_allowed"] else "red",
    }
