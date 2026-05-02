from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_AUTONOMOUS_GENERATION_POLICY: dict[str, Any] = {
    "version": 1,
    "mode": "review_gated_autonomy",
    "enabled": False,
    "default_behavior": {
        "auto_publish": False,
        "auto_write_to_vault": False,
        "auto_qmd_index_raw": False,
        "auto_promote_to_gold": False,
        "requires_review": True,
    },
    "cadence": {
        "song_skeleton_every_hours": 4,
        "paper_onboarding_every_hours_min": 4,
        "paper_onboarding_every_hours_max": 6,
        "blocker_experiment_daily": True,
        "memento_due_every_hours": 8,
    },
    "seed_sources": {
        "notes": {
            "enabled": True,
            "sources": [
                "qmd_search",
                "vault_recent_notes",
                "otto_realm_brain",
                "handoff",
                "dream_summary",
                "kairos_strategy",
                "unfinished_fragments",
            ],
        },
        "steering": {
            "enabled": True,
            "sources": [
                "state/autonomy/steering_vector.json",
                "SOUL.md",
                "HEARTBEAT.md",
                "state/openclaw/soul/otto_soul_v2.json",
                "user_declared_preferences",
            ],
        },
    },
    "song_generation": {
        "derive_hash_anchor_from_notes": True,
        "derive_at_atoms_from_notes": True,
        "chord_first": True,
        "one_atom_max_one_chord_cycle": True,
        "existential_censorship": True,
        "minimum_rhythm_routes": 4,
        "midi_spec_required": True,
        "visual_inspo_query_required": True,
    },
    "paper_generation": {
        "derive_topic_from_notes": True,
        "onboarding_before_critique": True,
        "source_priority": [
            "university_press_books",
            "top_journal_articles",
            "field_handbooks",
            "canonical_debates",
            "recent_review_articles",
        ],
        "must_explain_school_as_social_room": True,
    },
    "safety": {
        "no_diagnostic_claims": True,
        "audhd_bd_support_context_only": True,
        "no_youtube_download": True,
        "no_raw_vault_dump": True,
    },
}


def autonomy_state_dir() -> Path:
    return state_root() / "autonomy"


def autonomous_generation_policy_path() -> Path:
    return autonomy_state_dir() / "autonomous_generation_policy.json"


def load_autonomous_generation_policy() -> dict[str, Any]:
    return ensure_json(autonomous_generation_policy_path(), DEFAULT_AUTONOMOUS_GENERATION_POLICY)


def autonomous_policy_health() -> dict[str, Any]:
    existed = autonomous_generation_policy_path().exists()
    policy = load_autonomous_generation_policy()
    behavior = policy.get("default_behavior") or {}
    safety = policy.get("safety") or {}
    checks = {
        "policy_exists": existed,
        "requires_review": behavior.get("requires_review") is True,
        "auto_publish_false": behavior.get("auto_publish") is False,
        "auto_write_to_vault_false": behavior.get("auto_write_to_vault") is False,
        "auto_qmd_index_raw_false": behavior.get("auto_qmd_index_raw") is False,
        "auto_promote_to_gold_false": behavior.get("auto_promote_to_gold") is False,
        "no_raw_vault_dump": safety.get("no_raw_vault_dump") is True,
    }
    return {"ok": all(checks.values()), "checks": checks, "policy": policy}
