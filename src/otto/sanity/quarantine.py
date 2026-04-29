from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, read_jsonl, state_root
from ..state import now_iso


def quarantine_path() -> Path:
    return state_root() / "sanity" / "quarantine.jsonl"


def quarantine_issue(issue: dict[str, Any]) -> dict[str, Any]:
    item = {
        "quarantine_id": make_id("quar"),
        "record_id": issue.get("record_id"),
        "record_kind": issue.get("record_kind"),
        "reason": issue.get("problem"),
        "issue_id": issue.get("issue_id"),
        "blocked_outputs": ["vault", "qmd", "openclaw_context"],
        "created_at": now_iso(),
        "release_condition": "approved_review_or_rejected",
    }
    append_jsonl(quarantine_path(), item)
    return item


def quarantine_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quarantined = []
    for issue in issues:
        if issue.get("severity") == "fail" and (issue.get("quarantine", True)):
            quarantined.append(quarantine_issue(issue))
    return quarantined


def quarantine_summary() -> dict[str, Any]:
    rows = read_jsonl(quarantine_path())
    return {"count": len(rows), "record_ids": [row.get("record_id") for row in rows if row.get("record_id")]}
