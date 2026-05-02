from __future__ import annotations

from pathlib import Path
from typing import Any

from ...governance_utils import append_jsonl, find_jsonl, make_id, public_result, read_jsonl, state_root
from ...state import now_iso, write_json
from .markdown import render_note
from .vault import classify_target, default_target_path, is_allowed_otto_realm_target


WRITEBACK_STATE_DIR = Path("exports") / "obsidian"


def writeback_root() -> Path:
    return state_root() / WRITEBACK_STATE_DIR


def candidates_path() -> Path:
    return writeback_root() / "writeback_candidates.jsonl"


def last_path() -> Path:
    return writeback_root() / "writeback_last.json"


def previews_dir() -> Path:
    path = writeback_root() / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def evaluate_writeback_policy(item: dict[str, Any]) -> dict[str, Any]:
    kind = str(item.get("kind") or "")
    state = str(item.get("state") or "").lower()
    status = str(item.get("status") or item.get("otto_state") or "").lower()
    domain = str(item.get("domain") or "")
    privacy = str(item.get("privacy") or "private")
    target = item.get("target_path")

    blocked: list[str] = []
    if kind in {"social_raw", "instagram_raw", "telegram_raw", "api_dump"}:
        blocked.append("raw_social_blocked")
    if status == "candidate" and domain in {"profile", "self_model"}:
        blocked.append("candidate_profile_claim_blocked")
    if kind in {"profile_claim_candidate", "psychometric_hypothesis", "sociometric_hypothesis"} and status not in {
        "reviewed",
        "gold",
        "approved",
    }:
        blocked.append("unreviewed_profile_or_psychometric_claim_blocked")
    if privacy == "sensitive" and status not in {"reviewed", "gold", "approved"}:
        blocked.append("sensitive_unreviewed_blocked")
    if target and not is_allowed_otto_realm_target(target):
        blocked.append("target_outside_otto_realm_allowed_paths")

    allowed_status = status in {"reviewed", "gold", "approved"} or state in {
        "approved",
        "gold",
        "reviewed",
        "written_to_vault",
    }
    allowed = not blocked and bool(target) and allowed_status
    return {
        "allowed_to_preview": not any(reason.endswith("target_outside_otto_realm_allowed_paths") for reason in blocked),
        "allowed_to_write": allowed,
        "blocked_reason": None if allowed else (blocked[0] if blocked else "not_reviewed"),
        "blocked_reasons": blocked or ([] if allowed else ["not_reviewed"]),
        "target": classify_target(target) if target else None,
    }


def create_writeback_candidate(kind: str = "handoff", *, dry_run: bool = True, body: str | None = None) -> dict[str, Any]:
    writeback_id = make_id("wb")
    normalized_kind = "handoff_note" if kind == "handoff" else kind
    item = {
        "writeback_id": writeback_id,
        "state": "WRITE_CANDIDATE",
        "kind": normalized_kind,
        "status": "candidate",
        "target_path": str(default_target_path(normalized_kind)),
        "source_refs": ["state/openclaw/context_pack_v1.json", "state/runtime/smoke_last.json"],
        "privacy": "private_reviewed",
        "requires_review": True,
        "allowed_to_write": False,
        "blocked_reason": "not_reviewed",
        "title": "Otto Handoff",
        "body": body or "Reviewed writeback candidate generated for Otto-Realm.",
        "created_at": now_iso(),
        "qmd_reindex_recommended": True,
        "dry_run": dry_run,
    }
    policy = evaluate_writeback_policy(item)
    item.update({"policy": policy})
    append_jsonl(candidates_path(), item)
    write_json(last_path(), item)
    return public_result(True, candidate=item, path=str(candidates_path()), dry_run=dry_run)


def load_writeback_item(writeback_id: str) -> dict[str, Any] | None:
    return find_jsonl(candidates_path(), "writeback_id", writeback_id)


def preview_writeback(writeback_id: str, *, item: dict[str, Any] | None = None) -> dict[str, Any]:
    item = item or load_writeback_item(writeback_id)
    if not item:
        return public_result(False, reason="writeback-id-not-found", writeback_id=writeback_id)
    markdown = render_note(item)
    preview_path = previews_dir() / f"{writeback_id}.md"
    preview_path.write_text(markdown, encoding="utf-8")
    return public_result(True, writeback_id=writeback_id, preview_path=str(preview_path), markdown=markdown)


def write_reviewed_item(item: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    policy = evaluate_writeback_policy(item)
    if not policy["allowed_to_write"]:
        blocked = {**item, "state": "BLOCKED_BY_POLICY", "policy": policy, "updated_at": now_iso()}
        write_json(last_path(), blocked)
        return public_result(False, reason=policy["blocked_reason"], policy=policy, item=blocked)
    markdown = render_note(item)
    target = Path(item["target_path"]).expanduser().resolve()
    preview = preview_writeback(str(item.get("writeback_id") or item.get("gold_id") or make_id("wb")), item=item)
    if dry_run:
        return public_result(True, dry_run=True, write_allowed=True, preview=preview, target_path=str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")
    written = {
        **item,
        "state": "WRITTEN_TO_VAULT",
        "written_at": now_iso(),
        "target_path": str(target),
        "qmd_reindex_recommended": True,
    }
    append_jsonl(candidates_path(), written)
    write_json(last_path(), written)
    return public_result(True, dry_run=False, written=written, path=str(target))


def write_reviewed_by_id(writeback_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    item = load_writeback_item(writeback_id)
    if not item:
        return public_result(False, reason="writeback-id-not-found", writeback_id=writeback_id)
    item = {
        **item,
        "state": "APPROVED",
        "status": "reviewed",
        "allowed_to_write": True,
        "blocked_reason": None,
    }
    return write_reviewed_item(item, dry_run=dry_run)


def write_gold_memory(gold: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    item = {
        "writeback_id": make_id("wb"),
        "state": "APPROVED",
        "status": "gold" if gold.get("state") == "GOLD" else "reviewed",
        "kind": gold.get("kind", "gold_memory"),
        "title": gold.get("title", "Gold Memory"),
        "body": gold.get("body", ""),
        "privacy": gold.get("privacy", "private_reviewed"),
        "source_refs": gold.get("evidence_refs", []),
        "target_path": str(default_target_path(gold.get("kind", "gold_memory"))),
        "qmd_reindex_recommended": True,
    }
    return write_reviewed_item(item, dry_run=dry_run)


def writeback_counts() -> dict[str, int]:
    rows = read_jsonl(candidates_path())
    return {
        "candidate_count": len([row for row in rows if row.get("state") == "WRITE_CANDIDATE"]),
        "written_count": len([row for row in rows if row.get("state") == "WRITTEN_TO_VAULT"]),
        "blocked_count": len([row for row in rows if row.get("state") == "BLOCKED_BY_POLICY"]),
    }
