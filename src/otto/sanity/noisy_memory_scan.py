from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, state_root
from .invariants import issue, record_id, result_shape
from .state_index import iter_indexed_records


CANDIDATE_RECORD_TYPES = {
    "candidate_memory",
    "writeback_candidates",
    "song_skeletons",
    "paper_onboarding",
    "reflections",
    "council_statements",
    "release_candidates",
    "production_briefs",
}


def noisy_memory_path() -> Path:
    return state_root() / "sanity" / "noisy_memory.jsonl"


def scan_noisy_memory(*, write: bool = True) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    title_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    pending_reviews = 0
    for item in iter_indexed_records():
        record = item["record"]
        if item["record_type"] == "review_items" and record.get("state") == "PENDING_REVIEW":
            pending_reviews += 1
        if item["record_type"] in CANDIDATE_RECORD_TYPES and "CANDIDATE" in str(record.get("state", "")).upper():
            evidence = record.get("evidence_refs") or record.get("source_refs") or []
            if len(evidence) < 1:
                issues.append(
                    issue(
                        prefix="noise",
                        severity="warn",
                        record=record,
                        record_kind_name=item["record_type"],
                        problem="candidate has low evidence",
                        signal_score=0.31,
                        duplicate_score=0.0,
                        staleness_days=0,
                        review_priority="low_until_evidence_added",
                        recommended_action="request_evidence_or_park",
                    )
                )
            title = str(record.get("title") or record.get("title_working") or "").strip().lower()
            if title:
                title_groups[(item["record_type"], title)].append(record)
    for (record_type, _title), records in title_groups.items():
        if len(records) > 1:
            first = records[0]
            issues.append(
                issue(
                    prefix="noise",
                    severity="warn",
                    record=first,
                    record_kind_name=record_type,
                    problem="duplicate_semantic_candidate_by_title",
                    signal_score=0.45,
                    duplicate_score=0.72,
                    staleness_days=0,
                    related_records=[record_id(record) for record in records],
                    review_priority="dedupe_before_review",
                    recommended_action="link_or_dedupe_candidate_variants",
                )
            )
    if pending_reviews > 25:
        issues.append(
            issue(
                prefix="noise",
                severity="warn",
                record={"id": "review_queue", "state": "OVERLOADED", "kind": "review_queue"},
                record_kind_name="review_queue",
                problem="too_many_pending_reviews",
                signal_score=0.5,
                duplicate_score=0.0,
                staleness_days=0,
                review_priority="triage_required",
                recommended_action="triage_pending_reviews_before_generating_more_candidates",
            )
        )
    if write:
        for item in issues:
            append_jsonl(noisy_memory_path(), item)
    return result_shape(
        ok=True,
        state_changed=write and bool(issues),
        created_ids=[item["issue_id"] for item in issues],
        warnings=issues,
        blockers=[],
        next_required_action="triage_noisy_memory" if issues else None,
        issues=issues,
        issue_count=len(issues),
    )
