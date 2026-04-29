from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from otto.openclaw_support import (
    build_qmd_index_health,
    build_openclaw_health,
    decide_openclaw_fallback,
    probe_openclaw_gateway,
    qmd_refresh_status_path,
    reload_openclaw_plugin_surface,
    restart_openclaw_gateway,
    run_qmd_index_refresh,
    sync_openclaw_config,
)


def _openclaw_fixture(cli_path: Path) -> dict:
    return {
        "agents": {
            "defaults": {
                "cliBackends": {
                    "claude-cli": {
                        "command": str(cli_path),
                    }
                },
                "models": {
                    "claude-cli/claude-sonnet-4-6": {"alias": "Claude Sonnet 4.6"},
                },
                "heartbeat": {
                    "every": "1h",
                    "model": "openai-codex/gpt-5.4-mini",
                    "target": "none",
                    "ackMaxChars": 300,
                    "lightContext": True,
                    "isolatedSession": True,
                    "timeoutSeconds": 120,
                    "includeSystemPromptSection": False,
                },
                "blockStreamingBreak": "text_end",
                "contextInjection": "always",
                "bootstrapMaxChars": 20000,
                "bootstrapTotalMaxChars": 150000,
                "systemPromptOverride": "Treat USER.md and MEMORY.md as human-first context.",
            }
        },
        "models": {
            "providers": {
                "huggingface": {
                    "api": "huggingface",
                    "apiKey": {"source": "env", "id": "HF_TOKEN"},
                    "baseUrl": "https://api-inference.huggingface.co/framework/openai",
                    "models": [
                        {
                            "id": "Qwen/Qwen2.5-72B-Instruct",
                            "name": "Qwen 72B",
                        }
                    ],
                }
            }
        },
        "plugins": {
            "entries": {
                "skill-routing": {
                    "enabled": True,
                    "config": {
                        "routing_config_path": "config/routing.yaml",
                        "fallback": {
                            "on_status_codes": [529],
                            "provider": "huggingface",
                            "model": "Qwen/Qwen2.5-72B-Instruct",
                        },
                    },
                }
            }
        },
    }


def test_openclaw_sync_and_health(tmp_path, monkeypatch):
    cli_path = tmp_path / "claude.exe"
    cli_path.write_text("", encoding="utf-8")
    repo_config = tmp_path / "repo_openclaw.json"
    live_config = tmp_path / "live_openclaw.json"
    repo_fixture = _openclaw_fixture(cli_path)
    live_fixture = _openclaw_fixture(cli_path)
    live_fixture["models"]["providers"]["huggingface"]["models"][0]["id"] = "Wrong/Model"
    live_fixture["agents"]["defaults"]["systemPromptOverride"] = "Wrong prompt"
    repo_config.write_text(json.dumps(repo_fixture, indent=2), encoding="utf-8")
    live_config.write_text(json.dumps(live_fixture, indent=2), encoding="utf-8")

    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "present")
    monkeypatch.setenv("HF_TOKEN", "present")
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)

    before = live_config.read_text(encoding="utf-8")
    result = sync_openclaw_config(repo_config, live_config)
    after = live_config.read_text(encoding="utf-8")
    assert result["sync_performed"] is True
    assert result["boundary_mode"] == "managed-sync"
    assert result["config_drift_free"] is True
    assert before != after
    assert result["backup_path"] is not None
    assert Path(result["backup_path"]).exists()
    assert "models.providers" in result["changed_sections"]
    assert "agents.defaults.systemPromptOverride" in result["changed_sections"]
    assert result["otto_env_contract"]["OTTO_LAUNCHER"] == "otto.bat"
    assert result["openclaw_config_sync"] is True

    health = build_openclaw_health(repo_config, live_config)
    assert health["config_drift_free"] is True
    assert health["anthropic_ready"] is True
    assert health["hf_fallback_ready"] is True
    live_after = json.loads(after)
    assert live_after["models"]["providers"]["huggingface"]["models"][0]["id"] == "Qwen/Qwen2.5-72B-Instruct"
    assert live_after["agents"]["defaults"]["heartbeat"]["every"] == "2m"
    assert live_after["agents"]["defaults"]["systemPromptOverride"] == "Treat USER.md and MEMORY.md as human-first context."
    assert live_after["env"]["shellEnv"]["enabled"] is True
    assert (tmp_path / "state" / "openclaw" / "sync_status.json").exists()
    assert json.loads((tmp_path / "state" / "openclaw" / "sync_status.json").read_text(encoding="utf-8"))["openclaw_config_sync"] is True
    assert (tmp_path / "state" / "openclaw" / "env_contract.json").exists()
    assert (tmp_path / "state" / "openclaw" / "capabilities.json").exists()
    assert result["cli_validation"]["skipped"] is True


