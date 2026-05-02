from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, find_jsonl, make_id, public_result, read_jsonl, state_root
from ..state import now_iso
from .memory_policy import evaluate_memory_export
from .review_queue import reviewed_path


def gold_index_path() -> Path:
    return state_root() / "memory" / "gold_index.jsonl"


def promote_review_to_gold(review_id: str, *, dry_run: bool = True) -> dict[str, Any]:
    reviewed = find_jsonl(reviewed_path(), "review_id", review_id)
    if not reviewed:
        return public_result(False, reason="approved-review-not-found", review_id=review_id)
    gold = {
        "gold_id": make_id("gold"),
        "state": "GOLD",
        "from_review_id": review_id,
        "from_candidate_id": reviewed.get("item_id"),
        "kind": reviewed.get("kind", "handoff_note"),
        "title": reviewed.get("title", "Reviewed memory"),
        "body": reviewed.get("body", ""),
        "privacy": reviewed.get("privacy", "private_reviewed"),
        "evidence_refs": reviewed.get("evidence_refs", []),
        "qmd_index_allowed": True,
        "vault_writeback_allowed": True,
        "context_pack_allowed": True,
        "created_at": now_iso(),
    }
    export = evaluate_memory_export({**gold, "reviewed_at": reviewed.get("reviewed_at")})
    gold.update(export)
    if not dry_run:
        append_jsonl(gold_index_path(), gold)
    return public_result(True, dry_run=dry_run, gold=gold)


def load_gold(gold_id: str) -> dict[str, Any] | None:
    return find_jsonl(gold_index_path(), "gold_id", gold_id)


def gold_counts() -> dict[str, int]:
    rows = read_jsonl(gold_index_path())
    return {"gold_count": len(rows)}
