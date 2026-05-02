from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, find_jsonl, make_id, public_result, state_root
from ..state import now_iso
from .memory_policy import evaluate_memory_export


def candidate_claims_path() -> Path:
    return state_root() / "memory" / "candidate_claims.jsonl"


def promotion_queue_path() -> Path:
    return state_root() / "memory" / "promotion_queue.jsonl"


def contradiction_log_path() -> Path:
    return state_root() / "memory" / "contradiction_log.jsonl"


def create_candidate(kind: str = "handoff", *, dry_run: bool = True) -> dict[str, Any]:
    candidate = {
        "candidate_id": make_id("cand"),
        "state": "CANDIDATE",
        "kind": "handoff_note" if kind == "handoff" else kind,
        "title": "Bridge checkpoint completed",
        "body": "WSL shadow gateway, QMD retrieval, context pack, and single-owner lock are green.",
        "confidence": 0.93,
        "evidence_refs": [
            "state/runtime/smoke_last.json",
            "state/openclaw/gateway_probe.json",
            "state/qmd/qmd_last_health.json",
        ],
        "privacy": "private_reviewed",
        "review_required": True,
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "created_at": now_iso(),
    }
    append_jsonl(candidate_claims_path(), candidate)
    return public_result(True, candidate=candidate, dry_run=dry_run)


def load_candidate(candidate_id: str) -> dict[str, Any] | None:
    return find_jsonl(candidate_claims_path(), "candidate_id", candidate_id)


def dry_run_promotion(candidate: dict[str, Any]) -> dict[str, Any]:
    export = evaluate_memory_export(candidate)
    reasons = list(export["reasons"])
    if "candidate_requires_review_before_qmd" not in reasons:
        reasons.append("candidate requires review before gold")
    result = {
        "candidate_id": candidate.get("candidate_id"),
        "can_promote": False,
        "next_state": "REVIEW_REQUIRED",
        "blocked_outputs": ["qmd", "vault"],
        "reasons": reasons or ["candidate requires review before gold", "vault writeback requires reviewed/gold"],
    }
    append_jsonl(promotion_queue_path(), {**result, "state": "REVIEW_REQUIRED", "created_at": now_iso()})
    return result


def promote_candidate(candidate_id: str, *, dry_run: bool = True) -> dict[str, Any]:
    candidate = load_candidate(candidate_id)
    if not candidate:
        return public_result(False, reason="candidate-id-not-found", candidate_id=candidate_id)
    result = dry_run_promotion(candidate)
    return public_result(True, dry_run=dry_run, promotion=result)
