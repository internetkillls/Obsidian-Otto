from __future__ import annotations

import json
import subprocess
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

import otto.launcher_state as launcher_state_module
from otto.app.launcher import LauncherApp, classify_runtime, clear_stale_runtime_pid, render_action_description, resolve_action_spec
from otto.launcher_state import LauncherStateStore, mcp_configured, recommend_next_actions
from otto.infra import build_infra_result


def _make_case_dir(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_launcher_tests"
    root.mkdir(parents=True, exist_ok=True)
    case_dir = root / f"{name}_{uuid.uuid4().hex}"
    case_dir.mkdir(parents=True, exist_ok=False)
    return case_dir


def test_classify_runtime_states():
    case_dir = _make_case_dir("runtime_states")
    try:
        pid_file = case_dir / "runtime.pid"
        stopped = classify_runtime(pid_file)
        assert stopped.status == "STOPPED"
        assert stopped.pid is None

        pid_file.write_text("", encoding="utf-8")
        empty = classify_runtime(pid_file)
        assert empty.status == "STALE"

        pid_file.write_text("abc", encoding="utf-8")
        invalid = classify_runtime(pid_file)
        assert invalid.status == "STALE"

        pid_file.write_text("123", encoding="utf-8")
        running = classify_runtime(pid_file, process_checker=lambda pid: pid == 123)
        assert running.status == "RUNNING"
        assert running.pid == 123

        stale = classify_runtime(pid_file, process_checker=lambda pid: False)
        assert stale.status == "STALE"
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


def test_clear_stale_runtime_pid():
    case_dir = _make_case_dir("clear_pid")
    try:
        pid_file = case_dir / "runtime.pid"
        pid_file.write_text("999", encoding="utf-8")
        clear_stale_runtime_pid(pid_file)
        assert not pid_file.exists()
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


def test_launcher_state_store_writes_json():
    case_dir = _make_case_dir("state_store")
    try:
        store = LauncherStateStore(state_root=case_dir / "state")

        current_path = store.write_current(
            screen="home",
            runtime_status="STOPPED",
            runtime_pid=None,
            venv_is_ready=True,
            docker_cli_is_available=True,
            mcp_is_configured=True,
            recommended_next_actions=["Start the background runtime."],
            vault_host_path="C:\\vault",
        )
        current = json.loads(current_path.read_text(encoding="utf-8"))
        assert current["screen"] == "home"
        assert current["runtime_status"] == "STOPPED"
        assert current["docker_cli_available"] is True
        assert current["vault_host_path"] == "C:\\vault"

        action_path = store.record_action(
            action="start",
            screen="home",
            status="ok",
            exit_code=0,
            duration_ms=120,
            details={"runtime_status": "started"},
        )
        action = json.loads(action_path.read_text(encoding="utf-8"))
        assert action["action"] == "start"
        assert action["details"]["runtime_status"] == "started"

        mcp_path = store.record_mcp_run(
            mode="build_only",
            vault_host="C:\\vault",
            vault_path="/vault",
            build_exit=0,
            run_exit=None,
            notes=["build only"],
        )
        mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
        assert mcp["mode"] == "build_only"
        assert mcp["build_exit"] == 0
        assert mcp["notes"] == ["build only"]
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


def test_recommend_next_actions_prefers_runtime_repair():
    actions = recommend_next_actions(
        "STALE",
        screen="home",
        venv_is_ready=True,
        docker_cli_is_available=False,
        mcp_is_configured=False,
    )
    assert any("stale PID" in item for item in actions)
    assert any("Docker Desktop" in item for item in actions)


def test_mcp_configured_requires_enabled(monkeypatch):
    monkeypatch.setattr(launcher_state_module, "load_env_file", lambda path: {"OBSIDIAN_VAULT_HOST": "C:\\vault"})
    monkeypatch.setattr(launcher_state_module, "load_docker_config", lambda: {"enabled": False, "services": ["obsidian-mcp"]})
    assert mcp_configured() is False


def test_launch_mcp_respects_disabled_config(monkeypatch):
    app = LauncherApp()
    recorded: dict[str, object] = {}

    monkeypatch.setattr("otto.app.launcher.mcp_configured", lambda: False)
    monkeypatch.setattr(
        app.state,
        "record_mcp_run",
        lambda **kwargs: recorded.update(kwargs) or Path("state/launcher/mcp_last_run.json"),
    )

    result = app._action_launch_mcp(args=[], interactive=False)
    assert result.status == "error"
    assert result.details["reason"] == "mcp-disabled"
    assert recorded["mode"] == "stdio_run"
    assert "disabled in config/docker.yaml" in recorded["notes"]


def test_build_infra_result_survives_missing_docker(monkeypatch):
    monkeypatch.setattr("otto.infra.load_docker_config", lambda: {"services": ["postgres", "chromadb"]})
    monkeypatch.setattr("otto.infra.docker_available", lambda: False)
    monkeypatch.setattr("otto.infra.docker_daemon_running", lambda: False)

    result = build_infra_result()
    assert result.docker_available is False
    assert result.daemon_running is False
    assert result.running_services_known is False
    assert result.running_services == []


def test_build_infra_result_uses_docker_ps_when_available(monkeypatch):
    monkeypatch.setattr("otto.infra.load_docker_config", lambda: {"services": ["postgres", "chromadb", "obsidian-mcp"]})
    monkeypatch.setattr("otto.infra.docker_available", lambda: True)
    monkeypatch.setattr("otto.infra.docker_daemon_running", lambda: False)
    monkeypatch.setattr(
        "otto.infra._running_container_names",
        lambda: ({"ob-otto-postgres", "ob-otto-chromadb", "ob-otto-obsidian-mcp"}, None, "powershell-fallback"),
    )

    result = build_infra_result()
    assert result.daemon_running is True
    assert result.running_services_known is True
    assert result.docker_probe_status == "ok"
    assert result.docker_probe_transport == "powershell-fallback"
    assert result.running_services == ["postgres", "chromadb", "obsidian-mcp"]
    assert result.mcp_reachable is True


def test_build_infra_result_marks_probe_denied_without_fake_service_down(monkeypatch):
    monkeypatch.setattr("otto.infra.load_docker_config", lambda: {"services": ["postgres", "chromadb"]})
    monkeypatch.setattr("otto.infra.docker_available", lambda: True)
    monkeypatch.setattr("otto.infra.docker_daemon_running", lambda: False)
    monkeypatch.setattr("otto.infra._running_container_names", lambda: (None, "Access is denied.", "direct"))
    monkeypatch.setattr("otto.infra._postgres_reachable", lambda: True)

    result = build_infra_result()
    assert result.daemon_running is False
    assert result.running_services_known is False
    assert result.docker_probe_status == "access-denied"
    assert result.docker_probe_transport == "direct"
    assert result.running_services == []
    assert result.postgres_reachable is True


def test_compose_profile_args_follow_config():
    app = LauncherApp()
    app.root = Path.cwd()
    profiles = app._compose_profile_args()
    assert "--profile" in profiles
    assert "vector" in profiles


def test_advanced_menu_routes_mcp_to_ready_mode():
    app = LauncherApp()
    assert app._resolve_choice("advanced", "5") == "openclaw-gateway-probe"
    assert app._resolve_choice("advanced", "6") == "openclaw-plugin-reload"
    assert app._resolve_choice("advanced", "7") == "mcp-ready"
    assert app._resolve_choice("home", "8") == "training-queue"
    assert app._resolve_choice("home", "9") == "resolve-training-task"
    assert app._resolve_choice("home", "a") == "advanced"
    assert app._resolve_choice("home", "q") == "exit"


def test_launcher_action_catalog_resolves_wrapper_alias():
    spec = resolve_action_spec("reload-openclaw-gateway")
    assert spec is not None
    assert spec.name == "openclaw-gateway-restart"
    docker_probe = resolve_action_spec("docker-probe")
    assert docker_probe is not None
    assert docker_probe.name == "docker-probe"
    exit_code, text = render_action_description("status")
    assert exit_code == 0
    assert "Show status report" in text
    assert "status.bat" in text


def test_openclaw_probe_action_uses_http_bypass(monkeypatch):
    app = LauncherApp()
    monkeypatch.setattr(
        "otto.app.launcher.probe_openclaw_gateway",
        lambda timeout_seconds=5.0: {"ok": True, "reason": "gateway-http-healthy", "pids": [56944]},
    )

    result = app._action_openclaw_gateway_probe(args=[], interactive=False)

    assert result.status == "ok"
    assert result.details["reason"] == "gateway-http-healthy"


def test_openclaw_plugin_reload_action_defaults_to_soft_reload(monkeypatch):
    app = LauncherApp()
    captured: dict[str, object] = {}

    def fake_reload(wait_seconds=30, hard_restart=False):
        captured["wait_seconds"] = wait_seconds
        captured["hard_restart"] = hard_restart
        return {"ok": True, "reason": "plugin-surface-reloaded"}

    monkeypatch.setattr("otto.app.launcher.reload_openclaw_plugin_surface", fake_reload)

    result = app._action_openclaw_plugin_reload(args=[], interactive=False)

    assert result.status == "ok"
    assert captured["hard_restart"] is False


def test_docker_probe_action_reports_diagnostics(monkeypatch):
    app = LauncherApp()
    monkeypatch.setattr(
        "otto.app.launcher.docker_probe_diagnostics",
        lambda: {
            "docker_available": True,
            "daemon_running": True,
            "info_probe": {"transport": "powershell-fallback", "ok": True},
            "container_probe": {"transport": "powershell-fallback", "ok": True},
        },
    )

    result = app._action_docker_probe(args=[], interactive=False)

    assert result.status == "ok"
    assert result.details["daemon_running"] is True
    assert result.details["info_probe"]["transport"] == "powershell-fallback"


def test_mcp_ready_mode_does_not_attach_stdio(tmp_path, monkeypatch):
    app = LauncherApp()
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    app.paths = SimpleNamespace(repo_root=app.root, vault_path=vault_dir, state_root=tmp_path / "state")

    recorded: dict[str, object] = {}
    calls: list[list[str]] = []
    ps_counter = {"count": 0}

    class _Completed:
        def __init__(self, returncode: int = 0, stdout: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout

    def fake_run(command, *args, **kwargs):
        calls.append(list(command))
        if command[:3] == ["docker", "ps", "-q"]:
            ps_counter["count"] += 1
            return _Completed(stdout="" if ps_counter["count"] == 1 else "cid-123\n")
        return _Completed()

    def fake_popen(*args, **kwargs):
        raise AssertionError("stdio attach should not run in ready mode")

    monkeypatch.setattr("otto.app.launcher.mcp_configured", lambda: True)
    monkeypatch.setattr("otto.app.launcher.docker_available", lambda: True)
    monkeypatch.setattr("otto.app.launcher.docker_daemon_running", lambda: True)
    monkeypatch.setattr(
        "otto.app.launcher.load_env_file",
        lambda path: {
            "OBSIDIAN_VAULT_HOST": str(vault_dir),
            "OBSIDIAN_VAULT_PATH": "/vault",
        },
    )
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        app.state,
        "record_mcp_run",
        lambda **kwargs: recorded.update(kwargs) or Path(tmp_path / "state" / "launcher" / "mcp_last_run.json"),
    )

    result = app._action_mcp_ready(args=[], interactive=True)
    assert result.status == "ok"
    assert result.details["mode"] == "container_ready"
    assert recorded["mode"] == "container_ready"
    assert recorded["run_exit"] == 0
    assert any(command[:4] == ["docker", "compose", "-f", "docker-compose.yml"] and "build" in command for command in calls)
    assert any(command[:6] == ["docker", "compose", "-f", "docker-compose.yml", "--profile", "mcp"] for command in calls)


def test_training_queue_action_handles_empty_state(monkeypatch):
    app = LauncherApp()
    monkeypatch.setattr(
        app,
        "_mentor_snapshot",
        lambda: {
            "feedback_loop_ready": True,
            "active_probes": [],
            "pending_tasks": [],
            "completed_tasks": [],
            "skipped_tasks": [],
            "weakness_registry": {},
        },
    )

    result = app._action_training_queue(args=[], interactive=False)

    assert result.status == "ok"
    assert result.details["active_probes"] == 0
    assert result.details["pending_tasks"] == 0


def test_resolve_training_task_moves_note(tmp_path, monkeypatch):
    app = LauncherApp()
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    state_root = tmp_path / "state"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("OTTO_VAULT_PATH", str(vault_dir))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(state_root))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(artifacts_root))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))

    pending_dir = vault_dir / ".Otto-Realm" / "Training" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    pending_note = pending_dir / "2026-04-25-context-switching.md"
    pending_note.write_text(
        "\n".join(
            [
                "---",
                "task_id: mentor-probe-context-switching-re-entry-anchor-drill",
                "weakness_key: context-switching",
                "weakness: Context switching stays expensive; continuity must be carried by the system.",
                "title: re-entry anchor drill",
                "status: pending",
                "created_at: 2026-04-25T00:00:00+07:00",
                "resolved_at: ",
                "gap_type: application_gap",
                "probe_id: probe-context-switching-2026-04-25",
                "completion_signal: Move this note after review.",
                "---",
                "# Training Task: re-entry anchor drill",
                "",
                "## Prompt",
                "Write one anchor.",
            ]
        ),
        encoding="utf-8",
    )

    result = app._action_resolve_training_task(
        args=["mentor-probe-context-switching-re-entry-anchor-drill", "done"],
        interactive=False,
    )

    done_note = vault_dir / ".Otto-Realm" / "Training" / "done" / pending_note.name
    assert result.status == "ok"
    assert done_note.exists()
    assert not pending_note.exists()
    text = done_note.read_text(encoding="utf-8")
    assert "status: done" in text
    assert "resolved_at:" in text
