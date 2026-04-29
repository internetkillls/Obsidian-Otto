from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, state_root
from ..state import now_iso


def idea_inbox_path() -> Path:
    return state_root() / "artifacts" / "idea_inbox.jsonl"


def capture_idea(text: str, *, source_id: str = "manual") -> dict[str, Any]:
    idea = {
        "idea_id": make_id("idea"),
        "state": "IDEA_CAPTURED",
        "source_id": source_id,
        "raw_text": text,
        "captured_at": now_iso(),
        "evidence_refs": ["state/human/reflection_log.jsonl", "state/openclaw/context_pack_v1.json"],
        "privacy": "private",
        "initial_tags": ["creative", "meaning"],
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
    }
    append_jsonl(idea_inbox_path(), idea)
    return {"ok": True, "idea": idea}
