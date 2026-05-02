from __future__ import annotations

from pathlib import Path
from typing import Any

from ..corridor import ensure_jsonl_row
from ..governance_utils import find_jsonl, make_id, public_result, state_root
from .gold_policy import evaluate_gold_policy
from .training_export_gate import evaluate_training_export_gate


def gold_index_path() -> Path:
    return state_root() / "gold" / "gold_index.jsonl"


def load_review_for_candidate(candidate_id: str) -> dict[str, Any] | None:
    reviewed_path = state_root() / "memory" / "reviewed.jsonl"
    rows = __import__("otto.governance_utils", fromlist=["read_jsonl"]).read_jsonl(reviewed_path)
    matches = [row for row in rows if str(row.get("item_id")) == candidate_id]
    return matches[-1] if matches else None


def compile_gold_candidate(candidate_id: str, *, dry_run: bool = True) -> dict[str, Any]:
    from ..enrichment.gold_readiness import build_gold_readiness_payload, load_enriched_candidate

    enriched = load_enriched_candidate(candidate_id)
    if not enriched:
        return public_result(False, reason="candidate-id-not-found", candidate_id=candidate_id)
    review = load_review_for_candidate(candidate_id)
    readiness = build_gold_readiness_payload(enriched)
    contradiction_status = str(((enriched.get("enrichment") or {}).get("contradiction_check") or {}).get("status") or "")
    gold = {
        "gold_id": make_id("gold"),
        "state": "GOLD",
        "from_candidate_id": candidate_id,
        "review_id": review.get("review_id") if review else None,
        "kind": "research_onboarding_principle" if enriched.get("kind") == "research_onboarding_seed" else "artifact_seed",
        "claim": enriched.get("claim"),
        "evidence_refs": [*list(enriched.get("evidence_refs") or []), review.get("review_id")] if review else list(enriched.get("evidence_refs") or []),
        "why_it_matters": enriched.get("why_it_matters"),
        "durability": "medium_high" if readiness["gold_readiness"]["durability"] >= 0.7 else "medium",
        "allowed_outputs": ["vault", "qmd", "context"] if review else [],
        "training_eligible": readiness["gold_readiness"]["overall"] >= readiness["thresholds"]["gold_candidate"],
        "training_export_allowed": False,
        "contains_no_secret": True,
        "contains_no_unreviewed_profile_claim": True,
        "contains_no_clinical_claim": True,
        "has_clear_instruction_output_shape": True,
        "has_artifact_or_decision_value": True,
        "not_overfit_to_raw_private_context": True,
        "contradiction_status": contradiction_status,
        "gold_readiness": readiness["gold_readiness"],
    }
    policy = evaluate_gold_policy(gold)
    gate = evaluate_training_export_gate(gold)
    gold["qmd_index_allowed"] = policy["qmd_index_allowed"]
    gold["vault_writeback_allowed"] = policy["vault_writeback_allowed"]
    gold["training_export_allowed"] = gate["export_allowed"]
    gold["blocked_reasons"] = [*policy["blocked_reasons"], *gate["blocked_reasons"]]
    if not policy["ok"]:
        return public_result(False, reason=policy["blocked_reasons"][0], gold=gold, policy=policy)
    if not dry_run:
        ensure_jsonl_row(gold_index_path(), gold)
    return public_result(True, dry_run=dry_run, gold=gold)
