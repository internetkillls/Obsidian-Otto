from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, make_id, state_root
from ..state import now_iso


DEFAULT_SANITY_POLICY: dict[str, Any] = {
    "version": 1,
    "mode": "fail_closed",
    "default_behavior": {
        "auto_repair": False,
        "auto_delete": False,
        "auto_promote": False,
        "auto_qmd_reindex": False,
        "auto_vault_write": False,
        "quarantine_ambiguous": True,
        "require_repair_plan": True,
    },
    "required_record_fields": [
        "id",
        "state",
        "kind",
        "created_at",
        "privacy",
        "evidence_refs",
        "qmd_index_allowed",
        "vault_writeback_allowed",
    ],
    "allowed_unknowns": {"source_id": False, "privacy": False, "state": False, "kind": False, "owner": False},
    "staleness_days": {
        "candidate": 14,
        "pending_review": 30,
        "action_selected": 2,
        "song_skeleton_candidate": 14,
        "paper_onboarding_candidate": 21,
    },
    "fail_conditions": [
        "gold_without_review",
        "vault_write_without_reviewed_or_gold",
        "qmd_index_raw_or_candidate",
        "candidate_profile_in_context_pack",
        "unreviewed_council_in_context_pack",
        "missing_source_registry_entry",
        "dangling_evidence_ref",
        "duplicate_active_owner",
        "success_without_expected_output",
    ],
    "warning_conditions": [
        "stale_candidate",
        "low_evidence_candidate",
        "duplicate_semantic_candidate",
        "too_many_pending_reviews",
        "heartbeat_generated_zero_candidates_with_reason",
    ],
}


DEFAULT_INVARIANT_REGISTRY: dict[str, Any] = {
    "version": 1,
    "invariants": [
        {
            "id": "INV_GOLD_REQUIRES_REVIEW",
            "severity": "fail",
            "rule": "GoldMemory must reference approved review_id or explicit reviewed state.",
        },
        {
            "id": "INV_RAW_NEVER_QMD",
            "severity": "fail",
            "rule": "RAW, BRONZE, social_raw, raw_song_seed, raw_idea must have qmd_index_allowed=false.",
        },
        {
            "id": "INV_CANDIDATE_NEVER_VAULT",
            "severity": "fail",
            "rule": "Candidate items cannot be written to Vault before review/gold.",
        },
        {
            "id": "INV_PROFILE_REVIEW_REQUIRED",
            "severity": "fail",
            "rule": "Profile/council/psychometric/support claims must not surface as truth before review.",
        },
        {
            "id": "INV_ONE_LIVE_TELEGRAM_OWNER",
            "severity": "fail",
            "rule": "Only one OpenClaw runtime may own Telegram.",
        },
        {
            "id": "INV_HEARTBEAT_EXPLAINS_NO_OUTPUT",
            "severity": "fail",
            "rule": "Heartbeat commands that generate no candidate must include no_output_reason.",
        },
        {
            "id": "INV_EVIDENCE_REFS_RESOLVE",
            "severity": "fail",
            "rule": "Every evidence_ref must resolve to an existing state file item or file path.",
        },
        {
            "id": "INV_CONTEXT_PACK_NO_RAW_CONTENT",
            "severity": "fail",
            "rule": "Context pack may include counts/summaries but not raw private candidate content.",
        },
    ],
}


ID_FIELDS = [
    "id",
    "raw_id",
    "bronze_id",
    "event_id",
    "candidate_id",
    "review_id",
    "decision_id",
    "gold_id",
    "writeback_id",
    "idea_id",
    "route_id",
    "brief_id",
    "song_seed_id",
    "atom_id",
    "song_skeleton_id",
    "pack_id",
    "quiz_id",
    "block_id",
    "action_id",
    "outcome_id",
    "reflection_id",
    "statement_id",
]


def sanity_policy_path() -> Path:
    return state_root() / "sanity" / "sanity_policy.json"


def invariant_registry_path() -> Path:
    return state_root() / "sanity" / "invariant_registry.json"


def load_sanity_policy() -> dict[str, Any]:
    return ensure_json(sanity_policy_path(), DEFAULT_SANITY_POLICY)


