from __future__ import annotations

from pathlib import Path

from otto.orchestration.runtime_smoke import build_runtime_smoke


def test_runtime_smoke_passes_for_s4_with_ubuntu_owner_only(monkeypatch):
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.build_wsl_health",
        lambda: {
            "identity": {"ok": True},
            "qmd": {"available": True},
            "openclaw": {"native": True},
            "docker": {"daemon_running": True},
        },
    )
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke._build_wsl_runtime_probe",
        lambda: {
            "ok": True,
            "identity": {"ok": True},
            "qmd": {"available": True, "command": "/usr/bin/qmd"},
            "openclaw": {"native": True, "command": "/home/joshu/.npm-global/bin/openclaw"},
            "docker": {"daemon_running": True},
        },
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.qmd_manifest_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.read_json", lambda path, default=None: {"last_success_at": "now"})
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke._run_openclaw",
        lambda args, timeout_seconds=120, runtime_state=None: {"ok": True},
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.probe_openclaw_gateway", lambda **kwargs: {"ok": True, "auth_required": True})
    owner_payload = {
        "runtime_state": "S4_WSL_LIVE",
        "gateway_owner": "ubuntu_openclaw",
        "windows_openclaw": {"telegram_enabled": False},
        "ubuntu_openclaw": {"telegram_enabled": True},
    }
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.write_runtime_owner",
        lambda: {
            "owner": owner_payload
        },
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_runtime_owner", lambda: owner_payload)
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.write_single_owner_lock",
        lambda: {"lock": {"ok": True}},
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_single_owner_lock", lambda: {"ok": True})
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke._load_runtime_config_preview",
        lambda runtime_state: {"channels": {"telegram": {"enabled": True}}, "gateway": {"auth": {"mode": "token"}}},
    )
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.run_sanity_scan",
        lambda strict=False, write=True: {
            "ok": True,
            "strict_failures": 0,
            "warning_count": 0,
            "schema_audit": {"ok": True},
            "blockers": [],
            "repair_plan": {"actions": []},
        },
    )

    smoke = build_runtime_smoke(write=False)

    assert smoke["ok"] is True
    assert smoke["result"] == "PASS"
    assert smoke["gates"]["gateway_live"] is True
    assert smoke["gates"]["ubuntu_telegram_live_enabled"] is True
    assert smoke["sanity"]["strict_failures"] == 0


def test_runtime_smoke_fails_if_s4_has_windows_telegram_enabled_too(monkeypatch):
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.build_wsl_health",
        lambda: {"identity": {"ok": True}, "qmd": {"available": True}, "openclaw": {"native": True}, "docker": {"daemon_running": True}},
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.qmd_manifest_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.read_json", lambda path, default=None: {"last_success_at": "now"})
    monkeypatch.setattr("otto.orchestration.runtime_smoke._run_openclaw", lambda args, timeout_seconds=120, runtime_state=None: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.probe_openclaw_gateway", lambda **kwargs: {"ok": True, "auth_required": True})
    owner_payload = {
        "runtime_state": "S4_WSL_LIVE",
        "gateway_owner": "ubuntu_openclaw",
        "windows_openclaw": {"telegram_enabled": True},
        "ubuntu_openclaw": {"telegram_enabled": True},
    }
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.write_runtime_owner",
        lambda: {
            "owner": owner_payload
        },
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_runtime_owner", lambda: owner_payload)
    monkeypatch.setattr("otto.orchestration.runtime_smoke.write_single_owner_lock", lambda: {"lock": {"ok": False}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_single_owner_lock", lambda: {"ok": False})
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke._load_runtime_config_preview",
        lambda runtime_state: {"channels": {"telegram": {"enabled": True}}, "gateway": {"auth": {"mode": "token"}}},
    )
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.run_sanity_scan",
        lambda strict=False, write=True: {"ok": True, "strict_failures": 0, "warning_count": 0, "schema_audit": {"ok": True}, "blockers": [], "repair_plan": {"actions": []}},
    )

    smoke = build_runtime_smoke(write=False)

    assert smoke["ok"] is False
    assert smoke["gates"]["windows_telegram_live_disabled"] is False


def test_runtime_smoke_fails_if_shadow_has_ubuntu_telegram_enabled(monkeypatch):
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.build_wsl_health",
        lambda: {"identity": {"ok": True}, "qmd": {"available": True}, "openclaw": {"native": True}, "docker": {"daemon_running": True}},
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.validate_source_registry", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.qmd_manifest_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.read_json", lambda path, default=None: {"last_success_at": "now"})
    monkeypatch.setattr("otto.orchestration.runtime_smoke._run_openclaw", lambda args, timeout_seconds=120, runtime_state=None: {"ok": True})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.probe_openclaw_gateway", lambda **kwargs: {"ok": True, "auth_required": False})
    owner_payload = {
        "runtime_state": "S2C_WSL_SHADOW_GATEWAY_READY",
        "gateway_owner": "ubuntu_openclaw",
        "windows_openclaw": {"telegram_enabled": False},
        "ubuntu_openclaw": {"telegram_enabled": True},
    }
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.write_runtime_owner",
        lambda: {
            "owner": owner_payload
        },
    )
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_runtime_owner", lambda: owner_payload)
    monkeypatch.setattr("otto.orchestration.runtime_smoke.write_single_owner_lock", lambda: {"lock": {"ok": False}})
    monkeypatch.setattr("otto.orchestration.runtime_smoke.build_single_owner_lock", lambda: {"ok": False})
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke._load_runtime_config_preview",
        lambda runtime_state: {"channels": {"telegram": {"enabled": True}}, "gateway": {"auth": {"mode": "none"}}},
    )
    monkeypatch.setattr(
        "otto.orchestration.runtime_smoke.run_sanity_scan",
        lambda strict=False, write=True: {"ok": True, "strict_failures": 0, "warning_count": 0, "schema_audit": {"ok": True}, "blockers": [], "repair_plan": {"actions": []}},
    )

    smoke = build_runtime_smoke(write=False)

    assert smoke["ok"] is False
    assert smoke["gates"]["ubuntu_telegram_shadow_disabled"] is False
