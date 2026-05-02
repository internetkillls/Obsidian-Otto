from __future__ import annotations

from pathlib import Path

from ..corridor import ensure_jsonl_row
from ..governance_utils import read_jsonl, state_root


def patch_ledger_path() -> Path:
    return state_root() / "gold_rehab" / "patch_ledger.jsonl"


def record_patch(row: dict[str, object]) -> dict[str, object]:
    return ensure_jsonl_row(patch_ledger_path(), row)


def load_patch(patch_id: str) -> dict[str, object] | None:
    rows = [row for row in read_jsonl(patch_ledger_path()) if str(row.get("patch_id")) == patch_id]
    return rows[-1] if rows else None
