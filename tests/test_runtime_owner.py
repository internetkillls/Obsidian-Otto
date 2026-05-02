from __future__ import annotations

from otto.orchestration.runtime_owner import STATE_WSL_LIVE, decide_gateway_owner


def test_decide_gateway_owner_prefers_wsl_when_gateway_is_live(monkeypatch):
    monkeypatch.setattr(
        "otto.orchestration.runtime_owner.build_runtime_owner",
        lambda: {"runtime_state": STATE_WSL_LIVE},
    )
    monkeypatch.setattr(
        "otto.orchestration.runtime_owner.detect_windows_openclaw_process",
        lambda: {"ok": True, "running": False, "processes": []},
    )
    monkeypatch.setattr("otto.orchestration.runtime_owner._gateway_ok", lambda: True)

    decision = decide_gateway_owner()

    assert decision["active"] == "wsl"


def test_decide_gateway_owner_reports_conflict_when_both_live(monkeypatch):
    monkeypatch.setattr(
        "otto.orchestration.runtime_owner.build_runtime_owner",
        lambda: {"runtime_state": STATE_WSL_LIVE},
    )
    monkeypatch.setattr(
        "otto.orchestration.runtime_owner.detect_windows_openclaw_process",
        lambda: {"ok": True, "running": True, "processes": [{"pid": 123}]},
    )
    monkeypatch.setattr("otto.orchestration.runtime_owner._gateway_ok", lambda: True)

    decision = decide_gateway_owner()

    assert decision["active"] == "wsl"
    assert decision["windows_openclaw_running"] is True
