from __future__ import annotations

import json
from pathlib import Path

from otto import operator_control


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_operator_status_checks_native_wsl_qmd_cron_heartbeat_parity(tmp_path, monkeypatch):
    state = tmp_path / "state"
    native_config = {
        "gateway": {"port": 18789},
        "channels": {"telegram": {"enabled": False}},
        "memory": {
            "backend": "qmd",
            "qmd": {
                "command": "C:/Users/joshu/Obsidian-Otto/scripts/shell/qmd-wsl.js",
                "paths": [{"name": "gold", "path": "C:/Users/joshu/Obsidian-Otto/state/memory/gold_export", "pattern": "**/*.md"}],
            },
        },
    }
    wsl_config = {
        "gateway": {"port": 18790},
        "channels": {"telegram": {"enabled": True}},
        "memory": {
            "backend": "qmd",
            "qmd": {
                "command": "/usr/bin/qmd",
                "paths": [{"name": "gold", "path": "/mnt/c/Users/joshu/Obsidian-Otto/state/memory/gold_export", "pattern": "**/*.md"}],
            },
        },
    }
    _write_json(tmp_path / ".openclaw" / "openclaw.json", native_config)
    _write_json(state / "openclaw" / "ubuntu-shadow" / "openclaw.json", wsl_config)
    _write_json(
        state / "openclaw" / "cron_contract_v1.json",
        {"validation": {"drift_free": True}, "jobs": [{"job_key": "daily", "enabled": True, "schedule": {"tz": "Asia/Bangkok"}}]},
    )
    _write_json(state / "openclaw" / "heartbeat" / "otto_heartbeat_manifest.json", {"tools": [{"name": "otto.heartbeat"}]})
    monkeypatch.setattr(operator_control, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(operator_control, "state_root", lambda: state)
    monkeypatch.setattr(operator_control, "build_runtime_owner", lambda: {"runtime_state": "S4_WSL_LIVE"})
    monkeypatch.setattr(
        operator_control,
        "build_openclaw_health",
        lambda: {"config_drift_free": True, "qmd_index": {"ok": True, "source_count": 1}},
    )
    monkeypatch.setattr(
        operator_control,
        "probe_openclaw_gateway",
        lambda **_: {"ok": True, "reason": "healthy", "port": 18790, "telegram_enabled": False, "qmd_index_seen": True},
    )
    monkeypatch.setattr(
        operator_control,
        "wsl_environment_status",
        lambda: {
            "ok": True,
            "openclaw_bin": "/home/joshu/.npm-global/bin/openclaw",
            "qmd_bin": "/usr/bin/qmd",
            "repo_visible": True,
            "vault_visible": True,
            "raw": {"stderr": ""},
        },
    )

    result = operator_control.operator_status()

    assert result["ok"] is True
    assert result["parity"]["qmd_sources_match"] is True
    assert result["parity"]["wsl_telegram_enabled"] is True
    assert result["parity"]["telegram_enabled_owners"] == ["ubuntu_openclaw"]
    assert (state / "operator" / "openclaw_runtime.json").exists()


def test_operator_status_fails_closed_on_qmd_source_mismatch(tmp_path, monkeypatch):
    state = tmp_path / "state"
    native_config = {
        "channels": {"telegram": {"enabled": True}},
        "memory": {"backend": "qmd", "qmd": {"paths": [{"name": "gold", "path": "C:/Users/joshu/Obsidian-Otto/state/memory/gold_export"}]}},
    }
    wsl_config = {
        "channels": {"telegram": {"enabled": False}},
        "memory": {"backend": "qmd", "qmd": {"command": "/usr/bin/qmd", "paths": [{"name": "raw", "path": "/mnt/c/Users/joshu/Obsidian-Otto/state/ingest/raw"}]}},
    }
    _write_json(tmp_path / ".openclaw" / "openclaw.json", native_config)
    _write_json(state / "openclaw" / "ubuntu-shadow" / "openclaw.json", wsl_config)
    _write_json(state / "openclaw" / "cron_contract_v1.json", {"jobs": []})
    _write_json(state / "openclaw" / "heartbeat" / "otto_heartbeat_manifest.json", {"tools": [{"name": "otto.heartbeat"}]})
    monkeypatch.setattr(operator_control, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(operator_control, "state_root", lambda: state)
    monkeypatch.setattr(operator_control, "build_openclaw_health", lambda: {"qmd_index": {"ok": True}})
    monkeypatch.setattr(
        operator_control,
        "_canonical_wsl_config",
        lambda native_config, runtime_state: wsl_config,
    )
    monkeypatch.setattr(operator_control, "probe_openclaw_gateway", lambda **_: {"ok": False, "reason": "not-running", "port": 18790})
    monkeypatch.setattr(
        operator_control,
        "wsl_environment_status",
        lambda: {
            "ok": True,
            "openclaw_bin": "/home/joshu/.npm-global/bin/openclaw",
            "qmd_bin": "/usr/bin/qmd",
            "repo_visible": True,
            "vault_visible": True,
            "raw": {"stderr": ""},
        },
    )

    result = operator_control.operator_status()

    assert result["ok"] is False
    assert result["state"] == "OO_OPERATOR_PARITY_NEEDS_REPAIR"
    assert result["parity"]["qmd_sources_match"] is False
    assert result["next_required_action"] == "run operator-doctor or operator-repair"
