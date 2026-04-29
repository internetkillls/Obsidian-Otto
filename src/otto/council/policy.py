from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_COUNCIL_POLICY: dict[str, Any] = {
    "version": 1,
    "mode": "single_model_multi_lens_council",
    "clinical_boundary": {
        "diagnosis_allowed": False,
        "therapy_claims_allowed": False,
        "clinical_advice_allowed": False,
        "allowed_role_names": [
            "mentor",
            "thought_partner",
            "stabilizer",
            "business_partner",
            "evidence_auditor",
            "meaning_maker",
            "grounding_partner",
        ],
        "deprecated_role_names": ["therapist"],
    },
    "lenses": [
        {"id": "evidence_auditor", "question": "What evidence supports this claim, and what evidence is missing?"},
        {"id": "neurodivergent_support", "question": "What support design reduces friction without reducing agency?"},
        {"id": "mood_energy_stabilizer", "question": "What scope guardrail reduces overextension and protects recovery?"},
        {"id": "mentor", "question": "What probe or bounded training task would improve this pattern?"},
        {"id": "contrarian", "question": "What is the most likely false assumption or weakness point?"},
        {"id": "morpheus_meaning", "question": "What does this pattern mean in lived experience and continuity?"},
        {"id": "execution_partner", "question": "What is the smallest next action with real-world leverage?"},
    ],
    "synthesis_rules": {
        "must_include": [
            "weakness_point",
            "support_need",
            "stop_rule",
            "mentor_probe_or_task",
            "smallest_next_action",
            "confidence",
            "review_required",
        ],
        "blocked_outputs_before_review": ["qmd", "vault", "profile_snapshot"],
    },
}


def council_policy_path() -> Path:
    return state_root() / "council" / "council_policy.json"


def load_council_policy() -> dict[str, Any]:
    return ensure_json(council_policy_path(), DEFAULT_COUNCIL_POLICY)


def normalize_role_name(role: str) -> str:
    return "stabilizer" if role == "therapist" else role


def council_policy_health() -> dict[str, Any]:
    policy = load_council_policy()
    roles = policy.get("clinical_boundary", {})
    return {
        "council_policy": "green" if roles.get("diagnosis_allowed") is False else "red",
        "therapist_role_mapped_to_stabilizer": normalize_role_name("therapist") == "stabilizer",
        "lens_count": len(policy.get("lenses", [])),
    }
