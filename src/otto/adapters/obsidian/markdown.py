from __future__ import annotations

from typing import Any

from ...state import now_iso
from .frontmatter import render_frontmatter


def render_note(item: dict[str, Any]) -> str:
    writeback_id = item.get("writeback_id") or item.get("gold_id") or item.get("candidate_id") or "unknown"
    otto_type = item.get("kind") or "handoff_note"
    status = str(item.get("status") or item.get("otto_state") or item.get("state") or "reviewed").lower()
    title = item.get("title") or "Otto Handoff"
    source_refs = item.get("source_refs") or item.get("evidence_refs") or []
    fields = {
        "otto_type": otto_type,
        "otto_state": status,
        "otto_writeback_id": writeback_id,
        "source_refs": source_refs,
        "privacy": item.get("privacy", "private_reviewed"),
        "generated_at": item.get("generated_at") or now_iso(),
        "qmd_reindex_recommended": bool(item.get("qmd_reindex_recommended", True)),
    }
    body = item.get("body") or item.get("summary") or "Otto bridge state is ready for reviewed memory writeback."
    return f"{render_frontmatter(fields)}\n# {title}\n\n{body.strip()}\n"
