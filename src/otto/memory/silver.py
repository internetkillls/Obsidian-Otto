from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, state_root
from ..state import now_iso


def silver_events_path() -> Path:
    return state_root() / "memory" / "silver_events.jsonl"


def normalize_bronze_to_event(bronze: dict[str, Any], *, text: str = "") -> dict[str, Any]:
    event = {
        "event_id": make_id("evt"),
        "state": "SILVER",
        "source_id": bronze.get("source_id"),
        "kind": "note_activity" if bronze.get("kind") == "vault_note" else bronze.get("kind", "memory_event"),
        "ts": bronze.get("captured_at") or now_iso(),
        "actor": "self",
        "text": text,
        "entities": [],
        "relations": [],
        "evidence_refs": [bronze["bronze_id"]],
        "privacy": bronze.get("privacy", "private"),
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
    }
    append_jsonl(silver_events_path(), event)
    return event
