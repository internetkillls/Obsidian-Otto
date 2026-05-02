from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, find_jsonl, make_id, public_result, state_root
from ..state import now_iso
from .human_loop_policy import load_reflection_policy
from .outcome_capture import outcome_log_path


def reflection_log_path() -> Path:
    return state_root() / "human" / "reflection_log.jsonl"


def create_reflection_candidate(outcome_id: str) -> dict[str, Any]:
    outcome = find_jsonl(outcome_log_path(), "outcome_id", outcome_id)
    if not outcome:
        return public_result(False, reason="reflection_requires_outcome", outcome_id=outcome_id)
    policy = load_reflection_policy()
    reflection = {
        "reflection_id": make_id("refl"),
        "state": "REFLECTION_CANDIDATE_CREATED",
        "from_outcome_id": outcome_id,
        "kind": "human_loop_reflection",
        "claim": "Action-outcome closure is safer than adding another integration before review.",
        "why_it_matters": "It makes Otto learn from actual work rather than infer identity from raw data.",
        "confidence": 0.82,
        "evidence_refs": [outcome_id, "state/human/daily_handoff.json", "state/openclaw/context_pack_v1.json"],
        "recommended_review_action": "approve_as_handoff_memory",
        "blocked_outputs_before_review": policy["blocked_reflection_outputs_before_review"],
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "review_required": True,
        "created_at": now_iso(),
    }
    append_jsonl(reflection_log_path(), reflection)
    return public_result(True, reflection=reflection)
