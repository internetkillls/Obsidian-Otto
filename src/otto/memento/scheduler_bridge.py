from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, read_jsonl, state_root
from ..state import now_iso
from .quizworthy import blocks_path


def quiz_queue_path() -> Path:
    return state_root() / "memento" / "quiz_queue.jsonl"


def build_due_queue() -> dict[str, Any]:
    blocks = read_jsonl(blocks_path())
    quizzes = []
    for block in blocks[-10:]:
        quiz = {
            "quiz_id": make_id("quiz"),
            "state": "QUIZ_DUE",
            "block_id": block.get("block_id"),
            "quiz_type": "recall",
            "prompt": f"Recall the core move from {block.get('title', 'this block')}.",
            "created_at": now_iso(),
        }
        append_jsonl(quiz_queue_path(), quiz)
        quizzes.append(quiz)
    return {"ok": True, "quiz_count": len(quizzes), "quizzes": quizzes}
