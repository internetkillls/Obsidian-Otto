from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, find_jsonl, make_id, public_result, read_jsonl, state_root
from ..state import now_iso, write_json
from .promotion import candidate_claims_path
from .review_policy import load_review_policy


def review_queue_path() -> Path:
    return state_root() / "memory" / "review_queue.jsonl"


def reviewed_path() -> Path:
    return state_root() / "memory" / "reviewed.jsonl"


def rejected_path() -> Path:
    return state_root() / "memory" / "rejected.jsonl"


def needs_more_evidence_path() -> Path:
    return state_root() / "memory" / "needs_more_evidence.jsonl"


def review_audit_path() -> Path:
    return state_root() / "memory" / "review_audit.jsonl"


def load_review(review_id: str) -> dict[str, Any] | None:
    return find_jsonl(review_queue_path(), "review_id", review_id)


def enqueue_candidate(candidate: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    evidence = candidate.get("evidence_refs") or []
    if not evidence:
        return public_result(False, reason="candidate_without_evidence_blocked", candidate_id=candidate.get("candidate_id"))
    kind = str(candidate.get("kind", "handoff_note"))
    risk = "handoff" if kind == "handoff_note" else kind
    policy = load_review_policy()
    risk_rule = policy["risk_rules"].get(risk, policy["risk_rules"]["handoff"])
    min_count = int(risk_rule.get("min_evidence_count", 1))
    if len(evidence) < min_count:
        return public_result(False, reason="needs_more_evidence", min_evidence_count=min_count)
    review = {
        "review_id": make_id("rev"),
        "state": "PENDING_REVIEW",
        "item_type": "candidate_memory",
        "item_id": candidate["candidate_id"],
        "kind": kind,
        "title": candidate.get("title", ""),
        "body": candidate.get("body", ""),
        "risk": risk,
        "privacy": candidate.get("privacy", "private_reviewed"),
        "evidence_refs": evidence,
        "evidence_count": len(evidence),
        "recommended_decision": "approve",
        "blocked_outputs_before_review": ["vault", "qmd"],
        "allowed_outputs_before_review": ["review_queue"],
        "created_at": now_iso(),
    }
    if not dry_run:
        append_jsonl(review_queue_path(), review)
        append_jsonl(review_audit_path(), {"event": "enqueue", **review})
    return public_result(True, enqueue_ok=True, review=review, dry_run=dry_run)


def enqueue_candidate_by_id(candidate_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    candidate = find_jsonl(candidate_claims_path(), "candidate_id", candidate_id)
    if not candidate:
        return public_result(False, reason="candidate-id-not-found", candidate_id=candidate_id)
    return enqueue_candidate(candidate, dry_run=dry_run)


def decide_review(review_id: str, decision: str, *, note: str = "", dry_run: bool = True) -> dict[str, Any]:
    review = load_review(review_id)
    if not review:
        return public_result(False, reason="review-id-not-found", review_id=review_id)
    normalized = decision.lower().replace("-", "_")
    state_map = {
        "approved": "APPROVED",
        "rejected": "REJECTED",
        "needs_more_evidence": "NEEDS_MORE_EVIDENCE",
    }
    state = state_map[normalized]
    decision_item = {
        "decision_id": make_id("rdec"),
        "review_id": review_id,
        "decision": normalized,
        "state": state,
        "reviewed_by": "joshu",
        "reviewed_at": now_iso(),
        "notes": note,
        "allowed_outputs": ["vault", "qmd", "context_pack"] if normalized == "approved" else [],
    }
    if not dry_run:
        path = reviewed_path() if normalized == "approved" else rejected_path()
        if normalized == "needs_more_evidence":
            path = needs_more_evidence_path()
        append_jsonl(path, {**review, **decision_item})
        append_jsonl(review_audit_path(), {"event": normalized, **decision_item})
    return public_result(True, dry_run=dry_run, review=review, decision=decision_item)


def review_counts() -> dict[str, int]:
    queue = read_jsonl(review_queue_path())
    return {
        "pending_review_count": len([row for row in queue if row.get("state") == "PENDING_REVIEW"]),
        "approved_count": len(read_jsonl(reviewed_path())),
        "rejected_count": len(read_jsonl(rejected_path())),
        "needs_more_evidence_count": len(read_jsonl(needs_more_evidence_path())),
    }


def write_review_state() -> dict[str, Any]:
    counts = review_counts()
    result = {"ok": True, "review_queue": counts, "updated_at": now_iso()}
    write_json(state_root() / "memory" / "review_state_last.json", result)
    return result
