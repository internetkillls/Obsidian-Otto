from __future__ import annotations

from otto.operator_control import fallback_to_native


def test_fallback_to_native_blocks_when_wsl_active(monkeypatch):
    monkeypatch.setattr(
        "otto.operator_control.build_runtime_owner",
        lambda: {"runtime_state": "S4_WSL_LIVE"},
    )
    monkeypatch.setattr(
        "otto.operator_control.decide_gateway_owner",
        lambda: {"active": "wsl", "runtime_state": "S4_WSL_LIVE"},
    )

    result = fallback_to_native()

    assert result["ok"] is False
    assert result["state"] == "NATIVE_FALLBACK_BLOCKED"
    assert result["reason"] == "wsl-active"
