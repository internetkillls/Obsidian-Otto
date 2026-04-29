from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_REVIEW_POLICY: dict[str, Any] = {
    "version": 1,
    "default_rules": {
        "manual_review_required": True,
        "evidence_required": True,
        "min_evidence_count_for_gold": 1,
        "allow_auto_approval": False,
        "allow_candidate_to_context_pack": False,
        "allow_candidate_to_qmd": False,
        "allow_candidate_to_vault": False,
    },
    "risk_rules": {
        "handoff": {
            "review_required": True,
            "min_evidence_count": 1,
            "allowed_after_approval": ["vault", "qmd", "context_pack"],
        },
        "runtime_checkpoint": {
            "review_required": False,
            "min_evidence_count": 1,
            "allowed_after_approval": ["context_pack"],
        },
        "profile_claim": {
            "review_required": True,
            "min_evidence_count": 2,
            "allowed_after_approval": ["vault", "qmd", "context_pack"],
        },
        "psychometric_hypothesis": {
            "review_required": True,
            "min_evidence_count": 3,
            "allowed_after_approval": ["vault"],
            "blocked_before_review": ["qmd", "context_pack", "vault"],
        },
        "social_summary": {
            "review_required": True,
            "min_evidence_count": 2,
            "allowed_after_approval": ["vault", "qmd"],
            "raw_export_forbidden": True,
        },
    },
    "terminal_rules": {
        "rejected_items_exportable": False,
        "needs_more_evidence_exportable": False,
        "deferred_items_exportable": False,
    },
}


def review_policy_path() -> Path:
    return state_root() / "memory" / "review_policy.json"


def load_review_policy() -> dict[str, Any]:
    return ensure_json(review_policy_path(), DEFAULT_REVIEW_POLICY)
