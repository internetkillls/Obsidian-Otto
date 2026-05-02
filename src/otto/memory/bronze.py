from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, state_root


def bronze_index_path() -> Path:
    return state_root() / "memory" / "bronze_index.jsonl"


def promote_raw_to_bronze(raw: dict[str, Any]) -> dict[str, Any]:
    bronze = {
        "bronze_id": make_id("brz"),
        "state": "BRONZE",
        "raw_id": raw["raw_id"],
        "source_id": raw.get("source_id"),
        "kind": raw.get("kind"),
        "captured_at": raw.get("captured_at"),
        "evidence_refs": [raw["raw_id"]],
        "dedupe_key": raw.get("checksum"),
        "privacy": raw.get("privacy", "private"),
    }
    append_jsonl(bronze_index_path(), bronze)
    return bronze
