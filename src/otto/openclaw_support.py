from __future__ import annotations

# MIGRATION: migrate to MCP — see config/migration-bridges.yaml BRIDGE-004, BRIDGE-005, BRIDGE-006
# OpenClaw should own its config; Otto should receive state/pipeline events only after MCP is live.

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import load_env_file, load_paths, repo_root
from .events import (
    Event,
    EventBus,
    EVENT_OPENCLAW_CONFIG_SYNCED,
    EVENT_OPENCLAW_FALLBACK_TRIGGERED,
)
from .logging_utils import append_jsonl, get_logger
from .state import now_iso, read_json, write_json


OPENCLAW_RELATIVE_PATH = Path(".openclaw") / "openclaw.json"
OPENCLAW_LIVE_PATH = Path.home() / ".openclaw" / "openclaw.json"
DEFAULT_FALLBACK_PROVIDER = "huggingface"
DEFAULT_FALLBACK_MODEL = "Qwen/Qwen2.5-72B-Instruct"
FALLBACK_STATUS_CODES = {529}
MANAGED_SECTION_PATHS: tuple[tuple[str, ...], ...] = (
    ("agents", "defaults", "cliBackends"),
    ("agents", "defaults", "models"),
    ("agents", "defaults", "heartbeat"),
    ("models", "providers"),
)


def repo_openclaw_config_path() -> Path:
    return repo_root() / OPENCLAW_RELATIVE_PATH


def live_openclaw_config_path() -> Path:
    return OPENCLAW_LIVE_PATH