def load_invariant_registry() -> dict[str, Any]:
    return ensure_json(invariant_registry_path(), DEFAULT_INVARIANT_REGISTRY)


def record_id(record: dict[str, Any]) -> str | None:
    for field in ID_FIELDS:
        value = record.get(field)
        if value:
            return str(value)
    return None


def record_kind(record: dict[str, Any], fallback: str = "unknown") -> str:
    return str(record.get("kind") or record.get("item_type") or record.get("artifact_type") or fallback)


def canonical_state(record: dict[str, Any]) -> str:
    return str(record.get("state") or "").upper()


def is_candidate_state(state: str) -> bool:
    return "CANDIDATE" in state or state in {"WRITE_CANDIDATE", "PENDING_REVIEW", "PROPOSED"}


def issue(
    *,
    prefix: str,
    severity: str,
    problem: str,
    record: dict[str, Any] | None = None,
    record_kind_name: str | None = None,
    recommended_action: str,
    **extra: Any,
) -> dict[str, Any]:
    record = record or {}
    return {
        "issue_id": make_id(prefix),
        "severity": severity,
        "record_id": record_id(record),
        "record_kind": record_kind_name or record_kind(record),
        "state": record.get("state"),
        "problem": problem,
        "recommended_action": recommended_action,
        "auto_repair_allowed": False,
        "created_at": now_iso(),
        **extra,
    }


def result_shape(
    *,
    ok: bool,
    state_changed: bool = False,
    created_ids: list[str] | None = None,
    updated_ids: list[str] | None = None,
    warnings: list[Any] | None = None,
    blockers: list[Any] | None = None,
    quarantined: list[Any] | None = None,
    next_required_action: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "state_changed": state_changed,
        "created_ids": created_ids or [],
        "updated_ids": updated_ids or [],
        "warnings": warnings or [],
        "blockers": blockers or [],
        "quarantined": quarantined or [],
        "next_required_action": next_required_action,
        **extra,
    }


def evaluate_record_invariants(record: dict[str, Any]) -> list[dict[str, Any]]:
    state = canonical_state(record)
    kind = record_kind(record).lower()
    problems: list[dict[str, Any]] = []
    rawish = state in {"RAW", "BRONZE"} or kind in {"social_raw", "raw_song_seed", "raw_idea", "idea_captured"}
    if rawish and record.get("qmd_index_allowed") is True:
        problems.append(
            issue(
                prefix="inv",
                severity="fail",
                problem="raw_or_bronze_record_is_qmd_indexable",
                record=record,
                recommended_action="set_qmd_index_allowed_false_or_quarantine",
                invariant_id="INV_RAW_NEVER_QMD",
            )
        )
    if is_candidate_state(state) and record.get("vault_writeback_allowed") is True:
        problems.append(
            issue(
                prefix="inv",
                severity="fail",
                problem="candidate_record_is_vault_writeable_before_review",
                record=record,
                recommended_action="block_vault_writeback_until_review_or_gold",
                invariant_id="INV_CANDIDATE_NEVER_VAULT",
            )
        )
    if state == "GOLD" and not (record.get("from_review_id") or record.get("reviewed_at") or record.get("approved_at")):
        problems.append(
            issue(
                prefix="inv",
                severity="fail",
                problem="gold_record_missing_review_reference",
                record=record,
                recommended_action="attach_review_id_or_demote_to_review_required",
                invariant_id="INV_GOLD_REQUIRES_REVIEW",
            )
        )
    profileish = kind in {
        "profile_claim",
        "profile_claim_candidate",
        "psychometric_hypothesis",
        "sociometric_hypothesis",
        "council_synthesis",
    }
    if profileish and state not in {"REVIEWED_PROFILE_CLAIM", "GOLD", "APPROVED"}:
        problems.append(
            issue(
                prefix="inv",
                severity="fail",
                problem="profile_or_council_claim_unreviewed",
                record=record,
                recommended_action="enqueue_review_or_keep_candidate_out_of_context",
                invariant_id="INV_PROFILE_REVIEW_REQUIRED",
            )
        )
    return problems
