from __future__ import annotations

from types import SimpleNamespace

from otto.wsl_support import build_wsl_health, classify_openclaw_origin


def test_classify_openclaw_origin_accepts_native_linux_paths():
    assert classify_openclaw_origin("/usr/local/bin/openclaw") == "native-linux"
    assert classify_openclaw_origin("/home/joshu/.npm-global/bin/openclaw") == "native-linux"


def test_classify_openclaw_origin_rejects_windows_paths():
    assert classify_openclaw_origin("/mnt/c/Users/joshu/AppData/Roaming/npm/openclaw") == "windows-path"
    assert classify_openclaw_origin("/mnt/c/Users/joshu/AppData/Local/Microsoft/WindowsApps/openclaw") == "windows-path"
    assert classify_openclaw_origin("/mnt/c/Users/joshu/bin/openclaw.exe") == "windows-path"
    assert classify_openclaw_origin(r"C:\Users\joshu\AppData\Roaming\npm\openclaw") == "windows-path"


def test_build_wsl_health_reports_docker_recommendation(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    paths = SimpleNamespace(repo_root=tmp_path, vault_path=vault)

    monkeypatch.setattr("otto.wsl_support.load_paths", lambda: paths)
    monkeypatch.setattr("otto.wsl_support.is_wsl", lambda: True)
    monkeypatch.setattr(
        "otto.wsl_support._identity_probe",
        lambda: {
            "ok": True,
            "required": True,
            "expected_user": "joshu",
            "user": "joshu",
            "uid": 1000,
            "home": "/home/joshu",
            "expected_home": "/home/joshu",
            "is_root": False,
        },
    )
    monkeypatch.setattr(
        "otto.wsl_support._qmd_probe",
        lambda: {"available": True, "status": "ok", "command": "/usr/bin/qmd", "version": "2.1.0"},
    )
    monkeypatch.setattr(
        "otto.wsl_support._openclaw_probe",
        lambda: {
            "available": True,
            "native": True,
            "origin": "native-linux",
            "status": "ok",
            "command": "/usr/local/bin/openclaw",
            "version": "OpenClaw 2026.4.26",
        },
    )
    monkeypatch.setattr(
        "otto.wsl_support.build_qmd_index_health",
        lambda: {"ok": True, "source_count": 6},
    )
    monkeypatch.setattr(
        "otto.wsl_support.docker_probe_diagnostics",
        lambda: {"docker_available": False, "daemon_running": False},
    )
    monkeypatch.setattr(
        "otto.wsl_support.docker_compose_status",
        lambda probe=True: {"available": False, "status": "docker-not-found", "services": []},
    )

    health = build_wsl_health()

    assert health["ok"] is False
    assert health["paths"]["repo_readable"] is True
    assert health["paths"]["vault_readable"] is True
    assert "Enable Docker Desktop WSL integration" in health["recommendations"][0]


def test_build_wsl_health_fails_when_openclaw_resolves_to_windows_path(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    paths = SimpleNamespace(repo_root=tmp_path, vault_path=vault)

    monkeypatch.setattr("otto.wsl_support.load_paths", lambda: paths)
    monkeypatch.setattr("otto.wsl_support.is_wsl", lambda: True)
    monkeypatch.setattr(
        "otto.wsl_support._identity_probe",
        lambda: {
            "ok": True,
            "required": True,
            "expected_user": "joshu",
            "user": "joshu",
            "uid": 1000,
            "home": "/home/joshu",
            "expected_home": "/home/joshu",
            "is_root": False,
        },
    )
    monkeypatch.setattr(
        "otto.wsl_support._qmd_probe",
        lambda: {"available": True, "status": "ok", "command": "/usr/bin/qmd", "version": "2.1.0"},
    )
    monkeypatch.setattr(
        "otto.wsl_support._openclaw_probe",
        lambda: {
            "available": True,
            "native": False,
            "origin": "windows-path",
            "status": "windows-openclaw-from-wsl-path",
            "command": "/mnt/c/Users/joshu/AppData/Roaming/npm/openclaw",
            "version": None,
        },
    )
    monkeypatch.setattr(
        "otto.wsl_support.build_qmd_index_health",
        lambda: {"ok": True, "source_count": 6},
    )
    monkeypatch.setattr(
        "otto.wsl_support.docker_probe_diagnostics",
        lambda: {"docker_available": True, "daemon_running": True},
    )
    monkeypatch.setattr(
        "otto.wsl_support.docker_compose_status",
        lambda probe=True: {"available": True, "status": "ok", "services": []},
    )

    health = build_wsl_health()

    assert health["ok"] is False
    assert health["openclaw"]["status"] == "windows-openclaw-from-wsl-path"
    assert health["openclaw"]["native"] is False
    assert "Refusing Windows OpenClaw from WSL PATH" in health["recommendations"][0]


def test_build_wsl_health_fails_when_running_as_root(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    paths = SimpleNamespace(repo_root=tmp_path, vault_path=vault)

    monkeypatch.setattr("otto.wsl_support.load_paths", lambda: paths)
    monkeypatch.setattr("otto.wsl_support.is_wsl", lambda: True)
    monkeypatch.setattr(
        "otto.wsl_support._identity_probe",
        lambda: {
            "ok": False,
            "required": True,
            "expected_user": "joshu",
            "user": "root",
            "uid": 0,
            "home": "/root",
            "expected_home": "/home/joshu",
            "is_root": True,
        },
    )
    monkeypatch.setattr(
        "otto.wsl_support._qmd_probe",
        lambda: {"available": True, "status": "ok", "command": "/usr/bin/qmd", "version": "2.1.0"},
    )
    monkeypatch.setattr(
        "otto.wsl_support._openclaw_probe",
        lambda: {
            "available": True,
            "native": True,
            "origin": "native-linux",
            "status": "ok",
            "command": "/home/joshu/.npm-global/bin/openclaw",
            "version": "OpenClaw 2026.4.26",
        },
    )
    monkeypatch.setattr("otto.wsl_support.build_qmd_index_health", lambda: {"ok": True, "source_count": 6})
    monkeypatch.setattr("otto.wsl_support.docker_probe_diagnostics", lambda: {"docker_available": True, "daemon_running": True})
    monkeypatch.setattr("otto.wsl_support.docker_compose_status", lambda probe=True: {"available": True, "status": "ok", "services": []})

    health = build_wsl_health()

    assert health["ok"] is False
    assert health["identity"]["is_root"] is True
    assert "canonical user joshu" in health["recommendations"][0]
