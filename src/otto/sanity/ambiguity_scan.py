from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, state_root
from ..state import read_json
from .invariants import evaluate_record_invariants, issue, record_id, result_shape
from .state_index import iter_indexed_records, records_by_id


INFRA_RECORD_TYPES = {
    "context_pack",
    "daily_loop_last",
    "runtime_owner",
    "single_owner_lock",
    "runtime_smoke",
    "creative_heartbeat_policy",
    "production_cron_policy",
    "openclaw_tool_manifest",
    "openclaw_gateway_probe",
    "openclaw_cron_contract",
    "openclaw_loop_state",
    "openclaw_sync_status",
    "openclaw_qmd_refresh_status",
    "openclaw_heartbeat_manifest",
    "openclaw_soul_v2",
    "qmd_manifest",
    "source_registry",
    "native_openclaw_config",
    "openclaw_shadow_config",
    "routing_config",
    "kernelization_config",
    "paths_config",
    "retrieval_config",
    "heartbeat_telemetry_config",
}


def ambiguities_path() -> Path:
    return state_root() / "sanity" / "ambiguities.jsonl"


def scan_ambiguities(*, write: bool = True) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for rid, records in records_by_id().items():
        if len(records) > 1:
            files = sorted({record["file"] for record in records})
            issues.append(
                issue(
                    prefix="amb",
                    severity="fail",
                    problem="duplicate_id_across_state_files",
                    record={"id": rid, "state": "AMBIGUOUS", "kind": "duplicate"},
                    record_kind_name="duplicate_id",
                    ambiguity_type="duplicate_id",
                    records=[rid],
                    files=files,
                    recommended_action="link_as_variant_or_mark_one_superseded",
                    quarantine=True,
                )
            )
    for item in iter_indexed_records():
        record = item["record"]
        rid = record_id(record)
        if item["record_type"] not in INFRA_RECORD_TYPES:
            if not record.get("state"):
                issues.append(
                    issue(
                        prefix="amb",
                        severity="fail",
                        record=record,
                        record_kind_name=item["record_type"],
                        problem="missing_state",
                        ambiguity_type="missing_required_field",
                        recommended_action="set_explicit_state_or_quarantine",
                        file=item["file"],
                    )
                )
            if "privacy" in record and not record.get("privacy"):
                issues.append(
                    issue(
                        prefix="amb",
                        severity="fail",
                        record=record,
                        record_kind_name=item["record_type"],
                        problem="missing_privacy",
                        ambiguity_type="missing_required_field",
                        recommended_action="set_privacy_or_quarantine",
                        file=item["file"],
                    )
                )
        issues.extend(evaluate_record_invariants(record))
        if rid and record.get("qmd_index_allowed") is True and str(record.get("state", "")).upper() in {"RAW", "CANDIDATE", "WRITE_CANDIDATE"}:
            issues.append(
                issue(
                    prefix="amb",
                    severity="fail",
                    record=record,
                    record_kind_name=item["record_type"],
                    problem="conflicting_qmd_index_allowed_for_raw_or_candidate",
                    ambiguity_type="conflicting_policy_flag",
                    recommended_action="set_qmd_index_allowed_false",
                    file=item["file"],
                )
            )
    context = read_json(state_root() / "openclaw" / "context_pack_v1.json", default={}) or {}
    if context.get("safety", {}).get("candidate_content_in_context") is True:
        issues.append(
            issue(
                prefix="amb",
                severity="fail",
                problem="candidate_content_marked_visible_in_context_pack",
                record={"id": "context_pack", "state": context.get("state"), "kind": "context_pack"},
                record_kind_name="context_pack",
                ambiguity_type="candidate_shown_as_context_truth",
                recommended_action="remove_candidate_content_from_context_pack",
                quarantine=False,
            )
        )
    lock = read_json(state_root() / "runtime" / "single_owner_lock.json", default={}) or {}
    telegram_owners = lock.get("telegram_enabled_owners") or []
    if isinstance(telegram_owners, list) and len(telegram_owners) > 1:
        issues.append(
            issue(
                prefix="amb",
                severity="fail",
                problem="multiple_active_telegram_owners",
                record={"id": "single_owner_lock", "state": lock.get("classification"), "kind": "runtime_owner"},
                record_kind_name="runtime_owner",
                ambiguity_type="duplicate_active_owner",
                records=telegram_owners,
                recommended_action="disable_all_but_one_telegram_owner",
                quarantine=False,
            )
        )
    if lock.get("classification") == "unsafe-owner-conflict":
        issues.append(
            issue(
                prefix="amb",
                severity="fail",
                problem="runtime_owner_lock_reports_conflict",
                record={"id": "single_owner_lock", "state": lock.get("classification"), "kind": "runtime_owner"},
                record_kind_name="runtime_owner",
                ambiguity_type="owner_conflict",
                recommended_action="run single-owner-lock and fix owner conflict before automation",
                quarantine=False,
            )
        )
    tool_manifest = read_json(state_root() / "openclaw" / "tool_manifest.json", default={}) or {}
    tool_names = {tool.get("name") for tool in tool_manifest.get("tools", []) if isinstance(tool, dict)}
    for required in {"otto.heartbeat", "otto.context_pack", "otto.runtime_status", "otto.qmd_health"}:
        if tool_manifest and required not in tool_names:
            issues.append(
                issue(
                    prefix="amb",
                    severity="fail",
                    problem=f"openclaw_tool_manifest_missing_{required}",
                    record={"id": "openclaw_tool_manifest", "state": tool_manifest.get("state"), "kind": "tool_manifest"},
                    record_kind_name="openclaw_tool_manifest",
                    ambiguity_type="missing_openclaw_tool",
                    recommended_action="rewrite openclaw-tool-manifest",
                    quarantine=False,
                )
            )
    qmd_manifest = read_json(state_root() / "qmd" / "qmd_manifest.json", default={}) or {}
    for source in qmd_manifest.get("sources", []) if isinstance(qmd_manifest.get("sources"), list) else []:
        if str(source.get("kind", "")).endswith("_raw"):
            issues.append(
                issue(
                    prefix="amb",
                    severity="fail",
                    problem="raw_source_present_in_qmd_manifest",
                    record={"id": source.get("id"), "state": "QMD_SOURCE", "kind": source.get("kind")},
                    record_kind_name="qmd_manifest_source",
                    ambiguity_type="qmd_policy_conflict",
                    recommended_action="remove_raw_source_from_qmd_manifest",
                    quarantine=True,
                )
            )
    source_registry = read_json(state_root() / "memory" / "source_registry.json", default={}) or {}
    for source in source_registry.get("sources", []) if isinstance(source_registry.get("sources"), list) else []:
        if str(source.get("kind", "")).endswith("_raw") and source.get("qmd_index") is True:
            issues.append(
                issue(
                    prefix="amb",
                    severity="fail",
                    problem="raw_source_registry_entry_is_qmd_indexable",
                    record={"id": source.get("id"), "state": "SOURCE_REGISTRY", "kind": source.get("kind")},
                    record_kind_name="source_registry_entry",
                    ambiguity_type="source_registry_policy_conflict",
                    recommended_action="set_source_registry_qmd_index_false",
                    quarantine=True,
                )
            )
    production_cron = read_json(state_root() / "schedules" / "production_cron_policy.json", default={}) or {}
    safety = production_cron.get("default_safety") or {}
    if safety.get("auto_publish") is True or safety.get("auto_send") is True:
        issues.append(
            issue(
                prefix="amb",
                severity="fail",
                problem="production_cron_policy_allows_autonomous_publication",
                record={"id": "production_cron_policy", "state": production_cron.get("mode"), "kind": "cron_policy"},
                record_kind_name="cron_policy",
                ambiguity_type="unsafe_cron_policy",
                recommended_action="set auto_publish/auto_send false",
                quarantine=False,
            )
        )
    if write:
        for item in issues:
            append_jsonl(ambiguities_path(), item)
    return result_shape(
        ok=not any(item["severity"] == "fail" for item in issues),
        state_changed=write and bool(issues),
        created_ids=[item["issue_id"] for item in issues],
        warnings=[item for item in issues if item["severity"] == "warn"],
        blockers=[item for item in issues if item["severity"] == "fail"],
        next_required_action="quarantine_or_resolve_ambiguities" if issues else None,
        issues=issues,
        issue_count=len(issues),
    )
