from __future__ import annotations

from types import SimpleNamespace

from otto.adapters.openclaw.context_pack import build_openclaw_context_pack
from otto.adapters.openclaw.tool_payloads import build_openclaw_tool_manifest
from otto.orchestration.runtime_owner import build_single_owner_lock


def test_tool_manifest_exposes_initial_read_only_tools():
    manifest = build_openclaw_tool_manifest()

    assert manifest["state"] == "OCB1_TOOL_MANIFEST_GENERATED"
    tool_names = {tool["name"] for tool in manifest["tools"]}
    assert {
        "otto.qmd_health",
        "otto.qmd_manifest",
        "otto.context_pack",
        "otto.source_registry",
        "otto.runtime_status",
    }.issubset(tool_names)
    assert "otto.heartbeat" in tool_names
    assert all(tool["risk"] in {"read_only", "candidate_generation", "web_research_candidate", "read_write_private_state", "web_query_candidate"} for tool in manifest["tools"])


def test_context_pack_is_qmd_aware_when_health_is_green(monkeypatch):
    monkeypatch.setattr(
        "otto.adapters.openclaw.context_pack.build_runtime_owner",
        lambda: {"runtime_state": "S2C_WSL_SHADOW_GATEWAY_READY"},
    )
    monkeypatch.setattr(
        "otto.adapters.openclaw.context_pack.build_qmd_index_health",
        lambda: {"ok": True, "source_count": 6},
    )
    monkeypatch.setattr(
        "otto.adapters.openclaw.context_pack.qmd_manifest_health",
        lambda: {"ok": True, "source_count": 7},
    )
    monkeypatch.setattr(
        "otto.adapters.openclaw.context_pack.validate_source_registry",
        lambda: {"ok": True},
    )
    monkeypatch.setattr(
        "otto.adapters.openclaw.context_pack.build_single_owner_lock",
        lambda: {"ok": True, "ubuntu_shadow_telegram_disabled": True},
    )
    monkeypatch.setattr(
        "otto.adapters.openclaw.context_pack.read_json",
        lambda path, default=None: {"ok": True, "port": 18790, "reason": "gateway-http-healthy"},
    )

    pack = build_openclaw_context_pack(task="bridge")

    assert pack["state"] in {"CP2_QMD_AWARE", "CP6_CREATIVE_ACTION_AWARE"}
    assert pack["runtime"]["telegram"] == "disabled"
    assert "otto.qmd_health" in pack["available_tools"]
    assert pack["safety"]["raw_social_to_qmd_allowed"] is False
    assert pack["creative_forge"]["raw_idea_content_in_context"] is False
    assert "sanity" in pack
    assert "quarantined records" in pack["do_not_use"]


def test_single_owner_lock_fails_if_ubuntu_shadow_telegram_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "otto.orchestration.runtime_owner.build_runtime_owner",
        lambda: {
            "runtime_state": "S2B_WSL_SHADOW_MEMORY_READY",
            "windows_openclaw": {"telegram_enabled": False},
            "ubuntu_openclaw": {"telegram_enabled": True, "gateway_port": 18790},
        },
    )

    lock = build_single_owner_lock()

    assert lock["ok"] is False
    assert lock["classification"] == "unsafe-owner-conflict"
    assert lock["telegram_enabled_owners"] == ["ubuntu_openclaw"]
