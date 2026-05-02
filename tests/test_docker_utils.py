from __future__ import annotations

import subprocess
from types import SimpleNamespace

from otto.docker_utils import cleanup_ephemeral_mcp_containers, docker_compose_status, run_docker_command
from otto.docker_utils import classify_docker_probe_error


def test_classify_docker_probe_error_detects_wsl_integration_missing():
    assert classify_docker_probe_error("The command 'docker' could not be found in this WSL 2 distro.") == "command-not-found"


def test_run_docker_command_falls_back_to_powershell(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(list(command))
        if command[:2] == ["docker", "info"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="Access is denied.")
        return SimpleNamespace(returncode=0, stdout="Server Version: 28.3.2\n", stderr="")

    monkeypatch.setattr("otto.docker_utils.docker_available", lambda: True)
    monkeypatch.setattr("otto.docker_utils._docker_powershell_command", lambda args: ["pwsh", "-NoProfile", "-Command", "docker info"])
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_docker_command(["info"], timeout=5)

    assert result["ok"] is True
    assert result["transport"] == "powershell-fallback"
    assert result["fallback_used"] is True
    assert result["direct_status"] == "access-denied"
    assert calls[0] == ["docker", "info"]
    assert calls[1][:3] == ["pwsh", "-NoProfile", "-Command"]


def test_docker_compose_status_reports_fallback_transport(monkeypatch, tmp_path):
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    monkeypatch.setattr("otto.docker_utils.docker_available", lambda: True)
    monkeypatch.setattr("otto.docker_utils.load_docker_config", lambda: {"compose_file": str(compose_file)})
    monkeypatch.setattr(
        "otto.docker_utils.run_docker_command",
        lambda args, timeout=5: {
            "ok": True,
            "status": "ok",
            "transport": "powershell-fallback",
            "fallback_used": True,
            "direct_status": "access-denied",
            "stdout": '{"Name":"ob-otto-chromadb","State":"running"}\n',
            "stderr": "",
        },
    )

    result = docker_compose_status(probe=True)

    assert result["status"] == "ok"
    assert result["transport"] == "powershell-fallback"
    assert result["fallback_used"] is True
    assert result["services"][0]["Name"] == "ob-otto-chromadb"


def test_cleanup_ephemeral_mcp_containers_removes_only_run_containers(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_docker_command(args, timeout=5, allow_powershell_fallback=True):
        calls.append(list(args))
        if args[:2] == ["ps", "-a"]:
            return {
                "ok": True,
                "status": "ok",
                "transport": "direct",
                "stdout": (
                    "abc123\tobsidian-otto-obsidian-mcp-run-deadbeef\n"
                    "def456\tob-otto-obsidian-mcp\n"
                    "fed999\tobsidian-mcp-run-cafebabe\n"
                ),
                "stderr": "",
            }
        if args[:2] == ["rm", "-f"]:
            return {"ok": True, "status": "ok", "transport": "direct", "stdout": "\n".join(args[2:]), "stderr": ""}
        raise AssertionError(args)

    monkeypatch.setattr("otto.docker_utils.run_docker_command", fake_run_docker_command)

    result = cleanup_ephemeral_mcp_containers()

    assert result["ok"] is True
    assert result["removed"] == ["obsidian-otto-obsidian-mcp-run-deadbeef", "obsidian-mcp-run-cafebabe"]
    assert calls[1] == ["rm", "-f", "abc123", "fed999"]


def test_cleanup_ephemeral_mcp_containers_preserves_recent_running_when_ttl_enabled(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_docker_command(args, timeout=5, allow_powershell_fallback=True):
        calls.append(list(args))
        if args[:2] == ["ps", "-a"]:
            return {
                "ok": True,
                "status": "ok",
                "transport": "direct",
                "stdout": (
                    "abc123\tobsidian-otto-obsidian-mcp-run-old\n"
                    "def456\tobsidian-otto-obsidian-mcp-run-fresh\n"
                    "fed999\tobsidian-otto-obsidian-mcp-run-exited\n"
                ),
                "stderr": "",
            }
        if args[:1] == ["inspect"]:
            return {
                "ok": True,
                "status": "ok",
                "transport": "direct",
                "stdout": """
[
  {"Id": "abc123", "Created": "2026-04-28T00:00:00Z", "State": {"Running": true, "Status": "running"}},
  {"Id": "def456", "Created": "2026-04-28T00:05:30Z", "State": {"Running": true, "Status": "running"}},
  {"Id": "fed999", "Created": "2026-04-28T00:04:40Z", "State": {"Running": false, "Status": "exited"}}
]
""",
                "stderr": "",
            }
        if args[:2] == ["rm", "-f"]:
            return {"ok": True, "status": "ok", "transport": "direct", "stdout": "\n".join(args[2:]), "stderr": ""}
        raise AssertionError(args)

    class _FrozenDatetime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime, timezone

            return datetime(2026, 4, 28, 0, 10, 0, tzinfo=timezone.utc)

        @classmethod
        def fromisoformat(cls, value):
            from datetime import datetime

            return datetime.fromisoformat(value)

    monkeypatch.setattr("otto.docker_utils.run_docker_command", fake_run_docker_command)
    monkeypatch.setattr("otto.docker_utils.datetime", _FrozenDatetime)

    result = cleanup_ephemeral_mcp_containers(remove_running=True, running_ttl_seconds=300)

    assert result["ok"] is True
    assert result["removed"] == ["obsidian-otto-obsidian-mcp-run-old", "obsidian-otto-obsidian-mcp-run-exited"]
    assert result["skipped"] == ["obsidian-otto-obsidian-mcp-run-fresh"]
    assert calls[2] == ["rm", "-f", "abc123", "fed999"]
