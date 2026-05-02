from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, public_result, state_root
from ..state import now_iso
from .policy import load_memento_policy


def blocks_path() -> Path:
    return state_root() / "memento" / "blocks.jsonl"


def ingest_gold(gold: dict[str, Any]) -> dict[str, Any]:
    policy = load_memento_policy()["memento_policy"]
    if gold.get("state") not in policy["quizworthy_states"]:
        return public_result(False, reason="memento_rejects_non_gold_or_unreviewed", state=gold.get("state"))
    block = {
        "block_id": make_id("memblk"),
        "state": "MEMENTO_BLOCK_READY",
        "source_id": gold.get("gold_id") or gold.get("id"),
        "title": gold.get("title", "Gold block"),
        "quiz_types": policy["quiz_types"],
        "created_at": now_iso(),
    }
    append_jsonl(blocks_path(), block)
    return public_result(True, block=block)
