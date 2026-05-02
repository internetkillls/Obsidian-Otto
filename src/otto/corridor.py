from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import yaml

from .adapters.obsidian.frontmatter import render_frontmatter
from .governance_utils import append_jsonl, read_jsonl
from .state import now_iso, write_json


RISK_LEVELS = {
    "R0_SAFE_MECHANICAL": 0,
    "R1_LOW_RISK_SEMANTIC": 1,
    "R2_REVIEW_RECOMMENDED": 2,
    "R3_REVIEW_REQUIRED": 3,
}


def to_plain_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    raise TypeError(f"unsupported-value-type:{type(value)!r}")


def ensure_jsonl_row(path: Path, row: Any) -> dict[str, Any]:
    payload = to_plain_dict(row)
    append_jsonl(path, payload)
    return payload


def rewrite_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")
    return path


def sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, bool]:
    if not text.startswith("---\n"):
        return {}, text, False
    marker = "\n---\n"
    end = text.find(marker, 4)
    if end == -1:
        return {}, text, False
    raw = text[4:end]
    body = text[end + len(marker) :]
    loaded = yaml.safe_load(raw) or {}
    return (loaded if isinstance(loaded, dict) else {}), body, True


def merge_frontmatter(base: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in additions.items():
        if key not in merged:
            merged[key] = value
            continue
        if isinstance(merged[key], dict) and isinstance(value, dict):
            nested = dict(merged[key])
            for nested_key, nested_value in value.items():
                if nested_key not in nested:
                    nested[nested_key] = nested_value
            merged[key] = nested
    return merged


def render_markdown(frontmatter: dict[str, Any], body: str) -> str:
    trimmed = body.strip("\n")
    return f"{render_frontmatter(frontmatter)}\n{trimmed}\n"


def load_jsonl_map(path: Path, key: str) -> dict[str, dict[str, Any]]:
    return {
        str(row.get(key)): row
        for row in read_jsonl(path)
        if isinstance(row, dict) and row.get(key) is not None
    }


def risk_at_most(risk: str, max_risk: str) -> bool:
    return RISK_LEVELS.get(risk, 99) <= RISK_LEVELS.get(max_risk, -1)


def ensure_last(path: Path, payload: dict[str, Any]) -> Path:
    return write_json(path, payload)


def created_payload(**fields: Any) -> dict[str, Any]:
    return {"created_at": now_iso(), **fields}
