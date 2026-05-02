from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_DAILY_LOOP_POLICY: dict[str, Any] = {
    "version": 1,
    "mode": "dry_run",
    "default_behavior": {
        "write_to_vault": False,
        "auto_promote_to_gold": False,
        "auto_reindex_qmd": False,
        "auto_enable_telegram": False,
        "mutate_openclaw_live": False,
    },
    "inputs": {
        "runtime_smoke": True,
        "source_registry": True,
        "qmd_health": True,
        "context_pack": True,
        "review_queue_counts": True,
        "gold_memory_counts": True,
        "profile_policy": True,
        "council_policy": True,
        "single_owner_lock": True,
    },
    "outputs": {
        "daily_handoff": True,
        "action_queue": True,
        "writeback_candidate": False,
        "reflection_candidate": False,
        "review_queue_enqueue": False,
    },
    "human_meaning_policy": {
        "must_answer": [
            "what_changed",
            "why_it_matters",
            "active_weakness_or_support_lens",
            "smallest_meaningful_next_action",
            "what_not_to_do_yet",
            "what_needs_review_before_memory",
        ],
        "tone": "partner_mentor_not_clinician",
        "avoid": [
            "diagnostic_language",
            "identity_reduction",
            "overconfident_profile_claims",
            "unreviewed_council_conclusions",
        ],
    },
    "action_policy": {
        "max_suggested_actions": 3,
        "prefer_bounded_commits": True,
        "prefer_reentry_anchors": True,
        "avoid_new_integrations_when_runtime_unstable": True,
        "avoid_profile_automation_before_review_policy": True,
        "avoid_social_api_before_fixture_ingest": True,
    },
}


DEFAULT_HUMAN_LOOP_POLICY: dict[str, Any] = {
    "version": 1,
    "role": "partner_mentor",
    "not_roles": ["clinician", "therapist", "diagnostician"],
    "support_context_handling": {
        "AuDHD": {
            "use_as": "support_context",
            "allowed": ["reentry_anchor", "task_chunking", "attention_load_reduction", "context_switch_guardrail"],
            "blocked": ["diagnosis", "fixed_identity_claim", "pathology_label"],
        },
        "BD": {
            "use_as": "support_context",
            "allowed": ["scope_control", "activation_awareness", "sleep_boundary_reminder", "overextension_guardrail"],
            "blocked": ["episode_prediction_without_evidence", "medical_advice", "risk_labeling"],
        },
    },
    "council_use": {
        "allow_council_summary": True,
        "allow_unreviewed_council_as_memory": False,
        "allow_weakness_debate": True,
        "must_mark_as_candidate": True,
    },
    "mentor_use": {"allow_probe_generation": True, "allow_training_task_generation": True, "must_be_bounded": True},
}


DEFAULT_REFLECTION_POLICY: dict[str, Any] = {
    "version": 1,
    "default_behavior": {
        "auto_promote_to_gold": False,
        "auto_write_to_vault": False,
        "auto_reindex_qmd": False,
        "auto_expose_to_context": False,
    },
    "reflection_rules": {
        "requires_outcome": True,
        "requires_evidence": True,
        "requires_review_before_gold": True,
        "allow_no_meaningful_change": True,
    },
    "blocked_reflection_outputs_before_review": ["vault", "qmd", "openclaw_context", "profile_snapshot"],
    "meaning_questions": [
        "what_happened",
        "what_changed",
        "why_it_matters",
        "what_should_repeat",
        "what_should_not_repeat",
        "what_needs_review",
    ],
    "clinical_boundary": {"diagnostic_inference_allowed": False, "profile_claims_from_single_outcome_allowed": False},
}


def daily_loop_policy_path() -> Path:
    return state_root() / "human" / "daily_loop_policy.json"


def human_loop_policy_path() -> Path:
    return state_root() / "human" / "human_loop_policy.json"


def reflection_policy_path() -> Path:
    return state_root() / "human" / "reflection_policy.json"


def load_daily_loop_policy() -> dict[str, Any]:
    return ensure_json(daily_loop_policy_path(), DEFAULT_DAILY_LOOP_POLICY)


def load_human_loop_policy() -> dict[str, Any]:
    return ensure_json(human_loop_policy_path(), DEFAULT_HUMAN_LOOP_POLICY)


def load_reflection_policy() -> dict[str, Any]:
    return ensure_json(reflection_policy_path(), DEFAULT_REFLECTION_POLICY)
