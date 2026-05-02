from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, find_jsonl, make_id, read_jsonl, state_root
from ..state import now_iso


def action_queue_path() -> Path:
    return state_root() / "human" / "action_queue.jsonl"


def default_action() -> dict[str, Any]:
    return {
        "action_id": make_id("act"),
        "state": "PROPOSED",
        "title": "Run creative-human heartbeat dry-run",
        "kind": "engineering",
        "scope": "bounded_commit",
        "why_it_matters": "Turns Otto from bridge infrastructure into a human-facing continuity system.",
        "expected_outcome": "daily_handoff.json and action_queue.jsonl are generated safely.",
        "support_lens": {"dimension": "context_switching_cost", "support": "bounded scope plus explicit done signal"},
        "evidence_refs": [
            "state/human/daily_handoff.json",
            "state/openclaw/context_pack_v1.json",
            "state/profile/profile_policy.json",
            "state/council/council_policy.json",
        ],
        "blocked_by": [],
        "risk": "low",
        "created_at": now_iso(),
    }


def write_action_queue(actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    actions = actions or [default_action()]
    for action in actions:
        append_jsonl(action_queue_path(), action)
    return {"ok": True, "path": str(action_queue_path()), "actions": actions}


def list_actions() -> list[dict[str, Any]]:
    return read_jsonl(action_queue_path())


def load_action(action_id: str) -> dict[str, Any] | None:
    return find_jsonl(action_queue_path(), "action_id", action_id)
