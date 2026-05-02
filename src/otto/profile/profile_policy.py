from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_PROFILE_POLICY: dict[str, Any] = {
    "version": 1,
    "mode": "functional_self_model",
    "diagnostic_inference_allowed": False,
    "clinical_labels_allowed": "declared_or_verified_only",
    "conditions": {
        "AuDHD": {
            "status": "user_declared_context",
            "use_for": [
                "attention_support",
                "reentry_design",
                "overload_prevention",
                "communication_preference",
                "environmental_friction_mapping",
            ],
            "do_not_use_for": ["diagnosis", "identity reduction", "automatic limitation claims"],
        },
        "BD": {
            "status": "user_declared_context",
            "use_for": [
                "energy_rhythm_awareness",
                "sleep_and_overextension_guardrails",
                "scope_control",
                "activation_deactivation_tracking",
            ],
            "do_not_use_for": [
                "diagnosis",
                "episode prediction without explicit evidence",
                "medication or clinical advice",
                "automatic risk labeling",
            ],
        },
    },
    "allowed_dimensions": [
        "attention_rhythm",
        "context_switching_cost",
        "reentry_needs",
        "overload_threshold",
        "activation_rhythm",
        "recovery_levers",
        "social_energy",
        "communication_preference",
        "execution_friction",
        "novelty_vs_structure_balance",
        "meaning_motivation",
        "economic_pressure_response",
    ],
    "blocked_outputs_before_review": ["vault", "qmd", "openclaw_context", "profile_snapshot"],
    "review_required_for": [
        "profile_claim",
        "psychometric_hypothesis",
        "sociometric_hypothesis",
        "AuDHD_related_support_claim",
        "BD_related_support_claim",
        "weakness_taxonomy",
        "council_synthesis",
    ],
}


DEFAULT_FUNCTIONAL_DIMENSIONS: dict[str, Any] = {
    "version": 1,
    "dimensions": {
        "attention_rhythm": {
            "description": "How attention starts, drifts, fragments, and returns.",
            "evidence_types": ["session_log", "vault_activity", "task_history", "self_report"],
            "safe_outputs": ["support_hint", "ritual_prompt", "context_pack_hint"],
        },
        "context_switching_cost": {
            "description": "Cost of leaving and re-entering a cognitive thread.",
            "evidence_types": ["handoff_gap", "abandoned_task", "reentry_note"],
            "safe_outputs": ["reentry_anchor", "stop_rule", "daily_action"],
        },
        "reentry_needs": {
            "description": "External anchors needed before resuming complex work.",
            "evidence_types": ["handoff", "selected_action", "self_report"],
            "safe_outputs": ["handoff_prompt", "resume_anchor"],
        },
        "overload_threshold": {
            "description": "Signals that scope is exceeding usable working capacity.",
            "evidence_types": ["task_burst", "missed_done_signal", "self_report"],
            "safe_outputs": ["scope_guardrail", "stop_rule"],
        },
        "activation_rhythm": {
            "description": "Pattern of high-energy initiation and follow-through friction.",
            "evidence_types": ["task_bursts", "late_night_activity", "completion_ratio"],
            "safe_outputs": ["scope_guardrail", "bounded_action", "cooldown_prompt"],
        },
        "recovery_levers": {
            "description": "What helps regain clarity, continuity, and agency.",
            "evidence_types": ["successful_reentry", "completed_task", "self_report"],
            "safe_outputs": ["ritual", "support_style", "mentor_prompt"],
        },
        "social_energy": {"description": "How social load changes execution capacity.", "evidence_types": []},
        "communication_preference": {"description": "Preferred help format and pacing.", "evidence_types": []},
        "execution_friction": {"description": "Where intent fails to become done signal.", "evidence_types": []},
        "novelty_vs_structure_balance": {"description": "How structure can support without flattening novelty.", "evidence_types": []},
    },
}


def profile_policy_path() -> Path:
    return state_root() / "profile" / "profile_policy.json"


def functional_dimensions_path() -> Path:
    return state_root() / "profile" / "functional_dimensions.json"


def load_profile_policy() -> dict[str, Any]:
    return ensure_json(profile_policy_path(), DEFAULT_PROFILE_POLICY)


def load_functional_dimensions() -> dict[str, Any]:
    return ensure_json(functional_dimensions_path(), DEFAULT_FUNCTIONAL_DIMENSIONS)


def evaluate_profile_claim(item: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not item.get("evidence_refs"):
        reasons.append("profile_hypothesis_requires_evidence")
    if item.get("state") != "REVIEWED_PROFILE_CLAIM":
        reasons.append("candidate_profile_claim_cannot_export_before_review")
    return {
        "qmd_index_allowed": not reasons,
        "vault_writeback_allowed": not reasons,
        "openclaw_context_allowed": not reasons,
        "blocked_outputs_before_review": [] if not reasons else ["vault", "qmd", "openclaw_context"],
        "reasons": reasons,
    }


def profile_policy_health() -> dict[str, Any]:
    policy = load_profile_policy()
    dimensions = load_functional_dimensions()
    claim = evaluate_profile_claim({"state": "PROFILE_HYPOTHESIS", "evidence_refs": ["fp_1"]})
    return {
        "profile_policy": "green" if policy.get("diagnostic_inference_allowed") is False else "red",
        "functional_dimensions": "green" if "attention_rhythm" in dimensions.get("dimensions", {}) else "red",
        "diagnostic_inference_allowed": False,
        "unreviewed_profile_claim_not_qmd_indexable": not claim["qmd_index_allowed"],
    }