def test_build_qmd_index_health_supports_paths_schema(tmp_path, monkeypatch):
    vault_path = tmp_path / "vault"
    facts_path = vault_path / ".Otto-Realm" / "Memory-Tiers" / "01-Facts"
    facts_path.mkdir(parents=True, exist_ok=True)
    (facts_path / "fact.md").write_text("# Fact\n", encoding="utf-8")

    live_config = tmp_path / "live_openclaw.json"
    live_config.write_text(
        json.dumps(
            {
                "memory": {
                    "backend": "qmd",
                    "qmd": {
                        "paths": [
                            {
                                "name": "otto-facts",
                                "path": str(facts_path),
                                "pattern": "**/*.md",
                            }
                        ]
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
        vault_path=vault_path,
    )
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr("otto.openclaw_support.repo_openclaw_config_path", lambda: tmp_path / "missing_repo.json")

    health = build_qmd_index_health(live_config)

    assert health["ok"] is True
    assert health["backend_is_qmd"] is True
    assert health["source_count"] == 1
    assert health["sources"][0]["id"] == "otto-facts"
    assert health["sources"][0]["exists"] is True
    assert health["sources"][0]["md_file_count"] == 1


def test_run_qmd_index_refresh_skips_unhealthy_preflight_and_records_state(tmp_path, monkeypatch):
    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr(
        "otto.openclaw_support.build_qmd_index_health",
        lambda live_config_path=None: {
            "ok": False,
            "backend_is_qmd": True,
            "source_count": 0,
            "sources": [],
        },
    )
    monkeypatch.setattr("otto.openclaw_support.shutil.which", lambda name: r"C:\tool\openclaw.exe")

    result = run_qmd_index_refresh()

    assert result["ok"] is False
    assert result["skipped"] is True
    assert result["reason"] == "qmd-preflight-unhealthy"
    state = json.loads(qmd_refresh_status_path().read_text(encoding="utf-8"))
    assert state["failure_kind"] == "preflight-unhealthy"
    assert state["consecutive_failures"] == 0


def test_run_qmd_index_refresh_applies_cooldown_after_command_failure(tmp_path, monkeypatch):
    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr(
        "otto.openclaw_support.build_qmd_index_health",
        lambda live_config_path=None: {
            "ok": True,
            "backend_is_qmd": True,
            "source_count": 1,
            "sources": [{"id": "otto-facts"}],
        },
    )
    monkeypatch.setattr("otto.openclaw_support.shutil.which", lambda name: r"C:\tool\openclaw.exe")

    class _Completed:
        returncode = 1
        stdout = ""
        stderr = "boom"

    monkeypatch.setattr("otto.openclaw_support.subprocess.run", lambda *args, **kwargs: _Completed())

    first = run_qmd_index_refresh()
    second = run_qmd_index_refresh()

    assert first["ok"] is False
    assert first["skipped"] is False
    assert first["state"]["failure_kind"] == "command-failed"
    assert second["ok"] is False
    assert second["skipped"] is True
    assert second["reason"] == "qmd-cooldown-active"


def test_openclaw_fallback_decision_logs_event(tmp_path, monkeypatch):
    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr(
        "otto.openclaw_support.build_openclaw_health",
        lambda repo_config_path=None, live_config_path=None: {
            "hf_fallback_ready": True,
            "live_hf_model_id": "Qwen/Qwen2.5-72B-Instruct",
        },
    )

    decision = decide_openclaw_fallback(529)
    assert decision["should_fallback"] is True
    assert decision["fallback_provider"] == "huggingface"
    fallback_log = tmp_path / "state" / "openclaw" / "fallback_events.jsonl"
    assert fallback_log.exists()
    assert "Qwen/Qwen2.5-72B-Instruct" in fallback_log.read_text(encoding="utf-8")


def test_openclaw_fallback_rejects_non_529(tmp_path, monkeypatch):
    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr(
        "otto.openclaw_support.build_openclaw_health",
        lambda repo_config_path=None, live_config_path=None: {
            "hf_fallback_ready": True,
            "live_hf_model_id": "Qwen/Qwen2.5-72B-Instruct",
        },
    )

    decision = decide_openclaw_fallback(401)
    assert decision["should_fallback"] is False
    assert decision["reason"] == "status_not_supported"


def test_openclaw_gateway_restart_uses_repo_fallback(tmp_path, monkeypatch):
    gateway_cmd = tmp_path / "gateway.cmd"
    gateway_cmd.write_text("@echo off\r\necho gateway\r\n", encoding="utf-8")

    pid_sequences = [[111], [], [222]]
    port_sequences = [True, False, True]

    monkeypatch.setattr("otto.openclaw_support.live_openclaw_gateway_cmd_path", lambda: gateway_cmd)
    monkeypatch.setattr("otto.openclaw_support._openclaw_gateway_port", lambda: 18789)
    monkeypatch.setattr(
        "otto.openclaw_support._find_openclaw_gateway_pids",
        lambda: pid_sequences.pop(0) if pid_sequences else [222],
    )
    monkeypatch.setattr(
        "otto.openclaw_support._gateway_port_open",
        lambda port, timeout=0.4: port_sequences.pop(0) if port_sequences else True,
    )

    class DummyRunResult:
        def __init__(self, returncode=0):
            self.returncode = returncode
            self.stderr = ""

    monkeypatch.setattr("otto.openclaw_support.subprocess.run", lambda *args, **kwargs: DummyRunResult())
    monkeypatch.setattr("otto.openclaw_support.time.sleep", lambda seconds: None)

    result = restart_openclaw_gateway(wait_seconds=2)

    assert result["ok"] is True
    assert result["reason"] == "gateway-restarted"
    assert result["before_pids"] == [111]
    assert result["after_pids"] == [222]
    assert result["stdout_log"].endswith("gateway-reload.out.log")


def test_openclaw_gateway_probe_uses_http_health(tmp_path, monkeypatch):
    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr("otto.openclaw_support._openclaw_gateway_port", lambda: 18789)
    monkeypatch.setattr("otto.openclaw_support._find_openclaw_gateway_pids", lambda: [69452])
    monkeypatch.setattr("otto.openclaw_support._gateway_port_open", lambda port, timeout=0.4: True)
    monkeypatch.setattr(
        "otto.openclaw_support._recent_restart_window",
        lambda window_seconds=600: {"active": False, "state": "none", "last_event_at": None, "last_event": None},
    )

    def fake_http(url, timeout_seconds):
        if url.endswith("/health"):
            return 200, {"ok": True, "status": "live"}, None
        return 200, None, "<!doctype html>"

    monkeypatch.setattr("otto.openclaw_support._http_get_json", fake_http)

    result = probe_openclaw_gateway(timeout_seconds=2.0)

    assert result["ok"] is True
    assert result["reason"] == "gateway-http-healthy"
    assert result["cli_bypass_recommended"] is True
    assert result["pids"] == [69452]
    assert result["health_json"]["status"] == "live"
    assert result["checked_at"]


def test_openclaw_gateway_probe_accepts_shadow_port_and_runtime(tmp_path, monkeypatch):
    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr("otto.openclaw_support._find_openclaw_gateway_pids", lambda: [])
    monkeypatch.setattr("otto.openclaw_support._gateway_port_open", lambda port, timeout=0.4: port == 18790)
    monkeypatch.setattr(
        "otto.openclaw_support._recent_restart_window",
        lambda window_seconds=600: {"active": False, "state": "none", "last_event_at": None, "last_event": None},
    )
    monkeypatch.setattr(
        "otto.openclaw_support._gateway_shadow_telegram_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "otto.openclaw_support.build_qmd_index_health",
        lambda: {"ok": True, "source_count": 6},
    )

    def fake_http(url, timeout_seconds):
        if url.endswith("/health"):
            return None, None, "not-json"
        return 200, None, "<!doctype html>"

    monkeypatch.setattr("otto.openclaw_support._http_get_json", fake_http)

    result = probe_openclaw_gateway(port=18790, runtime="wsl-shadow", timeout_seconds=2.0)

    assert result["ok"] is True
    assert result["reason"] == "gateway-root-reachable"
    assert result["runtime"] == "wsl-shadow"
    assert result["telegram_enabled"] is False
    assert result["qmd_index_seen"] is True


def test_openclaw_gateway_probe_treats_shadow_websocket_port_as_reachable(tmp_path, monkeypatch):
    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr("otto.openclaw_support._find_openclaw_gateway_pids", lambda: [])
    monkeypatch.setattr("otto.openclaw_support._gateway_port_open", lambda port, timeout=0.4: True)
    monkeypatch.setattr(
        "otto.openclaw_support._recent_restart_window",
        lambda window_seconds=600: {"active": False, "state": "none", "last_event_at": None, "last_event": None},
    )
    monkeypatch.setattr("otto.openclaw_support._gateway_shadow_telegram_enabled", lambda: False)
    monkeypatch.setattr("otto.openclaw_support.build_qmd_index_health", lambda: {"ok": True})
    monkeypatch.setattr("otto.openclaw_support._http_get_json", lambda url, timeout_seconds: (None, None, "timed out"))

    result = probe_openclaw_gateway(port=18790, runtime="wsl-shadow", timeout_seconds=2.0)

    assert result["ok"] is True
    assert result["reason"] == "gateway-port-open-websocket"
    assert result["websocket_reachable"] is True


def test_openclaw_gateway_probe_tracks_last_failure(tmp_path, monkeypatch):
    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr("otto.openclaw_support._openclaw_gateway_port", lambda: 18789)
    monkeypatch.setattr("otto.openclaw_support._find_openclaw_gateway_pids", lambda: [])
    monkeypatch.setattr(
        "otto.openclaw_support._recent_restart_window",
        lambda window_seconds=600: {"active": False, "state": "none", "last_event_at": None, "last_event": None},
    )

    responses = iter(
        [
            (False, (None, None, "timeout"), (None, None, "refused")),
            (True, (200, {"ok": True, "status": "live"}, None), (200, None, "<!doctype html>")),
        ]
    )

    def fake_port_open(port, timeout=0.4):
        current = fake_port_open.current
        return current[0]

    def fake_http(url, timeout_seconds):
        current = fake_port_open.current
        if url.endswith("/health"):
            return current[1]
        return current[2]

    fake_port_open.current = next(responses)
    monkeypatch.setattr("otto.openclaw_support._gateway_port_open", fake_port_open)
    monkeypatch.setattr("otto.openclaw_support._http_get_json", fake_http)

    first = probe_openclaw_gateway(timeout_seconds=1.0)
    assert first["ok"] is False
    assert first["last_failure_at"]

    fake_port_open.current = next(responses)
    second = probe_openclaw_gateway(timeout_seconds=1.0)
    assert second["ok"] is True
    assert second["reason"] == "gateway-http-healthy"
    assert second["last_failure_at"] == first["last_failure_at"]


def test_openclaw_plugin_reload_touches_config_and_restarts(tmp_path, monkeypatch):
    live_config = tmp_path / "openclaw.json"
    live_config.write_text(json.dumps({"meta": {"lastTouchedAt": "old"}}), encoding="utf-8")

    monkeypatch.setattr("otto.openclaw_support.live_openclaw_config_path", lambda: live_config)
    monkeypatch.setattr("otto.openclaw_support.time.sleep", lambda seconds: None)
    monkeypatch.setattr(
        "otto.openclaw_support.probe_openclaw_gateway",
        lambda timeout_seconds=5.0: {"ok": True, "reason": "gateway-http-healthy"},
    )
    monkeypatch.setattr(
        "otto.openclaw_support.restart_openclaw_gateway",
        lambda wait_seconds=30: {"ok": True, "reason": "gateway-restarted", "after_pids": [222]},
    )

    result = reload_openclaw_plugin_surface(wait_seconds=2, hard_restart=True)

    written = json.loads(live_config.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["touch_performed"] is True
    assert result["restart_attempted"] is True
    assert written["meta"]["lastTouchedBy"] == "otto.plugin_reload"