def _normalize_json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_config(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"missing: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"json_error: {exc}"
    if not isinstance(data, dict):
        return None, f"expected object, received {type(data).__name__}"
    return data, None


def _env_present(name: str) -> bool:
    if os.environ.get(name):
        return True
    env = load_env_file(repo_root() / ".env")
    if env.get(name):
        return True
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
                return bool(value)
        except OSError:
            return False
    return False


def _get_section(data: dict[str, Any], path_parts: tuple[str, ...]) -> Any:
    current: Any = data
    for part in path_parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _managed_hashes(data: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path_parts in MANAGED_SECTION_PATHS:
        key = ".".join(path_parts)
        section = _get_section(data, path_parts)
        hashes[key] = _sha256_text(_normalize_json_text(section))
    return hashes


def _first_hf_model_id(config: dict[str, Any]) -> str | None:
    providers = ((config.get("models") or {}).get("providers") or {})
    huggingface = providers.get("huggingface") or {}
    models = huggingface.get("models") or []
    if not isinstance(models, list) or not models:
        return None
    first = models[0] or {}
    if not isinstance(first, dict):
        return None
    model_id = first.get("id")
    return str(model_id) if model_id else None


def run_openclaw_cli_validation(timeout_seconds: int = 45) -> dict[str, Any]:
    cli_path = shutil.which("openclaw")
    if not cli_path:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": "openclaw executable not found on PATH",
            "command": ["openclaw", "config", "file"],
        }

    try:
        proc = subprocess.run(
            [cli_path, "config", "file"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": f"timed out after {timeout_seconds}s",
            "command": [cli_path, "config", "file"],
        }

    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "command": [cli_path, "config", "file"],
    }


def openclaw_sync_status_path() -> Path:
    return load_paths().state_root / "openclaw" / "sync_status.json"


def openclaw_fallback_events_path() -> Path:
    return load_paths().state_root / "openclaw" / "fallback_events.jsonl"


def latest_openclaw_sync_status() -> dict[str, Any]:
    return read_json(openclaw_sync_status_path(), default={}) or {}


def build_openclaw_health(
    repo_config_path: Path | None = None,
    live_config_path: Path | None = None,
) -> dict[str, Any]:
    repo_path = repo_config_path or repo_openclaw_config_path()
    live_path = live_config_path or live_openclaw_config_path()
    repo_config, repo_error = _load_config(repo_path)
    live_config, live_error = _load_config(live_path)
    repo_hashes = _managed_hashes(repo_config) if repo_config else {}
    live_hashes = _managed_hashes(live_config) if live_config else {}

    repo_hf_model = _first_hf_model_id(repo_config) if repo_config else None
    live_hf_model = _first_hf_model_id(live_config) if live_config else None

    cli_backend = (
        (((live_config or {}).get("agents") or {}).get("defaults") or {}).get("cliBackends") or {}
    ).get("claude-cli") or {}
    anthropic_backend_configured = bool(cli_backend)
    cli_path = Path(str(cli_backend.get("command", ""))).expanduser() if cli_backend.get("command") else None
    cli_exists = bool(cli_path and cli_path.exists())
    anthropic_key_present = _env_present("ANTHROPIC_API_KEY")
    hf_token_present = _env_present("HF_TOKEN")

    managed_hashes_match = bool(repo_hashes and repo_hashes == live_hashes)
    huggingface_provider_present = bool(
        (((live_config or {}).get("models") or {}).get("providers") or {}).get("huggingface")
    )

    report = {
        "canonical_source": str(repo_path),
        "live_config_path": str(live_path),
        "repo_exists": repo_config is not None,
        "repo_parse_error": repo_error,
        "live_exists": live_config is not None,
        "live_parse_error": live_error,
        "repo_managed_hashes": repo_hashes,
        "live_managed_hashes": live_hashes,
        "managed_hashes_match": managed_hashes_match,
        "openclaw_config_sync": managed_hashes_match,
        "repo_hf_model_id": repo_hf_model,
        "live_hf_model_id": live_hf_model,
        "huggingface_provider_present": huggingface_provider_present,
        "expected_hf_model_present": live_hf_model == DEFAULT_FALLBACK_MODEL,
        "claude_cli_path": str(cli_path) if cli_path else None,
        "claude_cli_exists": cli_exists,
        "anthropic_backend_configured": anthropic_backend_configured,
        "anthropic_key_present": anthropic_key_present,
        "hf_token_present": hf_token_present,
        "anthropic_ready": cli_exists and anthropic_backend_configured,
        "hf_fallback_ready": huggingface_provider_present
        and live_hf_model == DEFAULT_FALLBACK_MODEL
        and hf_token_present
        and managed_hashes_match,
        "fallback_on_status_codes": sorted(FALLBACK_STATUS_CODES),
        "fallback_provider": DEFAULT_FALLBACK_PROVIDER,
        "fallback_model": DEFAULT_FALLBACK_MODEL,
        "last_sync": latest_openclaw_sync_status(),
    }
    return report


def sync_openclaw_config(
    repo_config_path: Path | None = None,
    live_config_path: Path | None = None,
    *,
    validate_cli: bool = True,
) -> dict[str, Any]:
    logger = get_logger("otto.openclaw.sync")
    paths = load_paths()
    repo_path = repo_config_path or repo_openclaw_config_path()
    live_path = live_config_path or live_openclaw_config_path()

    source_data, source_error = _load_config(repo_path)
    if source_data is None:
        raise RuntimeError(f"Canonical OpenClaw config is invalid: {source_error}")

    live_path.parent.mkdir(parents=True, exist_ok=True)
    live_path.write_text(_normalize_json_text(source_data), encoding="utf-8")

    health = build_openclaw_health(repo_path, live_path)
    cli_validation = run_openclaw_cli_validation() if validate_cli else {"ok": True, "skipped": True}
    result = {
        "ts": now_iso(),
        "canonical_source": str(repo_path),
        "live_config_path": str(live_path),
        "openclaw_config_sync": health["openclaw_config_sync"],
        "managed_hashes_match": health["managed_hashes_match"],
        "anthropic_ready": health["anthropic_ready"],
        "hf_fallback_ready": health["hf_fallback_ready"],
        "huggingface_provider_present": health["huggingface_provider_present"],
        "expected_hf_model_present": health["expected_hf_model_present"],
        "cli_validation": cli_validation,
    }

    write_json(paths.state_root / "openclaw" / "sync_status.json", result)
    EventBus(paths).publish(
        Event(
            type=EVENT_OPENCLAW_CONFIG_SYNCED,
            source="openclaw",
            payload=result,
        )
    )
    logger.info(
        "[openclaw] sync repo=%s live=%s synced=%s hf_ready=%s",
        repo_path,
        live_path,
        result["openclaw_config_sync"],
        result["hf_fallback_ready"],
    )

    if not result["openclaw_config_sync"]:
        raise RuntimeError("OpenClaw config sync completed but managed sections still drift.")
    if validate_cli and not cli_validation.get("ok"):
        raise RuntimeError(
            "OpenClaw CLI validation failed after sync: "
            f"{cli_validation.get('stderr') or cli_validation.get('stdout') or 'unknown error'}"
        )
    return result


def decide_openclaw_fallback(
    http_status: int,
    *,
    attempted_backend: str = "claude-cli",
    attempted_model: str = "claude-cli/claude-sonnet-4-6",
    emit_event: bool = True,
) -> dict[str, Any]:
    paths = load_paths()
    health = build_openclaw_health()
    should_fallback = http_status in FALLBACK_STATUS_CODES and health["hf_fallback_ready"]
    decision = {
        "ts": now_iso(),
        "http_status": http_status,
        "attempted_backend": attempted_backend,
        "attempted_model": attempted_model,
        "should_fallback": should_fallback,
        "fallback_provider": DEFAULT_FALLBACK_PROVIDER if should_fallback else None,
        "fallback_model": health.get("live_hf_model_id") if should_fallback else None,
        "reason": "anthropic_overloaded" if should_fallback else (
            "hf_not_ready" if http_status in FALLBACK_STATUS_CODES else "status_not_supported"
        ),
    }

    if emit_event:
        append_jsonl(paths.state_root / "openclaw" / "fallback_events.jsonl", decision)
        EventBus(paths).publish(
            Event(
                type=EVENT_OPENCLAW_FALLBACK_TRIGGERED,
                source="openclaw",
                payload=decision,
            )
        )
    return decision
