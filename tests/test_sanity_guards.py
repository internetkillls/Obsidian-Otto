from __future__ import annotations

from types import SimpleNamespace

from otto.governance_utils import append_jsonl
from otto.sanity.ambiguity_scan import scan_ambiguities
from otto.sanity.dead_end_scan import scan_dead_ends
from otto.sanity.invariants import load_invariant_registry, load_sanity_policy
from otto.sanity.quarantine import quarantine_issue, quarantine_summary
from otto.sanity.repair_plan import generate_repair_plan, run_sanity_scan, sanity_summary
from otto.sanity.silent_failure_scan import scan_silent_failures
from otto.sanity.state_index import build_state_index
from otto.state import write_json


def _patch_paths(monkeypatch, tmp_path):
    paths = SimpleNamespace(state_root=tmp_path / "state", repo_root=tmp_path, vault_path=tmp_path / "vault")
    monkeypatch.setattr("otto.governance_utils.load_paths", lambda: paths)
    return paths


def test_sanity_policy_exists(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    policy = load_sanity_policy()
    registry = load_invariant_registry()

    assert policy["mode"] == "fail_closed"
    assert policy["default_behavior"]["auto_repair"] is False
    assert any(item["id"] == "INV_RAW_NEVER_QMD" for item in registry["invariants"])


def test_state_index_scans_known_state_files_and_runtime_surfaces(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    append_jsonl(
        paths.state_root / "memory" / "candidate_claims.jsonl",
        {
            "candidate_id": "cand_1",
            "state": "CANDIDATE",
            "kind": "handoff_note",
            "privacy": "private_reviewed",
            "evidence_refs": ["state/runtime/smoke_last.json"],
            "qmd_index_allowed": False,
            "vault_writeback_allowed": False,
        },
    )
    write_json(paths.state_root / "openclaw" / "heartbeat" / "otto_heartbeat_manifest.json", {"version": 1, "tools": []})
    write_json(paths.state_root / "qmd" / "qmd_manifest.json", {"version": 1, "sources": [], "generated_at": "now"})

    index = build_state_index()

    assert index["records"]["candidate_memory"]["count"] == 1
    assert index["records"]["openclaw_heartbeat_manifest"]["count"] == 1
    assert index["records"]["qmd_manifest"]["count"] == 1


def test_dead_end_scan_finds_candidate_without_review_route_and_allows_parked(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    append_jsonl(paths.state_root / "memory" / "candidate_claims.jsonl", {"candidate_id": "cand_dead", "state": "CANDIDATE", "kind": "handoff_note"})
    append_jsonl(paths.state_root / "memory" / "candidate_claims.jsonl", {"candidate_id": "cand_park", "state": "PARKED", "kind": "handoff_note"})

    result = scan_dead_ends()

    assert result["ok"] is False
    assert any(issue["record_id"] == "cand_dead" for issue in result["blockers"])
    assert not any(issue["record_id"] == "cand_park" for issue in result["issues"])


def test_silent_failure_detects_ok_without_expected_output(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    write_json(paths.state_root / "runtime" / "daily_loop_last.json", {"ok": True, "state": "DL3_CANDIDATE_GENERATION_READY"})

    result = scan_silent_failures()

    assert result["ok"] is False
    assert "state/human/daily_handoff.json" in result["blockers"][0]["missing_outputs"]


def test_ambiguity_scan_detects_duplicate_ids_and_conflicting_qmd_flags(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    append_jsonl(paths.state_root / "ingest" / "raw_index.jsonl", {"raw_id": "raw_1", "state": "RAW", "kind": "social_raw", "qmd_index_allowed": True})
    append_jsonl(paths.state_root / "memory" / "candidate_claims.jsonl", {"candidate_id": "dup_1", "state": "CANDIDATE", "kind": "handoff_note"})
    append_jsonl(paths.state_root / "memory" / "review_queue.jsonl", {"review_id": "dup_1", "state": "PENDING_REVIEW", "kind": "handoff_note", "item_id": "missing"})

    result = scan_ambiguities()

    assert result["ok"] is False
    assert any(issue["ambiguity_type"] == "duplicate_id" for issue in result["blockers"])
    assert any(issue.get("invariant_id") == "INV_RAW_NEVER_QMD" for issue in result["blockers"])


def test_quarantine_and_repair_plan_are_manual_only(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    issue = {
        "issue_id": "amb_1",
        "severity": "fail",
        "record_id": "ph_1",
        "record_kind": "profile_hypothesis",
        "problem": "profile hypothesis attempted to surface before review",
    }

    quarantined = quarantine_issue(issue)
    plan = generate_repair_plan(issues=[issue])

    assert quarantined["blocked_outputs"] == ["vault", "qmd", "openclaw_context"]
    assert quarantine_summary()["count"] == 1
    assert plan["auto_repair"] is False
    assert plan["actions"][0]["kind"] == "manual_resolution_required"


def test_sanity_scan_generates_summary(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    append_jsonl(paths.state_root / "memory" / "candidate_claims.jsonl", {"candidate_id": "cand_dead", "state": "CANDIDATE", "kind": "handoff_note"})

    result = run_sanity_scan(strict=False)
    summary = sanity_summary()

    assert result["ok"] is False
    assert result["strict_failures"] >= 1
    assert summary["state"] == "SAN1_DEAD_END_SILENT_FAILURE_AMBIGUITY_GUARD_READY"
    assert summary["repair_plan_available"] is True


def test_runtime_smoke_fails_on_sanity_fail(monkeypatch):
    from otto.orchestration.runtime_smoke import build_runtime_smoke

    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.build_wsl_health",
        lambda: {
            "identity": {"ok": True},
            "qmd": {"available": True},
            "openclaw": {"native": True},
            "docker": {"daemon_running": True},
        },
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.qmd_manifest_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.read_json", lambda path, default=None: {"last_success_at": "now"})
    monkeypatch.setattr("otto.orchestration.runtime_smoke._run_openclaw", lambda args, timeout_seconds=120, **kwargs: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.probe_openclaw_gateway", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.write_runtime_owner", lambda: {"owner": {"runtime_state": "S2C"}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.write_single_owner_lock", lambda: {"lock": {"ok": True}})
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.run_sanity_scan",
        lambda strict=False, write=True: {
            "ok": False,
            "strict_failures": 1,
            "warning_count": 0,
            "schema_audit": {"ok": True},
            "blockers": [{"issue_id": "amb_1"}],
            "repair_plan": {"actions": []},
        },
    )

    smoke = build_runtime_smoke(write=False)

    assert smoke["ok"] is False
    assert smoke["sanity"]["strict_failures"] == 1
