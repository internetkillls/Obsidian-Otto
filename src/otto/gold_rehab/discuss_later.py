from __future__ import annotations

from pathlib import Path

from ..corridor import ensure_jsonl_row
from ..governance_utils import public_result, read_jsonl, state_root


def discuss_later_path() -> Path:
    return state_root() / "gold_rehab" / "discuss_later.jsonl"


def queue_discuss_later(item: dict[str, object]) -> dict[str, object]:
    return ensure_jsonl_row(discuss_later_path(), item)


def discuss_later_summary() -> dict[str, object]:
    rows = read_jsonl(discuss_later_path())
    return public_result(True, count=len(rows), items=rows[-10:])
