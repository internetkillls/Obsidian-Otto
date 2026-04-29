from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, read_jsonl, state_root
from ..state import read_json
from .invariants import issue, result_shape


def silent_failures_path() -> Path:
    return state_root() / "sanity" / "silent_failures.jsonl"


def _exists(rel: str) -> bool:
    return (state_root() / rel).exists()


def scan_silent_failures(*, write: bool = True) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    daily = read_json(state_root() / "runtime" / "daily_loop_last.json", default={}) or {}
    if daily.get("ok") is True:
        expected = ["human/daily_handoff.json", "human/action_queue.jsonl"]
        missing = [rel for rel in expected if not _exists(rel)]
        if missing:
            issues.append(
                issue(
                    prefix="silent",
                    severity="fail",
                    record={"id": "daily-loop", "state": daily.get("state"), "kind": "command_result"},
                    record_kind_name="command_result",
                    command="daily-loop --dry-run",
                    problem="command reported ok=true but expected_outputs were not created",
                    expected_outputs=[f"state/{rel}" for rel in expected],
                    actual_outputs=[f"state/{rel}" for rel in expected if rel not in missing],
                    missing_outputs=[f"state/{rel}" for rel in missing],
                    recommended_action="rerun daily-loop or fix output contract",
                )
            )
    context = read_json(state_root() / "openclaw" / "context_pack_v1.json", default={}) or {}
    if context and not context.get("generated_at"):
        issues.append(
            issue(
                prefix="silent",
                severity="fail",
                record={"id": "context_pack", "state": context.get("state"), "kind": "context_pack"},
                record_kind_name="context_pack",
                problem="context pack exists but has no generated_at timestamp",
                expected_outputs=["state/openclaw/context_pack_v1.json.generated_at"],
                actual_outputs=[],
                missing_outputs=["generated_at"],
                recommended_action="rewrite context pack",
            )
        )
    heartbeat_manifest = read_json(state_root() / "openclaw" / "heartbeat" / "otto_heartbeat_manifest.json", default={}) or {}
    if heartbeat_manifest and not heartbeat_manifest.get("tools"):
        issues.append(
            issue(
                prefix="silent",
                severity="fail",
                record={"id": "creative-heartbeat", "state": "OK_WITHOUT_TOOLS", "kind": "heartbeat"},
                record_kind_name="heartbeat",
                command="creative-heartbeat --dry-run",
                problem="heartbeat reported ok=true but generated no candidates and no no_output_reason",
                expected_outputs=["candidate_or_no_output_reason"],
                actual_outputs=[],
                missing_outputs=["no_output_reason"],
                recommended_action="rerun with explain-no-output or fix heartbeat contract",
            )
        )
    tool_manifest = read_json(state_root() / "openclaw" / "tool_manifest.json", default={}) or {}
    if tool_manifest and not tool_manifest.get("tools"):
        issues.append(
            issue(
                prefix="silent",
                severity="fail",
                record={"id": "openclaw-tool-manifest", "state": tool_manifest.get("state"), "kind": "tool_manifest"},
                record_kind_name="tool_manifest",
                command="openclaw-tool-manifest",
                problem="OpenClaw tool manifest exists but exposes no tools",
                expected_outputs=["state/openclaw/tool_manifest.json.tools"],
                actual_outputs=[],
                missing_outputs=["tools"],
                recommended_action="rewrite openclaw-tool-manifest",
            )
        )
    gateway_probe = read_json(state_root() / "openclaw" / "gateway_probe.json", default={}) or {}
    if gateway_probe.get("ok") is True and not gateway_probe.get("port"):
        issues.append(
            issue(
                prefix="silent",
                severity="fail",
                record={"id": "openclaw-gateway-probe", "state": "OK_WITHOUT_PORT", "kind": "gateway_probe"},
                record_kind_name="gateway_probe",
                command="openclaw-gateway-probe",
                problem="gateway probe reported ok=true without a port",
                expected_outputs=["port", "reason"],
                actual_outputs=[key for key in ["port", "reason"] if gateway_probe.get(key)],
                missing_outputs=["port"],
                recommended_action="rerun gateway probe or fix probe output contract",
            )
        )
    qmd_manifest = read_json(state_root() / "qmd" / "qmd_manifest.json", default={}) or {}
    qmd_refresh = read_json(state_root() / "openclaw" / "qmd_refresh_status.json", default={}) or {}
    if qmd_manifest and not qmd_manifest.get("generated_at"):
        issues.append(
            issue(
                prefix="silent",
                severity="fail",
                record={"id": "qmd_manifest", "state": "MISSING_TIMESTAMP", "kind": "qmd_manifest"},
                record_kind_name="qmd_manifest",
                command="qmd-manifest --write",
                problem="qmd manifest exists but has no generated_at timestamp",
                expected_outputs=["state/qmd/qmd_manifest.json.generated_at"],
                actual_outputs=[],
                missing_outputs=["generated_at"],
                recommended_action="rewrite qmd manifest",
            )
        )
    if qmd_refresh.get("ok") is True and not qmd_refresh.get("last_success_at"):
        issues.append(
            issue(
                prefix="silent",
                severity="fail",
                record={"id": "qmd_refresh_status", "state": "OK_WITHOUT_SUCCESS_TIMESTAMP", "kind": "qmd_refresh"},
                record_kind_name="qmd_refresh",
                command="qmd-reindex",
                problem="qmd refresh reported ok=true but has no last_success_at",
                expected_outputs=["last_success_at"],
                actual_outputs=[],
                missing_outputs=["last_success_at"],
                recommended_action="rerun qmd-reindex or mark failed explicitly",
            )
        )
    production_cron = read_json(state_root() / "schedules" / "production_cron_policy.json", default={}) or {}
    if production_cron:
        cadences = production_cron.get("cadences") or {}
        jobs = [job for group in cadences.values() if isinstance(group, list) for job in group if isinstance(job, dict)]
        for job in jobs:
            missing = [key for key in ["job", "command", "output"] if not job.get(key)]
            if missing:
                issues.append(
                    issue(
                        prefix="silent",
                        severity="fail",
                        record={"id": job.get("job") or "unnamed_cron_job", "state": production_cron.get("mode"), "kind": "cron_job"},
                        record_kind_name="cron_job",
                        command=str(job.get("command") or ""),
                        problem="cron job is missing command/output contract",
                        expected_outputs=["job", "command", "output"],
                        actual_outputs=[key for key in ["job", "command", "output"] if job.get(key)],
                        missing_outputs=missing,
                        recommended_action="complete cron job contract or remove planned job",
                    )
                )
    empty_should_explain = [
        ("memory/candidate_claims.jsonl", "memory candidates"),
        ("artifacts/idea_inbox.jsonl", "artifact ideas"),
    ]
    for rel, label in empty_should_explain:
        path = state_root() / rel
        if path.exists() and not read_jsonl(path):
            issues.append(
                issue(
                    prefix="silent",
                    severity="warn",
                    record={"id": rel, "state": "EMPTY", "kind": "state_file"},
                    record_kind_name="state_file",
                    problem=f"{label} file exists but has no records",
                    expected_outputs=[f"state/{rel} records or no_output_reason"],
                    actual_outputs=[],
                    missing_outputs=["records"],
                    recommended_action="add no_output_reason or remove empty placeholder from active path",
                )
            )
    if write:
        for item in issues:
            append_jsonl(silent_failures_path(), item)
    return result_shape(
        ok=not any(item["severity"] == "fail" for item in issues),
        state_changed=write and bool(issues),
        created_ids=[item["issue_id"] for item in issues],
        warnings=[item for item in issues if item["severity"] == "warn"],
        blockers=[item for item in issues if item["severity"] == "fail"],
        next_required_action="fix_output_contract_or_explain_no_output" if issues else None,
        issues=issues,
        issue_count=len(issues),
    )
