from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, state_root
from ..state import now_iso, write_json


def raw_index_path() -> Path:
    return state_root() / "ingest" / "raw_index.jsonl"


def raw_payload_dir() -> Path:
    path = state_root() / "ingest" / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_raw_record(
    *,
    source_id: str,
    kind: str,
    uri: str,
    payload: dict[str, Any] | None = None,
    privacy: str = "private",
) -> dict[str, Any]:
    raw_id = make_id("raw")
    payload = payload or {"uri": uri}
    checksum = "sha256:" + hashlib.sha256(str(payload).encode("utf-8")).hexdigest()
    payload_ref = raw_payload_dir() / f"{raw_id}.json"
    write_json(payload_ref, payload)
    record = {
        "raw_id": raw_id,
        "state": "RAW",
        "source_id": source_id,
        "kind": kind,
        "captured_at": now_iso(),
        "uri": uri,
        "checksum": checksum,
        "privacy": privacy,
        "raw_payload_ref": str(payload_ref),
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
    }
    append_jsonl(raw_index_path(), record)
    return record
