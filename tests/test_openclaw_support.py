from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from otto.openclaw_support import (
    build_openclaw_health,
    decide_openclaw_fallback,
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
    repo_config.write_text(json.dumps(_openclaw_fixture(cli_path), indent=2), encoding="utf-8")

    paths = SimpleNamespace(
        state_root=tmp_path / "state",
        logs_root=tmp_path / "logs",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "present")
    monkeypatch.setenv("HF_TOKEN", "present")
    monkeypatch.setattr("otto.openclaw_support.load_paths", lambda: paths)
    monkeypatch.setattr(
        "otto.openclaw_support.run_openclaw_cli_validation",
        lambda timeout_seconds=45: {"ok": True, "exit_code": 0, "stdout": "OK", "stderr": "", "command": ["openclaw", "config", "file"]},
    )

    result = sync_openclaw_config(repo_config, live_config, validate_cli=True)
    assert result["openclaw_config_sync"] is True
    assert live_config.exists()

    health = build_openclaw_health(repo_config, live_config)
    assert health["openclaw_config_sync"] is True
    assert health["anthropic_ready"] is True
    assert health["hf_fallback_ready"] is True
    assert (tmp_path / "state" / "openclaw" / "sync_status.json").exists()


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
