from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from otto.orchestration.cron_health import build_cron_health
from otto.orchestration.golden_path_smoke import run_golden_path_smoke
from otto.orchestration.health_scorecard import build_health_scorecard
from otto.orchestration.ops_health import default_ops_health_policy, run_ops_health, run_qmd_vault_roundtrip
from otto.orchestration.rollback_drill import run_rollback_drill


REPO_ROOT = Path(__file__).resolve().parents[1]


def _patch_paths(monkeypatch, tmp_path):
    paths = SimpleNamespace(
        repo_root=tmp_path,
        vault_path=tmp_path / "vault",
        sqlite_path=tmp_path / "sqlite.db",
        chroma_path=tmp_path / "chroma",
        bronze_root=tmp_path / "bronze",
        artifacts_root=tmp_path / "artifacts",
        logs_root=tmp_path / "logs",
        state_root=tmp_path / "state",
    )
    monkeypatch.setattr("otto.config.load_paths", lambda: paths)
    monkeypatch.setattr("otto.governance_utils.load_paths", lambda: paths)
    return paths


def test_wsl_launcher_files_exist_and_contracts_present():
    openclaw_launcher = REPO_ROOT / "scripts" / "wsl" / "openclaw-wsl.sh"
    otto_launcher = REPO_ROOT / "scripts" / "wsl" / "otto-cli-wsl.sh"

    assert openclaw_launcher.exists()
    assert otto_launcher.exists()

    openclaw_text = openclaw_launcher.read_text(encoding="utf-8")
    otto_text = otto_launcher.read_text(encoding="utf-8")

    assert "/home/joshu/.npm-global/bin/openclaw" in openclaw_text
    assert "PYTHONPATH=\"src\"" in otto_text


def test_docs_mentions_powershell_quoting_issue():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "bash -lc" in readme
    assert "PowerShell interpolation" in readme


