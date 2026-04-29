from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, read_jsonl, state_root
from ..state import now_iso, read_json
from .invariants import issue, record_id, result_shape
from .state_index import iter_indexed_records


TERMINAL_STATES = {
    "REJECTED",
    "DEFERRED",
    "PARKED",
    "EXPIRED",
    "ARCHIVED",
    "BLOCKED_BY_POLICY",
    "NEEDS_MORE_EVIDENCE",
    "WRITTEN_TO_VAULT",
    "GOLD",
}


def dead_ends_path() -> Path:
    return state_root() / "sanity" / "dead_ends.jsonl"


def scan_dead_ends(*, write: bool = True) -> dict[str, Any]:
    records = iter_indexed_records()
    review_item_ids = {
        item["record"].get("item_id")
        for item in records
        if item["record_type"] == "review_items" and item["record"].get("item_id")
    }
    outcome_action_ids = {
        item["record"].get("action_id")
        for item in records
        if item["record_type"] == "outcomes" and item["record"].get("action_id")
    }
    feedback_song_ids = {
        item["record"].get("song_skeleton_id")
        for item in records
        if item["record_type"] == "song_feedback" and item["record"].get("song_skeleton_id")
    }
    issues: list[dict[str, Any]] = []
    for item in records:
        record = item["record"]
        rid = record_id(record)
        state = str(record.get("state") or "").upper()
        if state in TERMINAL_STATES:
            continue
        if item["record_type"] == "candidate_memory" and rid not in review_item_ids:
            issues.append(
                issue(
                    prefix="dead",
                    severity="fail",
                    record=record,
                    record_kind_name="candidate_memory",
                    problem="candidate has no review_queue item and no terminal state",
                    expected_next=["PENDING_REVIEW", "REJECTED", "PARKED", "EXPIRED"],
                    recommended_action=f"review-enqueue --candidate-id {rid}",
                )
            )
        if item["record_type"] == "review_items" and record.get("item_id"):
            source_exists = any(other.get("id") == record.get("item_id") for other in records)
            if not source_exists:
                issues.append(
                    issue(
                        prefix="dead",
                        severity="fail",
                        record=record,
                        record_kind_name="review_item",
                        problem="review item source candidate is missing",
                        expected_next=["BLOCKED_BY_POLICY", "NEEDS_MORE_EVIDENCE"],
                        recommended_action="mark_review_needs_more_evidence_or_reject",
                    )
                )
        if item["record_type"] == "selected_action" and record.get("action_id") not in outcome_action_ids:
            issues.append(
                issue(
                    prefix="dead",
                    severity="warn",
                    record=record,
                    record_kind_name="selected_action",
                    problem="selected action has no outcome yet",
                    expected_next=["OUTCOME_CAPTURED", "SKIPPED", "FAILED", "DEFERRED"],
                    recommended_action=f"action-outcome --id {record.get('action_id')} --result completed --note <text>",
                )
            )
        if item["record_type"] == "song_skeletons" and rid not in feedback_song_ids:
            issues.append(
                issue(
                    prefix="dead",
                    severity="warn",
                    record=record,
                    record_kind_name="song_skeleton_candidate",
                    problem="song skeleton has no feedback/review/archive path",
                    expected_next=["feedback", "PARKED", "REJECTED"],
                    recommended_action=f"song-feedback --song-id {rid} --decision park",
                )
            )
        if item["record_type"] == "paper_onboarding" and record.get("review_required") and state not in TERMINAL_STATES:
            issues.append(
                issue(
                    prefix="dead",
                    severity="warn",
                    record=record,
                    record_kind_name="paper_onboarding_candidate",
                    problem="paper onboarding candidate has no review/archive route",
                    expected_next=["PENDING_REVIEW", "PARKED", "REJECTED"],
                    recommended_action="enqueue_review_or_mark_parked",
                )
            )
    heartbeat = read_json(state_root() / "openclaw" / "heartbeat" / "otto_heartbeat_manifest.json", default={}) or {}
    if heartbeat and not heartbeat.get("tools"):
        issues.append(
            issue(
                prefix="dead",
                severity="fail",
                record={"id": "otto_heartbeat_manifest", "state": "NO_TOOLS", "kind": "openclaw_heartbeat"},
                record_kind_name="openclaw_heartbeat",
                problem="OpenClaw heartbeat manifest has no runnable tools",
                expected_next=["tool_manifest_ready", "heartbeat_disabled_with_reason"],
                recommended_action="regenerate otto_heartbeat_manifest with tool entries or disable heartbeat explicitly",
            )
        )
    qmd_manifest = read_json(state_root() / "qmd" / "qmd_manifest.json", default={}) or {}
    if qmd_manifest and not qmd_manifest.get("sources"):
        issues.append(
            issue(
                prefix="dead",
                severity="fail",
                record={"id": "qmd_manifest", "state": "NO_SOURCES", "kind": "qmd_manifest"},
                record_kind_name="qmd_manifest",
                problem="QMD manifest has no sources and cannot route retrieval",
                expected_next=["sources_present", "qmd_disabled_with_reason"],
                recommended_action="rewrite qmd manifest from source registry or mark QMD unavailable",
            )
        )
    if write:
        for item in issues:
            append_jsonl(dead_ends_path(), item)
    return result_shape(
        ok=not any(item["severity"] == "fail" for item in issues),
        state_changed=write and bool(issues),
        created_ids=[item["issue_id"] for item in issues],
        warnings=[item for item in issues if item["severity"] == "warn"],
        blockers=[item for item in issues if item["severity"] == "fail"],
        next_required_action="review_or_quarantine_dead_ends" if issues else None,
        issues=issues,
        issue_count=len(issues),
    )
