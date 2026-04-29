from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, read_jsonl, state_root
from ..state import now_iso, write_json
from .ambiguity_scan import ambiguities_path, scan_ambiguities
from .dead_end_scan import dead_ends_path, scan_dead_ends
from .invariants import result_shape
from .noisy_memory_scan import noisy_memory_path, scan_noisy_memory
from .quarantine import quarantine_issues
from .schema_audit import run_schema_audit
from .silent_failure_scan import scan_silent_failures, silent_failures_path
from .state_index import build_state_index


def sanity_last_path() -> Path:
    return state_root() / "sanity" / "sanity_last.json"


def sanity_runs_path() -> Path:
    return state_root() / "sanity" / "sanity_runs.jsonl"


def repair_plan_path() -> Path:
    return state_root() / "sanity" / "repair_plan.json"


def _issue_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in [dead_ends_path(), silent_failures_path(), ambiguities_path(), noisy_memory_path()]:
        rows.extend(read_jsonl(path))
    return rows


def generate_repair_plan(*, write: bool = True, issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    issues = issues if issues is not None else _issue_rows()
    fail_count = len([item for item in issues if item.get("severity") == "fail"])
    warn_count = len([item for item in issues if item.get("severity") == "warn"])
    actions = []
    for index, item in enumerate(issues, start=1):
        actions.append(
            {
                "action_id": f"repair_{index:03d}",
                "issue_id": item.get("issue_id"),
                "kind": "manual_resolution_required" if item.get("severity") == "fail" else "manual_triage_recommended",
                "recommended_command": item.get("recommended_action"),
                "risk": "medium" if item.get("severity") == "fail" else "low",
            }
        )
    plan = {
        "version": 1,
        "generated_at": now_iso(),
        "auto_repair": False,
        "summary": {"fail": fail_count, "warn": warn_count, "quarantined": 0},
        "actions": actions,
    }
    if write:
        write_json(repair_plan_path(), plan)
    return plan


def run_sanity_scan(*, strict: bool = False, write: bool = True) -> dict[str, Any]:
    index = build_state_index(write=write)
    schema = run_schema_audit()
    dead = scan_dead_ends(write=write)
    silent = scan_silent_failures(write=write)
    ambiguity = scan_ambiguities(write=write)
    noisy = scan_noisy_memory(write=write)
    all_issues = []
    for result in [dead, silent, ambiguity, noisy]:
        all_issues.extend(result.get("issues", []))
    quarantined = quarantine_issues([item for item in all_issues if item.get("severity") == "fail"]) if write else []
    plan = generate_repair_plan(write=write, issues=all_issues)
    if quarantined:
        plan["summary"]["quarantined"] = len(quarantined)
        if write:
            write_json(repair_plan_path(), plan)
    strict_failures = len([item for item in all_issues if item.get("severity") == "fail"])
    warnings = [item for item in all_issues if item.get("severity") == "warn"]
    ok = strict_failures == 0 and (not strict or not warnings) and schema.get("ok", False)
    result = result_shape(
        ok=ok,
        state_changed=write,
        created_ids=[item["issue_id"] for item in all_issues if item.get("issue_id")],
        warnings=warnings,
        blockers=[item for item in all_issues if item.get("severity") == "fail"],
        quarantined=quarantined,
        next_required_action="execute_repair_plan" if all_issues else None,
        state="SAN1_DEAD_END_SILENT_FAILURE_AMBIGUITY_GUARD_READY",
        strict=strict,
        strict_failures=strict_failures,
        warning_count=len(warnings),
        state_index=index,
        schema_audit=schema,
        repair_plan=plan,
    )
    if write:
        write_json(sanity_last_path(), result)
        append_jsonl(sanity_runs_path(), result)
    return result


def sanity_summary() -> dict[str, Any]:
    from ..state import read_json

    last = read_json(sanity_last_path(), default={}) or {}
    plan = read_json(repair_plan_path(), default={}) or {}
    active_quarantined = len(last.get("quarantined") or [])
    if not active_quarantined:
        active_quarantined = int(((plan.get("summary") or {}).get("quarantined") or 0))
    return {
        "state": last.get("state", "SAN0_NOT_STARTED"),
        "strict_failures": int(last.get("strict_failures", 0) or 0),
        "warnings": int(last.get("warning_count", 0) or 0),
        "quarantined": active_quarantined,
        "repair_plan_available": bool(plan),
    }