def _base_ops_monkeypatch(monkeypatch):
    monkeypatch.setattr("otto.orchestration.ops_health.ensure_ops_health_policy", lambda: {"required_green_states": ["S4_WSL_LIVE", "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY", "SAN1_DEAD_END_SILENT_FAILURE_AMBIGUITY_GUARD_READY", "HB1_PROACTIVE_HEARTBEAT_ASSURANCE_READY", "HB2_TELEGRAM_HEARTBEAT_ROUTER_READY"]})
    monkeypatch.setattr("otto.orchestration.ops_health.build_runtime_smoke", lambda **kwargs: {"ok": True, "owner": {"runtime_state": "S4_WSL_LIVE"}, "gates": {"memory_policy_blocks_raw_to_qmd": True, "single_owner_lock": True}})
    monkeypatch.setattr("otto.orchestration.ops_health.build_soul_health", lambda: {"ok": True, "state": "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY"})
    monkeypatch.setattr("otto.orchestration.ops_health.run_sanity_scan", lambda **kwargs: {"ok": True, "state": "SAN1_DEAD_END_SILENT_FAILURE_AMBIGUITY_GUARD_READY", "strict_failures": 0})
    monkeypatch.setattr("otto.orchestration.ops_health.build_heartbeat_readiness", lambda **kwargs: {"ok": True, "state": "HB1_PROACTIVE_HEARTBEAT_ASSURANCE_READY", "optional_checks": {"visual_sources_declared": True}})
    monkeypatch.setattr("otto.orchestration.ops_health.heartbeat_router_test", lambda message: {"ok": True, "routed_to": "creative-heartbeat --dry-run --explain"})
    monkeypatch.setattr("otto.orchestration.ops_health.build_cron_health", lambda **kwargs: {"ok": True, "errors": [], "warnings": []})
    monkeypatch.setattr("otto.orchestration.ops_health.run_golden_path_smoke", lambda **kwargs: {"ok": True, "checks": {"a": True}})
    monkeypatch.setattr("otto.orchestration.ops_health.run_qmd_vault_roundtrip", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("otto.orchestration.ops_health.run_rollback_drill", lambda **kwargs: {"ok": True, "state_mutation_performed": False})
    monkeypatch.setattr("otto.orchestration.ops_health.build_health_scorecard", lambda **kwargs: {"overall": "green"})


def test_ops_health_fails_if_heartbeat_readiness_missing(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    _base_ops_monkeypatch(monkeypatch)
    monkeypatch.setattr("otto.orchestration.ops_health.build_heartbeat_readiness", lambda **kwargs: {"ok": False, "state": "HB1_BLOCKED", "optional_checks": {"visual_sources_declared": True}})

    result = run_ops_health(strict=True, write=False)
    assert result["ok"] is False
    assert "heartbeat_readiness_missing" in result["errors"]


def test_ops_health_fails_if_soul_health_missing(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    _base_ops_monkeypatch(monkeypatch)
    monkeypatch.setattr("otto.orchestration.ops_health.build_soul_health", lambda: {"ok": False, "state": "SOUL1_BLOCKED"})

    result = run_ops_health(strict=True, write=False)
    assert result["ok"] is False
    assert "soul_health_missing" in result["errors"]


def test_ops_health_fails_if_sanity_has_invariant_failure(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    _base_ops_monkeypatch(monkeypatch)
    monkeypatch.setattr("otto.orchestration.ops_health.run_sanity_scan", lambda **kwargs: {"ok": False, "state": "SAN1_DEAD_END_SILENT_FAILURE_AMBIGUITY_GUARD_READY", "strict_failures": 1})

    result = run_ops_health(strict=True, write=False)
    assert result["ok"] is False
    assert "sanity_invariant_failures" in result["errors"]


def test_golden_path_smoke_passes_routes(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    def _route(message: str):
        if "paper now" in message:
            return {"ok": True, "routed_to": "paper-onboarding --force-candidate"}
        if "bikin lagu" in message:
            return {"ok": True, "routed_to": "song-skeleton --dry-run"}
        if "weakness" in message:
            return {"ok": True, "routed_to": "blocker-experiment --dry-run", "warnings": ["support_context_only_non_diagnostic_for_audhd_bd"]}
        if "memento" in message:
            return {"ok": True, "routed_to": "memento-due", "actual_outputs": [], "no_output_reason": "no_quizworthy_blocks_due"}
        return {"ok": True, "routed_to": "creative-heartbeat --dry-run --explain"}

    monkeypatch.setattr("otto.orchestration.golden_path_smoke.heartbeat_router_test", _route)
    monkeypatch.setattr("otto.orchestration.golden_path_smoke.build_openclaw_context_pack", lambda **kwargs: {"soul": {"state": "ok"}, "creative_heartbeat_summary": {"state": "ok"}})

    result = run_golden_path_smoke(write=False)
    assert result["ok"] is True
    assert result["checks"]["telegram_paper_route"] is True
    assert result["checks"]["telegram_song_route"] is True
    assert result["checks"]["telegram_weakness_non_diagnostic"] is True


def test_qmd_vault_roundtrip_finds_reviewed_gold_after_reindex(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("otto.orchestration.ops_health.load_paths", lambda: paths)
    monkeypatch.setattr("otto.orchestration.ops_health.run_qmd_index_refresh", lambda timeout_seconds=60: {"ok": True})
    monkeypatch.setattr("otto.orchestration.ops_health.qmd_search", lambda query, max_results=8, timeout_seconds=60: {"ok": True, "hit_count": 1, "hits": [{"title": query}]})

    result = run_qmd_vault_roundtrip(strict=True, write=True)
    assert result["ok"] is True
    assert result["search_found"] is True
    assert result["query"] == "OPS1 Roundtrip Proof"
    assert "Memory-Tiers" in str(result["target_path"] or "")
    assert (paths.vault_path / ".Otto-Realm" / "Memory-Tiers" / "Ops" / "OPS1 Roundtrip Proof.md").exists()


def test_default_ops_policy_gate_order_does_not_require_hb2():
    policy = default_ops_health_policy()
    required = policy["required_green_states"]
    assert "HB1_PROACTIVE_HEARTBEAT_ASSURANCE_READY" in required
    assert "HB2_TELEGRAM_HEARTBEAT_ROUTER_READY" not in required


def test_cron_health_rejects_job_without_expected_output(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    planned = paths.state_root / "schedules" / "planned_jobs.jsonl"
    planned.parent.mkdir(parents=True, exist_ok=True)
    planned.write_text(
        json.dumps(
            {
                "name": "song_skeleton",
                "command": "/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-cli-wsl.sh song-skeleton --dry-run",
                "cadence": {"every_hours": 4},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("otto.orchestration.cron_health.verify_cron_plan", lambda: {"ok": True, "errors": [], "warnings": []})

    result = build_cron_health(write=False)
    assert result["ok"] is False
    assert any("expected_output_missing:song_skeleton" in item for item in result["errors"])


def test_rollback_drill_dry_run_does_not_mutate_state(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("otto.orchestration.rollback_drill.build_runtime_owner", lambda: {"runtime_state": "S4_WSL_LIVE"})
    monkeypatch.setattr("otto.orchestration.rollback_drill.build_single_owner_lock", lambda: {"ok": True})

    result = run_rollback_drill(dry_run=True, write=False)
    assert result["ok"] in {True, False}
    assert result["state_mutation_performed"] is False


def test_health_scorecard_writes_all_required_sections(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    scorecard = build_health_scorecard(
        runtime_smoke={"ok": True, "gates": {"gateway_live": True, "single_owner_lock": True, "qmd_native": True, "source_registry": True, "qmd_manifest": True, "memory_policy_blocks_raw_to_qmd": True, "reflection_policy_safe": True}},
        soul_health={"checks": {"soul_manifest_exists": True, "profile_snapshot_exists": True, "heartbeats_dir_exists": True}},
        sanity={"ok": True, "warning_count": 0},
        heartbeat_readiness={"optional_checks": {"visual_sources_declared": True}},
        cron_health={"ok": True, "planned_job_count": 1, "warnings": [], "errors": []},
        golden_paths={"checks": {"telegram_song_route": True, "telegram_paper_route": True, "memento_route": True, "telegram_weakness_route": True, "telegram_weakness_non_diagnostic": True}},
        rollback={"ok": True, "state_mutation_performed": False},
        roundtrip={"ok": True, "gold_present": True, "vault_writeback_present": True},
        write=True,
    )

    for key in ["runtime", "memory", "soul", "creative", "cron", "safety", "rollback"]:
        assert key in scorecard
