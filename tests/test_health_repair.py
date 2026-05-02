from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from otto.app.health_repair import run_health_repair


def _infra(configured: list[str], postgres_reachable: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        to_dict=lambda: {
            "configured_services": configured,
            "running_services": configured,
            "postgres_reachable": postgres_reachable,
        }
    )


def test_health_repair_cleans_repairs_postgres_and_restarts_gateway(monkeypatch, tmp_path):
    commands: list[list[str]] = []
    gateway_restarts: list[int] = []

    monkeypatch.setattr("otto.app.health_repair.docker_available", lambda: True)
    monkeypatch.setattr("otto.app.health_repair.docker_daemon_running", lambda: True)
    monkeypatch.setattr(
        "otto.app.health_repair.load_docker_config",
        lambda: {"services": ["postgres", "chromadb", "otto-indexer", "obsidian-mcp"], "mcp": {"profiles": ["mcp"]}},
    )
    monkeypatch.setattr(
        "otto.app.health_repair.cleanup_ephemeral_mcp_containers",
        lambda **kwargs: {"ok": True, "removed": [{"id": "abc", "name": "obsidian-mcp-run-abc"}], "kwargs": kwargs},
    )
    infra_sequence = [_infra(["postgres", "chromadb", "otto-indexer", "obsidian-mcp"], False), _infra(["postgres"], True)]
    monkeypatch.setattr("otto.app.health_repair.build_infra_result", lambda: infra_sequence.pop(0))
    monkeypatch.setattr("otto.app.health_repair.sync_openclaw_config", lambda: {"config_drift_free": True})
    monkeypatch.setattr("otto.app.health_repair.probe_openclaw_gateway", lambda timeout_seconds=2.0: {"ok": False})
    monkeypatch.setattr(
        "otto.app.health_repair.restart_openclaw_gateway",
        lambda wait_seconds=45: gateway_restarts.append(wait_seconds) or {"ok": True, "reason": "gateway-restarted"},
    )
    monkeypatch.setattr("otto.app.health_repair.init_pg_schema", lambda: None)
    monkeypatch.setattr("otto.app.health_repair.time.sleep", lambda seconds: None)
    monkeypatch.setattr("otto.app.health_repair._write_run_journal", lambda root, result: None)

    def fake_run_command(root: Path, command: list[str], timeout=None):
        commands.append(command)
        return {"command": command, "exit_code": 0}

    monkeypatch.setattr("otto.app.health_repair._run_command", fake_run_command)

    result = run_health_repair(root=tmp_path, fresh=False, ensure_runtime=False)

    assert result["ok"] is True
    assert commands[0] == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "--profile",
        "vector",
        "--profile",
        "worker",
        "--profile",
        "mcp",
        "up",
        "-d",
    ]
    assert ["docker", "compose", "-f", "docker-compose.yml", "restart", "postgres"] in commands
    assert gateway_restarts == [45]
    assert any(step["name"] == "mcp-clean" for step in result["steps"])


def test_fresh_everything_force_recreates_and_restarts_gateway(monkeypatch, tmp_path):
    commands: list[list[str]] = []
    runtime_calls: list[bool] = []

    monkeypatch.setattr("otto.app.health_repair.docker_available", lambda: True)
    monkeypatch.setattr("otto.app.health_repair.docker_daemon_running", lambda: True)
    monkeypatch.setattr("otto.app.health_repair.load_docker_config", lambda: {"services": ["postgres"], "mcp": {"profiles": []}})
    monkeypatch.setattr("otto.app.health_repair.cleanup_ephemeral_mcp_containers", lambda **kwargs: {"ok": True, "removed": [], "kwargs": kwargs})
    monkeypatch.setattr("otto.app.health_repair.build_infra_result", lambda: _infra(["postgres"], True))
    monkeypatch.setattr("otto.app.health_repair.sync_openclaw_config", lambda: {"config_drift_free": True})
    monkeypatch.setattr("otto.app.health_repair.probe_openclaw_gateway", lambda timeout_seconds=2.0: {"ok": True})
    monkeypatch.setattr("otto.app.health_repair.restart_openclaw_gateway", lambda wait_seconds=45: {"ok": True})
    monkeypatch.setattr(
        "otto.app.health_repair._ensure_runtime",
        lambda root, env: runtime_calls.append(True) or {"ok": True, "reason": "runtime-started", "pid": 123},
    )
    monkeypatch.setattr("otto.app.health_repair._write_run_journal", lambda root, result: None)

    def fake_run_command(root: Path, command: list[str], timeout=None):
        commands.append(command)
        return {"command": command, "exit_code": 0}

    monkeypatch.setattr("otto.app.health_repair._run_command", fake_run_command)

    result = run_health_repair(root=tmp_path, fresh=True)

    assert result["ok"] is True
    assert "--force-recreate" in commands[0]
    assert runtime_calls == [True]
    assert any(step["name"] == "openclaw-gateway-restart" for step in result["steps"])


def test_health_automation_installer_registers_three_hour_and_login_tasks(monkeypatch):
    from scripts.manage import install_health_automation as installer

    commands: list[list[str]] = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, cwd=None, capture_output=False, text=False, check=False):
        commands.append(list(command))
        return Completed()

    monkeypatch.setattr(installer.subprocess, "run", fake_run)

    results = installer.install_tasks()

    assert all(item["exit_code"] == 0 for item in results)
    assert commands[0][:8] == ["schtasks", "/Create", "/TN", installer.HEALTH_TASK, "/SC", "HOURLY", "/MO", "3"]
    assert "health-repair.bat" in commands[0][commands[0].index("/TR") + 1]
    assert commands[1][:6] == ["schtasks", "/Create", "/TN", installer.STARTUP_TASK, "/SC", "ONLOGON"]
    assert "fresh-everything.bat" in commands[1][commands[1].index("/TR") + 1]
