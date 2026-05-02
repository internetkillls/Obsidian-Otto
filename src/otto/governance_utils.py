from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import load_paths
from .state import now_iso, read_json, write_json


def state_root() -> Path:
    return load_paths().state_root


def ensure_json(path: Path, default: Any) -> Any:
    if not path.exists():
        write_json(path, default)
        return default
    return read_json(path, default=default)


def ensure_jsonl(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def append_jsonl(path: Path, item: dict[str, Any]) -> Path:
    ensure_jsonl(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def find_jsonl(path: Path, key: str, value: str) -> dict[str, Any] | None:
    for row in reversed(read_jsonl(path)):
        if str(row.get(key)) == value:
            return row
    return None


def make_id(prefix: str) -> str:
    stamp = re.sub(r"[^0-9]", "", now_iso())[:14]
    return f"{prefix}_{stamp}"


def count_jsonl(path: Path, *, state: str | None = None) -> int:
    rows = read_jsonl(path)
    if state is None:
        return len(rows)
    return len([row for row in rows if row.get("state") == state])


def public_result(ok: bool, **fields: Any) -> dict[str, Any]:
    return {"ok": ok, **fields}
