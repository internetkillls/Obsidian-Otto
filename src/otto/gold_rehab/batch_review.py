from __future__ import annotations

from pathlib import Path

from ..corridor import ensure_jsonl_row
from ..governance_utils import make_id, public_result, read_jsonl, state_root


def batch_review_queue_path() -> Path:
    return state_root() / "gold_rehab" / "batch_review_queue.jsonl"


def build_batch_review_queue() -> dict[str, object]:
    from .review_needed import review_needed_path

    items = read_jsonl(review_needed_path())
    batch = {
        "batch_id": make_id("gbatch"),
        "state": "REVIEW_BATCH",
        "item_count": len(items),
        "review_ids": [item.get("review_id") for item in items],
    }
    ensure_jsonl_row(batch_review_queue_path(), batch)
    return public_result(True, batch=batch)
