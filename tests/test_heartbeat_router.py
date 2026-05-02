from __future__ import annotations

from types import SimpleNamespace

from otto.adapters.openclaw.context_pack import build_openclaw_context_pack
from otto.adapters.openclaw.tool_payloads import build_openclaw_tool_manifest
from otto.orchestration.heartbeat_readiness import build_heartbeat_readiness
from otto.orchestration.kairos_chat import KAIROSChatHandler
from otto.orchestration.telegram_router import heartbeat_router_test


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


def test_paper_cron_question_routes_to_paper_heartbeat_not_generic(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    result = heartbeat_router_test("Kamu punya cron paper gak?")
    assert result["ok"] is True
    assert result["routed_to"] in {"paper-heartbeat-status", "paper-onboarding --dry-run"}


def test_paper_now_routes_to_force_candidate(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    result = heartbeat_router_test("paper now")
    assert result["ok"] is True
    assert result["routed_to"] == "paper-onboarding --force-candidate"


def test_bikin_lagu_routes_to_song_skeleton(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    result = heartbeat_router_test("bikin lagu")
    assert result["ok"] is True
    assert result["routed_to"] == "song-skeleton --dry-run"


def test_weakness_routes_to_blocker_and_support_context_warning(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    result = heartbeat_router_test("cari weakness point saya")
    assert result["ok"] is True
    assert result["routed_to"] == "blocker-experiment --dry-run"
    assert "support_context_only_non_diagnostic_for_audhd_bd" in result["warnings"]


def test_memento_routes_to_due_queue(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    result = heartbeat_router_test("memento")
    assert result["ok"] is True
    assert result["routed_to"] == "memento-due"


def test_heartbeat_now_routes_to_creative_heartbeat(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    result = heartbeat_router_test("heartbeat now")
    assert result["ok"] is True
    assert result["routed_to"] == "creative-heartbeat --dry-run --explain"


def test_due_jobs_are_not_suppressed_by_legacy_no_action_path(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    handler = KAIROSChatHandler()
    result = handler.handle("halo")
    assert result["ok"] is True
    assert result["routed_to"] == "scheduled_due_jobs"


def test_routed_command_with_no_output_has_reason(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    result = heartbeat_router_test("memento")
    assert result["ok"] is True
    assert (result["actual_outputs"] or result["no_output_reason"]) is not None
    if not result["actual_outputs"]:
        assert isinstance(result["no_output_reason"], str) and result["no_output_reason"]


def test_openclaw_tool_manifest_includes_heartbeat_tools_and_readiness():
    manifest = build_openclaw_tool_manifest()
    names = {tool["name"] for tool in manifest["tools"]}
    assert "otto.heartbeat" in names
    assert "otto.song_skeleton_next" in names
    assert "otto.paper_onboarding_next" in names
    assert "otto.memento_due" in names
    assert "otto.blocker_experiment_next" in names
    assert "otto.visual_inspo_query" in names
    assert "otto.feedback_ingest" in names
    assert "otto.heartbeat_readiness" in names


def test_context_pack_includes_creative_heartbeat_summary(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.build_runtime_owner", lambda: {"runtime_state": "S2C_WSL_SHADOW_GATEWAY_READY"})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.build_qmd_index_health", lambda: {"ok": True, "source_count": 2})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.qmd_manifest_health", lambda: {"ok": True, "source_count": 2})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.build_single_owner_lock", lambda: {"ok": True, "ubuntu_shadow_telegram_disabled": True})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.build_soul_health", lambda: {"ok": True, "state": "SOUL1", "checks": {"profile_snapshot_exists": True, "heartbeats_dir_exists": True, "brain_dir_exists": True}, "warnings": [], "failures": [], "qmd_soul_audit": {"ok": True}})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.read_json", lambda path, default=None: {"ok": True})
    pack = build_openclaw_context_pack(task="hb2")
    summary = pack["creative_heartbeat_summary"]
    assert "heartbeat_readiness_state" in summary
    assert "next_due_jobs" in summary
    assert "memento_due_count" in summary


def test_heartbeat_readiness_strict_fails_if_paper_or_song_command_missing(monkeypatch):
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness._command_registry", lambda: {})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_openclaw_tool_manifest", lambda: {"tools": []})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.probe_openclaw_gateway", lambda **kwargs: {"ok": False})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_openclaw_context_pack", lambda **kwargs: {})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_qmd_index_health", lambda: {"ok": False})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.validate_source_registry", lambda: {"ok": False})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.qmd_manifest_health", lambda: {"ok": False})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_soul_health", lambda: {"ok": False})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_qmd_soul_audit", lambda: {"ok": False})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_skill_hierarchy", lambda: {"domains": {}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_blocker_map", lambda: {"blockers": []})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.soul_v2_path", lambda: SimpleNamespace(exists=lambda: False))
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_creative_heartbeat_policy", lambda: {"safety": {"auto_publish": False, "auto_qmd_index_raw": False, "auto_download_youtube": False, "auto_enable_telegram": False, "auto_vault_write_unreviewed": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_songforge_policy", lambda: {"safety": {"auto_qmd_index": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_visual_inspo_policy", lambda: {"visual_inspo_policy": {"sources": ["e-flux"]}})
    readiness = build_heartbeat_readiness(strict=True, write=False, run_dry_runs=False)
    assert readiness["ok"] is False
    assert readiness["discovery"]["paper-onboarding --dry-run"] is False
    assert readiness["discovery"]["song-skeleton --dry-run"] is False


def test_heartbeat_readiness_strict_passes_when_tools_and_dry_runs_available(monkeypatch):
    registry = {
        "creative-heartbeat --dry-run": lambda: {"ok": True, "song_skeleton": {"id": "x"}, "paper_onboarding": {"id": "x"}, "memento_due": {"quiz_count": 0}},
        "song-skeleton --dry-run": lambda: {"ok": True, "skeleton": {"song_skeleton_id": "x"}},
        "paper-onboarding --dry-run": lambda: {"ok": True, "pack": {"pack_id": "x"}},
        "memento-due": lambda: {"ok": True, "quiz_count": 0, "no_output_reason": "no_blocks_yet"},
        "blocker-experiment --dry-run": lambda: {"ok": True, "tasks": [{"training_task_id": "x"}]},
        "visual-inspo-query --dry-run": lambda: {"ok": True, "visual_query": "q"},
        "openclaw-context-pack": lambda: {"ok": True, "context_pack": {"creative_heartbeat_summary": {}, "soul": {}}},
        "openclaw-tool-manifest": lambda: {"ok": True, "manifest": {"tools": []}},
        "runtime-smoke": lambda: {"ok": True},
        "soul-health": lambda: {"ok": True},
        "qmd-soul-audit": lambda: {"ok": True},
    }
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness._command_registry", lambda: registry)
    tool_names = [
        "otto.heartbeat",
        "otto.song_skeleton_next",
        "otto.paper_onboarding_next",
        "otto.memento_due",
        "otto.blocker_experiment_next",
        "otto.visual_inspo_query",
        "otto.feedback_ingest",
        "otto.heartbeat_readiness",
    ]
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_openclaw_tool_manifest", lambda: {"tools": [{"name": name} for name in tool_names]})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.probe_openclaw_gateway", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_openclaw_context_pack", lambda **kwargs: {"creative_heartbeat_summary": {"state": "ok"}, "soul": {"state": "ok"}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.qmd_manifest_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_soul_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_qmd_soul_audit", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_skill_hierarchy", lambda: {"domains": {"x": {}}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_blocker_map", lambda: {"blockers": [{}]})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.soul_v2_path", lambda: SimpleNamespace(exists=lambda: True))
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_creative_heartbeat_policy", lambda: {"safety": {"auto_publish": False, "auto_qmd_index_raw": False, "auto_download_youtube": False, "auto_enable_telegram": False, "auto_vault_write_unreviewed": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_songforge_policy", lambda: {"safety": {"auto_qmd_index": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_visual_inspo_policy", lambda: {"visual_inspo_policy": {"sources": ["e-flux"]}})
    monkeypatch.setattr(
        "otto.orchestration.heartbeat_readiness.build_planned_jobs",
        lambda: [
            {"name": "song_skeleton", "cadence": {"every_hours": 4}},
            {"name": "paper_onboarding", "cadence": {"policy_window_hours": [4, 6]}},
            {"name": "blocker_experiment", "cadence": {"every_hours": 24}},
            {"name": "memento_due", "cadence": {"every_hours": 8}},
        ],
    )
    readiness = build_heartbeat_readiness(strict=True, write=False, run_dry_runs=True)
    assert readiness["ok"] is True
