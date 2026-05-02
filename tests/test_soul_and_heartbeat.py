from __future__ import annotations

import json
from types import SimpleNamespace

from otto.adapters.openclaw.context_pack import build_openclaw_context_pack
from otto.adapters.qmd.manifest import build_qmd_manifest
from otto.memory.source_registry import default_source_registry, load_source_registry
from otto.orchestration.heartbeat_readiness import build_heartbeat_readiness
from otto.orchestration.runtime_smoke import build_runtime_smoke
from otto.soul.health import build_soul_health
from otto.soul.manifest import build_soul_manifest
from otto.soul.rehydrate import run_soul_rehydrate
from otto.soul.scope import build_soul_scope


def _patch_paths(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    state = tmp_path / "state"
    artifacts = tmp_path / "artifacts"
    logs = tmp_path / "logs"
    paths = SimpleNamespace(
        repo_root=tmp_path,
        vault_path=vault,
        sqlite_path=tmp_path / "sqlite.db",
        chroma_path=tmp_path / "chroma",
        bronze_root=tmp_path / "bronze",
        artifacts_root=artifacts,
        logs_root=logs,
        state_root=state,
    )
    monkeypatch.setattr("otto.config.load_paths", lambda: paths)
    monkeypatch.setattr("otto.governance_utils.load_paths", lambda: paths)
    monkeypatch.setattr("otto.soul.paths.load_paths", lambda: paths)
    monkeypatch.setattr("otto.soul.paths.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "otto.soul.manifest.infer_soul_roots",
        lambda: SimpleNamespace(
            repo_root_windows=str(tmp_path).replace("\\", "/"),
            repo_root_wsl="/mnt/c/tmp/repo",
            vault_root_windows=str(vault).replace("\\", "/"),
            vault_root_wsl=str(vault).replace("\\", "/"),
        ),
    )
    return paths


def test_soul_scope_includes_root_control_docs_even_if_active_scope_excludes():
    scope = build_soul_scope()
    assert "CLAUDE.md" in scope["include_root_control_docs"]
    assert ".Otto-Realm/Brain/**/*.md" in scope["include_vault_identity_globs"]
    assert scope["raw_vault_full_scan_enabled"] is False


def test_soul_manifest_has_repo_and_vault_roots():
    manifest = build_soul_manifest()
    assert manifest["repo_root"]["windows"] == "C:/Users/joshu/Obsidian-Otto"
    assert manifest["repo_root"]["wsl"] == "/mnt/c/Users/joshu/Obsidian-Otto"
    assert manifest["vault_root"]["windows"] == "C:/Users/joshu/Josh Obsidian"
    assert manifest["vault_root"]["wsl"] == "/mnt/c/Users/joshu/Josh Obsidian"


def test_soul_health_fails_when_profile_snapshot_missing(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    (paths.vault_path / ".Otto-Realm" / "Heartbeats").mkdir(parents=True, exist_ok=True)
    health = build_soul_health()
    assert health["ok"] is False
    assert "profile_snapshot_missing" in health["failures"]


def test_source_registry_adds_control_plane_identity():
    registry = default_source_registry()
    ids = [item["id"] for item in registry["sources"]]
    assert "otto_control_plane_identity" in ids
    control = next(item for item in registry["sources"] if item["id"] == "otto_control_plane_identity")
    assert "AGENTS.md" in control["include_globs"]


def test_source_registry_adds_otto_realm_identity():
    registry = default_source_registry()
    ids = [item["id"] for item in registry["sources"]]
    assert "otto_realm_identity" in ids


def test_qmd_manifest_includes_soul_sources():
    manifest = build_qmd_manifest(default_source_registry())
    groups = manifest["source_groups"]
    assert groups["control_plane_identity"]["present"] is True
    assert groups["soul_identity"]["present"] is True


def test_context_pack_includes_soul_health_summary(monkeypatch):
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.build_runtime_owner", lambda: {"runtime_state": "S2C_WSL_SHADOW_GATEWAY_READY"})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.build_qmd_index_health", lambda: {"ok": True, "source_count": 2})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.qmd_manifest_health", lambda: {"ok": True, "source_count": 2})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.build_single_owner_lock", lambda: {"ok": True, "ubuntu_shadow_telegram_disabled": True})
    monkeypatch.setattr("otto.adapters.openclaw.context_pack.read_json", lambda path, default=None: {"ok": True, "port": 18790})
    monkeypatch.setattr(
        "otto.adapters.openclaw.context_pack.build_soul_health",
        lambda: {
            "ok": True,
            "state": "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY",
            "checks": {"profile_snapshot_exists": True, "heartbeats_dir_exists": True, "brain_dir_exists": True},
            "warnings": [],
            "failures": [],
            "qmd_soul_audit": {"ok": True},
        },
    )
    pack = build_openclaw_context_pack(task="test")
    assert pack["runtime"]["telegram"] == "disabled"
    assert pack["soul"]["state"] == "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY"
    assert "creative_heartbeat_summary" in pack


