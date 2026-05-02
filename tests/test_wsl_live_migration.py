from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from otto.orchestration import wsl_live_migration


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _base_repo_config() -> dict:
    return {
        "channels": {"telegram": {"enabled": True, "token": "secret-token"}},
        "memory": {
            "backend": "qmd",
            "qmd": {
                "command": r"C:\qmd.cmd",
                "paths": [{"name": "gold", "path": r"C:\Users\joshu\Obsidian-Otto\state\memory\gold_export"}],
            },
        },
        "plugins": {"local": [r"C:\Users\joshu\Obsidian-Otto\packages\openclaw-otto-bridge"]},
    }


def _patch_common(monkeypatch, tmp_path):
    state_root = tmp_path / "state"
    monkeypatch.setattr(wsl_live_migration, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(wsl_live_migration, "load_paths", lambda: SimpleNamespace(state_root=state_root))
    monkeypatch.setattr(wsl_live_migration, "is_wsl", lambda: False)
    monkeypatch.setattr(
        wsl_live_migration,
        "build_wsl_health",
        lambda: {
            "identity": {"ok": True, "home": "/home/joshu"},
            "qmd": {"available": True, "command": ["/usr/bin/qmd"]},
            "openclaw": {"native": True},
            "docker": {"daemon_running": True},
        },
    )
    monkeypatch.setattr(wsl_live_migration, "build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr(
        wsl_live_migration,
        "probe_openclaw_gateway",
        lambda **kwargs: {"ok": False, "reason": "port-free", "port": kwargs.get("port"), "auth_required": True},
    )
    monkeypatch.setattr(
        wsl_live_migration,
        "build_runtime_owner",
        lambda: {
            "runtime_state": "S2C_WSL_SHADOW_GATEWAY_READY",
            "telegram_owner": "windows_openclaw",
            "gateway_owner": "windows_openclaw",
            "windows_openclaw": {"telegram_enabled": True},
            "ubuntu_openclaw": {"telegram_enabled": False},
            "qmd_owner": "ubuntu_wsl",
        },
    )
    monkeypatch.setattr(
        wsl_live_migration,
        "build_single_owner_lock",
        lambda: {"ok": True, "runtime_state": "S2C_WSL_SHADOW_GATEWAY_READY"},
    )
    monkeypatch.setattr(wsl_live_migration, "_port_open", lambda port: False)
    monkeypatch.setattr(wsl_live_migration, "_rollback_available", lambda: True)
    monkeypatch.setattr(wsl_live_migration, "_write_rollback_plan", lambda gateway_port: {"ok": True, "gateway_port": gateway_port})
    _write_json(tmp_path / ".openclaw" / "openclaw.json", _base_repo_config())
    return state_root


def _fake_wsl_bash(script: str, timeout_seconds: int = 60, input_text: str | None = None) -> dict:
    if "whoami" in script:
        return {"ok": True, "stdout": "joshu", "stderr": ""}
    if "printf %s \"$HOME\"" in script:
        return {"ok": True, "stdout": "/home/joshu", "stderr": ""}
    if "command -v qmd" in script:
        return {"ok": True, "stdout": "/usr/bin/qmd", "stderr": ""}
    if "qmd-binary-ok" in script:
        return {"ok": True, "stdout": "qmd-binary-ok", "stderr": ""}
    if "command -v openclaw" in script:
        return {"ok": True, "stdout": "/home/joshu/.npm-global/bin/openclaw", "stderr": ""}
    if "docker info" in script:
        return {"ok": True, "stdout": "docker-ok", "stderr": ""}
    if "test -d" in script:
        return {"ok": True, "stdout": "installable", "stderr": ""}
    return {"ok": True, "stdout": "ok", "stderr": ""}


def test_preflight_passes_when_all_gates_green_and_windows_stopped(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(wsl_live_migration, "_run_wsl_bash", _fake_wsl_bash)
    monkeypatch.setattr(wsl_live_migration, "_load_wsl_config", lambda: {"channels": {"telegram": {"enabled": False}}})
    monkeypatch.setattr(wsl_live_migration, "detect_windows_openclaw_process", lambda: {"ok": True, "running": False, "processes": []})

    result = wsl_live_migration.build_wsl_live_preflight(write=False)

    assert result["ok"] is True
    assert result["state"] == "PREFLIGHT_PASS"
    assert result["checks"]["windows_openclaw_stopped"] == "green"


def test_preflight_blocks_when_windows_openclaw_appears_running(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(wsl_live_migration, "_run_wsl_bash", _fake_wsl_bash)
    monkeypatch.setattr(wsl_live_migration, "_load_wsl_config", lambda: {"channels": {"telegram": {"enabled": False}}})
    monkeypatch.setattr(wsl_live_migration, "detect_windows_openclaw_process", lambda: {"ok": True, "running": True, "processes": [{"pid": 10}]})

    result = wsl_live_migration.build_wsl_live_preflight(write=False)

    assert result["ok"] is False
    assert result["state"] == "PREFLIGHT_BLOCKED"
    assert any("Windows OpenClaw appears to be running" in item for item in result["blockers"])


def test_dry_run_promote_does_not_write_owner_state(monkeypatch, tmp_path):
    state_root = _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(wsl_live_migration, "_run_wsl_bash", _fake_wsl_bash)
    monkeypatch.setattr(wsl_live_migration, "_load_wsl_config", lambda: {"channels": {"telegram": {"enabled": False}}})
    monkeypatch.setattr(wsl_live_migration, "detect_windows_openclaw_process", lambda: {"ok": True, "running": False, "processes": []})

    result = wsl_live_migration.promote_wsl_live(write=False)

    assert result["ok"] is True
    assert result["state_changed"] is False
    assert not (state_root / "runtime" / "owner.json").exists()


def test_write_promote_enables_ubuntu_telegram_and_updates_owner_state(monkeypatch, tmp_path):
    state_root = _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(wsl_live_migration, "_run_wsl_bash", _fake_wsl_bash)
    monkeypatch.setattr(wsl_live_migration, "_load_wsl_config", lambda: {"channels": {"telegram": {"enabled": False}}})
    monkeypatch.setattr(wsl_live_migration, "detect_windows_openclaw_process", lambda: {"ok": True, "running": False, "processes": []})
    monkeypatch.setattr(wsl_live_migration, "_backup_wsl_config", lambda timestamp: {"ok": True, "backup_path": "/home/joshu/.openclaw/openclaw.json.bak", "raw": {}})
    monkeypatch.setattr(wsl_live_migration, "_write_wsl_config", lambda config: {"ok": True, "stdout": "", "stderr": ""})
    monkeypatch.setattr(
        wsl_live_migration,
        "write_runtime_owner",
        lambda owner=None: _write_owner_file(state_root / "runtime" / "owner.json", owner),
    )
    monkeypatch.setattr(
        wsl_live_migration,
        "write_single_owner_lock",
        lambda: {"ok": True, "lock": {"ok": True, "classification": "safe-wsl-live"}},
    )

    result = wsl_live_migration.promote_wsl_live(write=True)
    written_owner = json.loads((state_root / "runtime" / "owner.json").read_text(encoding="utf-8"))
    preview = json.loads((state_root / "openclaw" / "ubuntu-live" / "openclaw.json.preview").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert written_owner["runtime_state"] == "S4_WSL_LIVE"
    assert written_owner["telegram_owner"] == "ubuntu_openclaw"
    assert preview["channels"]["telegram"]["enabled"] is True
    assert "shadowDisabled" not in preview["channels"]["telegram"]
    assert "plugins" not in preview


def test_write_promote_links_plugin_without_force(monkeypatch, tmp_path):
    state_root = _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(wsl_live_migration, "_load_wsl_config", lambda: {"channels": {"telegram": {"enabled": False}}})
    monkeypatch.setattr(wsl_live_migration, "detect_windows_openclaw_process", lambda: {"ok": True, "running": False, "processes": []})
    monkeypatch.setattr(wsl_live_migration, "_backup_wsl_config", lambda timestamp: {"ok": True, "backup_path": "/home/joshu/.openclaw/openclaw.json.bak", "raw": {}})
    monkeypatch.setattr(wsl_live_migration, "_write_wsl_config", lambda config: {"ok": True, "stdout": "", "stderr": ""})
    monkeypatch.setattr(
        wsl_live_migration,
        "write_runtime_owner",
        lambda owner=None: _write_owner_file(state_root / "runtime" / "owner.json", owner),
    )
    monkeypatch.setattr(
        wsl_live_migration,
        "write_single_owner_lock",
        lambda: {"ok": True, "lock": {"ok": True, "classification": "safe-wsl-live"}},
    )

    seen_scripts: list[str] = []

    def fake_run(script: str, timeout_seconds: int = 60, input_text: str | None = None) -> dict:
        seen_scripts.append(script)
        if "plugins install -l" in script:
            return {"ok": True, "stdout": "linked", "stderr": ""}
        return _fake_wsl_bash(script, timeout_seconds=timeout_seconds, input_text=input_text)

    monkeypatch.setattr(wsl_live_migration, "_run_wsl_bash", fake_run)

    result = wsl_live_migration.promote_wsl_live(write=True)

    assert result["ok"] is True
    assert result["plugin_install"]["ok"] is True
    assert result["plugin_install_retry"] is None
    assert not any("plugins install -l" in script and "--force" in script for script in seen_scripts)


def test_write_promote_refuses_if_single_owner_would_be_violated(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(wsl_live_migration, "_run_wsl_bash", _fake_wsl_bash)
    monkeypatch.setattr(wsl_live_migration, "_load_wsl_config", lambda: {"channels": {"telegram": {"enabled": False}}})
    monkeypatch.setattr(wsl_live_migration, "detect_windows_openclaw_process", lambda: {"ok": True, "running": True, "processes": [{"pid": 99}]})

    result = wsl_live_migration.promote_wsl_live(write=True)

    assert result["ok"] is False
    assert result["state"] == "PROMOTE_BLOCKED"


def test_rollback_disables_ubuntu_telegram_and_restores_owner_to_windows(monkeypatch, tmp_path):
    state_root = _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(wsl_live_migration, "_backup_wsl_config", lambda timestamp: {"ok": True, "backup_path": "/home/joshu/.openclaw/openclaw.json.bak", "raw": {}})
    monkeypatch.setattr(wsl_live_migration, "_write_wsl_config", lambda config: {"ok": True, "stdout": "", "stderr": ""})
    monkeypatch.setattr(
        wsl_live_migration,
        "write_runtime_owner",
        lambda owner=None: _write_owner_file(state_root / "runtime" / "owner.json", owner),
    )
    monkeypatch.setattr(
        wsl_live_migration,
        "write_single_owner_lock",
        lambda: {"ok": True, "lock": {"ok": True, "classification": "safe-rollback"}},
    )

    result = wsl_live_migration.rollback_wsl_live(write=True)
    written_owner = json.loads((state_root / "runtime" / "owner.json").read_text(encoding="utf-8"))
    preview = json.loads((state_root / "openclaw" / "ubuntu-live" / "openclaw.json.preview").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert written_owner["runtime_state"] == "S5_ROLLBACK_WINDOWS"
    assert written_owner["telegram_owner"] == "windows_openclaw"
    assert preview["channels"]["telegram"]["enabled"] is False
    assert "shadowDisabled" not in preview["channels"]["telegram"]


def test_status_reports_gateway_telegram_qmd_owner_clearly(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        wsl_live_migration,
        "build_runtime_owner",
        lambda: {
            "runtime_state": "S4_WSL_LIVE",
            "gateway_owner": "ubuntu_openclaw",
            "telegram_owner": "ubuntu_openclaw",
            "qmd_owner": "ubuntu_wsl",
        },
    )
    monkeypatch.setattr(wsl_live_migration, "build_single_owner_lock", lambda: {"ok": True})
    monkeypatch.setattr(wsl_live_migration, "_load_wsl_config", lambda: {"channels": {"telegram": {"enabled": True}}})
    monkeypatch.setattr(wsl_live_migration, "probe_openclaw_gateway", lambda **kwargs: {"ok": True, "reason": "healthy", "port": 18790})
    monkeypatch.setattr(wsl_live_migration, "detect_windows_openclaw_process", lambda: {"ok": True, "running": False, "processes": []})
    monkeypatch.setattr(wsl_live_migration, "_rollback_available", lambda: True)
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.build_runtime_smoke",
        lambda gateway_port=18790, write=False: {"ok": True, "result": "PASS"},
    )

    result = wsl_live_migration.build_wsl_live_status()

    assert result["runtime_state"] == "S4_WSL_LIVE"
    assert result["gateway_owner"] == "ubuntu_openclaw"
    assert result["telegram_owner"] == "ubuntu_openclaw"
    assert result["qmd_owner"] == "ubuntu_wsl"


def _write_owner_file(path: Path, owner: dict | None) -> dict:
    assert owner is not None
    _write_json(path, owner)
    return {"ok": True, "owner": owner}
