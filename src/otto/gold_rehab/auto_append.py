from __future__ import annotations

from pathlib import Path
from typing import Any

from ..corridor import (
    ensure_last,
    load_jsonl_map,
    merge_frontmatter,
    render_markdown,
    risk_at_most,
    sha256_file,
    split_frontmatter,
)
from ..governance_utils import make_id, public_result, read_jsonl, state_root
from .patch_ledger import patch_ledger_path, record_patch
from .review_needed import queue_review_needed
from .discuss_later import queue_discuss_later


def auto_append_policy_path() -> Path:
    return state_root() / "gold_rehab" / "auto_append_policy.json"


def auto_append_last_path() -> Path:
    return state_root() / "gold_rehab" / "auto_append_last.json"


def auto_append_runs_path() -> Path:
    return state_root() / "gold_rehab" / "auto_append_runs.jsonl"


def _apply_single(candidate: dict[str, Any], run_id: str) -> dict[str, Any]:
    path = Path(str(candidate["path"]))
    if not path.exists():
        return {"ok": False, "reason": "path-not-found", "path": str(path)}
    before_checksum = sha256_file(path)
    frontmatter, body, _had_frontmatter = split_frontmatter(path.read_text(encoding="utf-8"))
    merged = merge_frontmatter(
        frontmatter,
        {
            "otto": {
                **dict(candidate.get("otto") or {}),
                "provenance": {**dict(((candidate.get("otto") or {}).get("provenance") or {}), run_id=run_id)},
            },
            "otto_suggestions": dict(candidate.get("otto_suggestions") or {}),
        },
    )
    markdown_block = str(candidate.get("markdown_block") or "").strip()
    next_body = body.strip()
    if markdown_block and "OTTO:ENRICHMENT" not in next_body:
        next_body = f"{next_body}\n\n{markdown_block}".strip()
    path.write_text(render_markdown(merged, next_body), encoding="utf-8")
    after_checksum = sha256_file(path)
    patch = {
        "patch_id": make_id("patch"),
        "run_id": run_id,
        "path": str(path),
        "operation": "append_otto_enrichment",
        "risk": candidate["risk"],
        "review_status": "auto_applied_low_risk",
        "before_checksum": before_checksum,
        "after_checksum": after_checksum,
        "reversible": True,
        "rollback_hint": "remove OTTO:ENRICHMENT block or otto namespace fields",
        "fields_added": ["otto.state", "otto.source_checksum", "otto_suggestions.suggested_tags"],
        "created_at": __import__("otto.state", fromlist=["now_iso"]).now_iso(),
    }
    record_patch(patch)
    return {"ok": True, "patch": patch}


def apply_safe_enrichment(*, risk_max: str = "R1_LOW_RISK_SEMANTIC", batch_size: int = 10) -> dict[str, Any]:
    run_id = make_id("rehab")
    applied: list[dict[str, Any]] = []
    queued_review = 0
    queued_discuss = 0
    for candidate in read_jsonl(state_root() / "gold_rehab" / "semantic_enrichment_candidates.jsonl")[: batch_size * 3]:
        risk = str(candidate.get("risk") or "")
        if risk_at_most(risk, risk_max):
            result = _apply_single(candidate, run_id)
            if result.get("ok"):
                applied.append(result["patch"])
            continue
        if risk == "R3_REVIEW_REQUIRED":
            queue_review_needed(
                {
                    "review_id": make_id("grev"),
                    "risk": risk,
                    "path": candidate.get("path"),
                    "reason": "Potential profile/weakness/support claim.",
                    "proposed_append": {"kind": "rehab_candidate", "claim": candidate.get("markdown_block"), "confidence": 0.69},
                    "allowed_actions": ["approve", "edit", "reject", "defer", "discuss_later"],
                    "default_action": "defer",
                }
            )
            queued_review += 1
        else:
            queue_discuss_later(
                {
                    "item_id": make_id("discuss"),
                    "topic": "Is this enrichment safe to promote automatically?",
                    "path": candidate.get("path"),
                    "proposed_claim": candidate.get("markdown_block"),
                    "why_discuss": "Medium confidence and identity-relevant.",
                    "status": "deferred_for_conversation",
                }
            )
            queued_discuss += 1
    summary = {
        "ok": True,
        "run_id": run_id,
        "applied_count": len(applied),
        "queued_review_count": queued_review,
        "queued_discuss_count": queued_discuss,
        "risk_max": risk_max,
    }
    ensure_last(auto_append_last_path(), summary)
    record = {**summary, "applied_patch_ids": [item["patch_id"] for item in applied]}
    __import__("otto.corridor", fromlist=["ensure_jsonl_row"]).ensure_jsonl_row(auto_append_runs_path(), record)
    ensure_last(auto_append_policy_path(), {"risk_max": risk_max, "batch_size": batch_size})
    return public_result(True, summary=summary)
