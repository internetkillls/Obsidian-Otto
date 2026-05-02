from __future__ import annotations

from pathlib import Path

from ..corridor import ensure_jsonl_row
from ..governance_utils import state_root


def frontmatter_patch_candidates_path() -> Path:
    return state_root() / "gold_rehab" / "frontmatter_patch_candidates.jsonl"


def build_frontmatter_patch_candidate(path: str, readiness: dict[str, object], *, persist: bool = True) -> dict[str, object]:
    payload = {
        "path": path,
        "otto": {
            "state": readiness.get("next_state"),
            "qmd_index_allowed": False,
            "vault_writeback_allowed": False,
        },
    }
    if persist:
        ensure_jsonl_row(frontmatter_patch_candidates_path(), payload)
    return payload