def test_runtime_smoke_fails_when_wsl_live_without_soul_section(monkeypatch, tmp_path):
    monkeypatch.setattr("otto.orchestration.runtime_smoke.runtime_smoke_path", lambda: tmp_path / "smoke_last.json")
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_wsl_health", lambda: {"identity": {"ok": True}, "qmd": {"available": True}, "openclaw": {"native": True}, "docker": {"daemon_running": True}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke._build_wsl_runtime_probe", lambda: {"ok": True, "identity": {"ok": True}, "qmd": {"available": True}, "openclaw": {"native": True}, "docker": {"daemon_running": True}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.qmd_manifest_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.read_json", lambda path, default=None: {"last_success_at": "now"})
    monkeypatch.setattr("otto.orchestration.runtime_smoke._run_openclaw", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.probe_openclaw_gateway", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.write_runtime_owner", lambda: {"owner": {"runtime_state": "S4_WSL_LIVE", "gateway_owner": "ubuntu_openclaw", "windows_openclaw": {"telegram_enabled": False}, "ubuntu_openclaw": {"telegram_enabled": True}}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_runtime_owner", lambda: {"runtime_state": "S4_WSL_LIVE"})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.write_single_owner_lock", lambda: {"lock": {"ok": True}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_single_owner_lock", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke._load_runtime_config_preview", lambda runtime_state: {"channels": {"telegram": {"enabled": True}}, "gateway": {"auth": {"mode": "token"}}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.load_daily_loop_policy", lambda: {"version": 1, "default_behavior": {"write_to_vault": False}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.load_human_loop_policy", lambda: {"role": "partner_mentor", "not_roles": ["diagnostician"]})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.load_reflection_policy", lambda: {"default_behavior": {"auto_promote_to_gold": False}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.load_artifact_type_policy", lambda: {"version": 1})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.load_songforge_policy", lambda: {"version": 1})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.load_vocal_chop_policy", lambda: {"vocal_chop_policy": {"youtube_download_allowed": False}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.load_creative_heartbeat_policy", lambda: {"safety": {"auto_publish": False}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_midi_spec", lambda payload: {"ok": True})
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.build_soul_health",
        lambda: {
            "checks": {
                "soul_manifest_exists": True,
                "repo_root_wsl_exists": True,
                "vault_root_wsl_exists": True,
                "otto_realm_exists": False,
                "profile_snapshot_exists": False,
                "heartbeats_dir_exists": False,
                "brain_dir_exists": False,
                "qmd_manifest_includes_soul_sources": False,
                "qmd_search_finds_profile_or_heartbeat": False,
            }
        },
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_heartbeat_readiness", lambda **kwargs: {"ok": True, "discovery": {}, "dry_run_checks": {}, "bridge_checks": {}, "soul_agent_skill_checks": {}, "cron_checks": {}, "safety_checks": {}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.run_sanity_scan", lambda **kwargs: {"ok": True, "strict_failures": 0, "warning_count": 0, "schema_audit": {"ok": True}, "blockers": [], "repair_plan": {"actions": []}})

    smoke = build_runtime_smoke(write=True)
    assert smoke["ok"] is False
    assert smoke["gates"]["soul_otto_realm_exists_live"] is False


def test_soul_rehydrate_dry_run_does_not_write(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    result = run_soul_rehydrate(dry_run=True, write=False)
    assert result["dry_run"] is True
    assert not (paths.state_root / "soul" / "soul_rehydrate_last.json").exists()


def test_soul_rehydrate_write_updates_manifest_registry_context(monkeypatch, tmp_path):
    paths = _patch_paths(monkeypatch, tmp_path)
    (paths.vault_path / ".Otto-Realm" / "Heartbeats").mkdir(parents=True, exist_ok=True)
    (paths.vault_path / ".Otto-Realm" / "Brain").mkdir(parents=True, exist_ok=True)
    (paths.vault_path / ".Otto-Realm" / "Profile Snapshot.md").write_text("ok", encoding="utf-8")

    result = run_soul_rehydrate(dry_run=False, write=True)
    assert result["write"] is True
    assert (paths.state_root / "soul" / "soul_manifest.json").exists()
    assert (paths.state_root / "soul" / "soul_health.json").exists()
    registry = load_source_registry(paths.state_root / "memory" / "source_registry.json")
    ids = [item["id"] for item in registry["sources"]]
    assert "otto_control_plane_identity" in ids
    assert "otto_realm_identity" in ids


def test_heartbeat_readiness_fails_if_song_skeleton_command_missing(monkeypatch):
    monkeypatch.setattr(
        "otto.orchestration.heartbeat_readiness._command_registry",
        lambda: {
            "creative-heartbeat --dry-run": lambda: {"ok": True, "song_skeleton": {}},
            "paper-onboarding --dry-run": lambda: {"ok": True, "pack": {}},
            "memento-due": lambda: {"ok": True, "quiz_count": 0, "no_output_reason": "none"},
            "blocker-experiment --dry-run": lambda: {"ok": True, "tasks": [{}]},
            "visual-inspo-query --dry-run": lambda: {"ok": True, "visual_query": "q"},
            "openclaw-context-pack": lambda: {"ok": True, "context_pack": {"creative_heartbeat_summary": {}}},
            "openclaw-tool-manifest": lambda: {"ok": True, "manifest": {"tools": []}},
            "runtime-smoke": lambda: {"ok": True},
            "soul-health": lambda: {"ok": True},
            "qmd-soul-audit": lambda: {"ok": True},
        },
    )
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_openclaw_tool_manifest", lambda: {"tools": [{"name": name} for name in ["otto.heartbeat", "otto.song_skeleton_next", "otto.paper_onboarding_next", "otto.memento_due", "otto.blocker_experiment_next", "otto.visual_inspo_query"]]})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.probe_openclaw_gateway", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_openclaw_context_pack", lambda **kwargs: {"creative_heartbeat_summary": {}, "soul": {}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.qmd_manifest_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_soul_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_qmd_soul_audit", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_skill_hierarchy", lambda: {"domains": {"x": {}}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_blocker_map", lambda: {"blockers": [{}]})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.soul_v2_path", lambda: SimpleNamespace(exists=lambda: True))
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_creative_heartbeat_policy", lambda: {"safety": {"auto_publish": False, "auto_qmd_index_raw": False, "auto_download_youtube": False, "auto_enable_telegram": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_songforge_policy", lambda: {"safety": {"auto_qmd_index": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_visual_inspo_policy", lambda: {"visual_inspo_policy": {"sources": ["e-flux"]}})

    readiness = build_heartbeat_readiness(strict=True, write=False, run_dry_runs=False)
    assert readiness["ok"] is False
    assert readiness["discovery"]["song-skeleton --dry-run"] is False


def test_heartbeat_readiness_fails_if_paper_onboarding_command_missing(monkeypatch):
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
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_creative_heartbeat_policy", lambda: {"safety": {"auto_publish": False, "auto_qmd_index_raw": False, "auto_download_youtube": False, "auto_enable_telegram": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_songforge_policy", lambda: {"safety": {"auto_qmd_index": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_visual_inspo_policy", lambda: {"visual_inspo_policy": {"sources": []}})

    readiness = build_heartbeat_readiness(strict=True, write=False, run_dry_runs=False)
    assert readiness["ok"] is False
    assert readiness["discovery"]["paper-onboarding --dry-run"] is False


def test_heartbeat_readiness_fails_if_creative_heartbeat_missing_output_and_reason(monkeypatch):
    registry = {
        "creative-heartbeat --dry-run": lambda: {"ok": True},
        "song-skeleton --dry-run": lambda: {"ok": True, "skeleton": {}},
        "paper-onboarding --dry-run": lambda: {"ok": True, "pack": {}},
        "memento-due": lambda: {"ok": True, "quiz_count": 0, "no_output_reason": "none"},
        "blocker-experiment --dry-run": lambda: {"ok": True, "tasks": [{}]},
        "visual-inspo-query --dry-run": lambda: {"ok": True, "visual_query": "q"},
        "openclaw-context-pack": lambda: {"ok": True, "context_pack": {"creative_heartbeat_summary": {}, "soul": {}}},
        "openclaw-tool-manifest": lambda: {"ok": True, "manifest": {"tools": []}},
        "runtime-smoke": lambda: {"ok": True},
        "soul-health": lambda: {"ok": True},
        "qmd-soul-audit": lambda: {"ok": True},
    }
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness._command_registry", lambda: registry)
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_openclaw_tool_manifest", lambda: {"tools": [{"name": name} for name in ["otto.heartbeat", "otto.song_skeleton_next", "otto.paper_onboarding_next", "otto.memento_due", "otto.blocker_experiment_next", "otto.visual_inspo_query"]]})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.probe_openclaw_gateway", lambda **kwargs: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_openclaw_context_pack", lambda **kwargs: {"creative_heartbeat_summary": {}, "soul": {}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.qmd_manifest_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_soul_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.build_qmd_soul_audit", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_skill_hierarchy", lambda: {"domains": {"x": {}}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_blocker_map", lambda: {"blockers": [{}]})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.soul_v2_path", lambda: SimpleNamespace(exists=lambda: True))
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_creative_heartbeat_policy", lambda: {"safety": {"auto_publish": False, "auto_qmd_index_raw": False, "auto_download_youtube": False, "auto_enable_telegram": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_songforge_policy", lambda: {"safety": {"auto_qmd_index": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_visual_inspo_policy", lambda: {"visual_inspo_policy": {"sources": ["e-flux"]}})

    readiness = build_heartbeat_readiness(strict=True, write=False, run_dry_runs=True)
    assert readiness["ok"] is False
    assert readiness["dry_run_checks"]["creative-heartbeat --dry-run"] is False


def test_cron_plan_creates_jobs_with_expected_cadence():
    from otto.orchestration.cron_plan import build_planned_jobs

    jobs = build_planned_jobs()
    assert any(job["name"] == "song_skeleton" and job["cadence"]["every_hours"] == 4 for job in jobs)
    assert any(job["name"] == "paper_onboarding" and job["cadence"]["policy_window_hours"] == [4, 6] for job in jobs)
    assert any(job["name"] == "memento_due" and job["cadence"]["every_hours"] == 8 for job in jobs)


def test_cron_verify_rejects_auto_publish_settings(monkeypatch, tmp_path):
    from otto.orchestration.cron_plan import write_cron_plan
    from otto.orchestration.cron_render import verify_cron_plan

    _patch_paths(monkeypatch, tmp_path)
    write_cron_plan()
    monkeypatch.setattr("otto.orchestration.cron_render.load_creative_heartbeat_policy", lambda: {"safety": {"auto_publish": True, "auto_qmd_index_raw": False, "auto_download_youtube": False, "auto_enable_telegram": False}})
    monkeypatch.setattr("otto.orchestration.cron_render.load_paper_onboarding_policy", lambda: {"paper_onboarding_policy": {"auto_vault_write": False}})
    monkeypatch.setattr("otto.orchestration.cron_render.load_songforge_policy", lambda: {"safety": {"auto_qmd_index": False}})
    monkeypatch.setattr("otto.orchestration.cron_render.load_memento_policy", lambda: {"memento_policy": {"enabled": True}})

    result = verify_cron_plan()
    assert result["ok"] is False
    assert "unsafe_setting:auto_publish" in result["errors"]


def test_heartbeat_readiness_reports_soul_or_skill_missing_as_blocker(monkeypatch):
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
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_creative_heartbeat_policy", lambda: {"safety": {"auto_publish": False, "auto_qmd_index_raw": False, "auto_download_youtube": False, "auto_enable_telegram": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_songforge_policy", lambda: {"safety": {"auto_qmd_index": False}})
    monkeypatch.setattr("otto.orchestration.heartbeat_readiness.load_visual_inspo_policy", lambda: {"visual_inspo_policy": {"sources": ["e-flux"]}})

    readiness = build_heartbeat_readiness(strict=True, write=False, run_dry_runs=False)
    assert readiness["ok"] is False
    assert readiness["soul_agent_skill_checks"]["soul_health_ok"] is False


def test_cron_render_disabled_does_not_install_os_cron():
    from otto.orchestration.cron_render import verify_cron_plan

    result = verify_cron_plan()
    assert result["os_cron_installed"] is False
