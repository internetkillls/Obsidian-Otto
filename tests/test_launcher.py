from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import otto.launcher_state as launcher_state_module
from otto.app.launcher import LauncherApp, classify_runtime, clear_stale_runtime_pid
from otto.launcher_state import LauncherStateStore, mcp_configured, recommend_next_actions


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
            vault_path="C:\\vault",
        )
        current = json.loads(current_path.read_text(encoding="utf-8"))
        assert current["screen"] == "home"
        assert current["runtime_status"] == "STOPPED"
        assert current["docker_cli_available"] is True

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
