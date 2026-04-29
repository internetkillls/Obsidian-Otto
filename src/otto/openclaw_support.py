from __future__ import annotations

# MIGRATION: migrate to MCP — see config/migration-bridges.yaml BRIDGE-004, BRIDGE-005, BRIDGE-006
# OpenClaw should own its config; Otto should receive state/pipeline events only after MCP is live.

import hashlib
import json
import os
import socket
import subprocess
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .adapters.qmd.manifest import build_qmd_manifest, qmd_manifest_health
from .config import load_env_file, load_paths, repo_root
from .events import (
    Event,
    EventBus,
    EVENT_OPENCLAW_FALLBACK_TRIGGERED,
    EVENT_QMD_INDEX_REFRESHED,
)
from .logging_utils import append_jsonl, get_logger
from .openclaw_guardrails import sanitize_generated_dreaming_artifacts, sync_openclaw_cron_contract
from .state import now_iso, read_json, write_json


OPENCLAW_RELATIVE_PATH = Path(".openclaw") / "openclaw.json"
OPENCLAW_LIVE_PATH = Path.home() / ".openclaw" / "openclaw.json"
OPENCLAW_GATEWAY_CMD_PATH = Path.home() / ".openclaw" / "gateway.cmd"
OPENCLAW_DEFAULT_GATEWAY_PORT = 18789
DEFAULT_FALLBACK_PROVIDER = "huggingface"
DEFAULT_FALLBACK_MODEL = "Qwen/Qwen2.5-72B-Instruct"
FALLBACK_STATUS_CODES = {529}
MANAGED_SECTION_PATHS: tuple[tuple[str, ...], ...] = (
    ("agents", "defaults", "cliBackends"),
    ("agents", "defaults", "models"),
    ("agents", "defaults", "heartbeat"),
    ("agents", "defaults", "blockStreamingBreak"),
    ("agents", "defaults", "contextInjection"),
    ("agents", "defaults", "bootstrapMaxChars"),
    ("agents", "defaults", "bootstrapTotalMaxChars"),
    ("agents", "defaults", "systemPromptOverride"),
    ("models", "providers"),
    ("env",),
)


def repo_openclaw_config_path() -> Path:
    return repo_root() / OPENCLAW_RELATIVE_PATH


def live_openclaw_config_path() -> Path:
    return OPENCLAW_LIVE_PATH


def live_openclaw_gateway_cmd_path() -> Path:
    return OPENCLAW_GATEWAY_CMD_PATH


def live_openclaw_logs_dir() -> Path:
    return Path.home() / ".openclaw" / "logs"


def _normalize_json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clone_json(data: Any) -> Any:
    return json.loads(json.dumps(data))


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


def _set_section(data: dict[str, Any], path_parts: tuple[str, ...], value: Any) -> None:
    current: dict[str, Any] = data
    for part in path_parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[path_parts[-1]] = _clone_json(value)


def _managed_hashes(data: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path_parts in MANAGED_SECTION_PATHS:
        key = ".".join(path_parts)
        section = _get_section(data, path_parts)
        hashes[key] = _sha256_text(_normalize_json_text(section))
    return hashes


def _otto_env_contract() -> dict[str, str]:
    paths = load_paths()
    repo = getattr(paths, "repo_root", repo_root())
    state_root = getattr(paths, "state_root", repo / "state")
    vault_path = getattr(paths, "vault_path", None)
    vault_host = os.environ.get("OTTO_VAULT_HOST") or str(vault_path or "")
    return {
        "OTTO_REPO_ROOT": str(repo),
        "OTTO_VAULT_HOST": vault_host,
        "OTTO_VAULT_PATH": vault_host,
        "OTTO_STATE_ROOT": str(state_root),
        "OTTO_LAUNCHER": "otto.bat",
        "OTTO_LOOP_MODE": "local",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }


def _with_otto_contract(config: dict[str, Any]) -> dict[str, Any]:
    merged = _clone_json(config)
    env = merged.setdefault("env", {})
    shell_env = env.setdefault("shellEnv", {})
    shell_env["enabled"] = True
    shell_env.setdefault("timeoutMs", 5000)

    heartbeat = (((merged.setdefault("agents", {})).setdefault("defaults", {})).setdefault("heartbeat", {}))
    heartbeat["every"] = "2m"
    return merged


def _backup_live_config(path: Path, ts: str) -> Path | None:
    if not path.exists():
        return None
    backup_name = f"{path.stem}_{ts.replace(':', '').replace('-', '').replace('T', '_').replace('+', '_').replace('.', '')}.bak.json"
    backup_path = load_paths().state_root / "openclaw" / "backups" / backup_name
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def _openclaw_gateway_port() -> int:
    raw = os.environ.get("OPENCLAW_GATEWAY_PORT")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass

    gateway_cmd = live_openclaw_gateway_cmd_path()
    if gateway_cmd.exists():
        for line in gateway_cmd.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if "OPENCLAW_GATEWAY_PORT=" not in line:
                continue
            value = line.split("OPENCLAW_GATEWAY_PORT=", 1)[1].strip().strip('"')
            try:
                return int(value)
            except ValueError:
                break
    return OPENCLAW_DEFAULT_GATEWAY_PORT


def _gateway_port_open(port: int, *, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            return sock.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


def _find_openclaw_gateway_pids() -> list[int]:
    if sys.platform != "win32":
        return []
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -match 'openclaw\\\\dist\\\\index\\.js gateway' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        value = line.strip()
        if not value:
            continue
        try:
            pids.append(int(value))
        except ValueError:
            continue
    return pids


def restart_openclaw_gateway(*, wait_seconds: int = 30) -> dict[str, Any]:
    gateway_cmd = live_openclaw_gateway_cmd_path()
    port = _openclaw_gateway_port()
    before_pids = _find_openclaw_gateway_pids()
    port_before = _gateway_port_open(port)
    log_dir = gateway_cmd.parent / "logs"
    stdout_log = log_dir / "gateway-reload.out.log"
    stderr_log = log_dir / "gateway-reload.err.log"

    if not gateway_cmd.exists():
        return {
            "ok": False,
            "reason": "gateway-cmd-missing",
            "gateway_cmd": str(gateway_cmd),
            "port": port,
            "before_pids": before_pids,
            "port_open_before": port_before,
        }

    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_log.write_text("", encoding="utf-8")
    stderr_log.write_text("", encoding="utf-8")

    stop_exit = 0
    if before_pids:
        stop_command = (
            f"Stop-Process -Id {','.join(str(pid) for pid in before_pids)} -Force -ErrorAction Stop"
        )
        stop_result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", stop_command],
            capture_output=True,
            text=True,
            check=False,
        )
        stop_exit = stop_result.returncode
        if stop_exit != 0:
            return {
                "ok": False,
                "reason": "gateway-stop-failed",
                "gateway_cmd": str(gateway_cmd),
                "port": port,
                "before_pids": before_pids,
                "port_open_before": port_before,
                "stop_exit": stop_exit,
                "stderr": stop_result.stderr.strip(),
            }
        time.sleep(1.0)

    start_exit = 0
    start_pid: int | None = None
    if sys.platform == "win32":
        start_command = (
            f"Start-Process -FilePath 'cmd.exe' "
            f"-ArgumentList '/c','{gateway_cmd}' "
            f"-WorkingDirectory '{gateway_cmd.parent}' "
            f"-WindowStyle Hidden "
            f"-RedirectStandardOutput '{stdout_log}' "
            f"-RedirectStandardError '{stderr_log}'"
        )
        start_result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", start_command],
            capture_output=True,
            text=True,
            check=False,
        )
        start_exit = start_result.returncode
        if start_exit != 0:
            return {
                "ok": False,
                "reason": "gateway-start-failed",
                "gateway_cmd": str(gateway_cmd),
                "port": port,
                "before_pids": before_pids,
                "port_open_before": port_before,
                "stop_exit": stop_exit,
                "start_exit": start_exit,
                "stderr": start_result.stderr.strip(),
                "stdout_log": str(stdout_log),
                "stderr_log": str(stderr_log),
            }
    else:
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        start_proc = subprocess.Popen(
            ["cmd", "/c", str(gateway_cmd)],
            cwd=gateway_cmd.parent,
            stdout=stdout_log.open("w", encoding="utf-8"),
            stderr=stderr_log.open("w", encoding="utf-8"),
            creationflags=creationflags,
        )
        start_pid = start_proc.pid

    deadline = time.time() + max(wait_seconds, 1)
    after_pids: list[int] = []
    port_open_after = False
    while time.time() < deadline:
        time.sleep(1.0)
        after_pids = _find_openclaw_gateway_pids()
        port_open_after = _gateway_port_open(port)
        if after_pids and port_open_after:
            return {
                "ok": True,
                "reason": "gateway-restarted",
                "gateway_cmd": str(gateway_cmd),
                "port": port,
                "before_pids": before_pids,
                "after_pids": after_pids,
                "port_open_before": port_before,
                "port_open_after": port_open_after,
                "stop_exit": stop_exit,
                "start_exit": start_exit,
                "start_pid": start_pid,
                "stdout_log": str(stdout_log),
                "stderr_log": str(stderr_log),
            }

    return {
        "ok": False,
        "reason": "gateway-restart-timeout",
        "gateway_cmd": str(gateway_cmd),
        "port": port,
        "before_pids": before_pids,
        "after_pids": after_pids,
        "port_open_before": port_before,
        "port_open_after": port_open_after,
        "stop_exit": stop_exit,
        "start_exit": start_exit,
        "start_pid": start_pid,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }


def _http_get_json(url: str, *, timeout_seconds: float) -> tuple[int | None, Any | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None)
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, None, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, None, str(exc)

    try:
        return status, json.loads(body), None
    except json.JSONDecodeError:
        return status, None, body


def openclaw_gateway_probe_state_path() -> Path:
    return load_paths().state_root / "openclaw" / "gateway_probe.json"


def _parse_restart_log_ts(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y %H:%M:%S,%f").astimezone()
    except ValueError:
        return None


def _recent_restart_window(*, window_seconds: int = 600) -> dict[str, Any]:
    restart_log = live_openclaw_logs_dir() / "gateway-restart.log"
    if not restart_log.exists():
        return {
            "active": False,
            "state": "none",
            "last_event_at": None,
            "last_event": None,
        }

    event_at: datetime | None = None
    event_state = "none"
    event_line: str | None = None
    for line in restart_log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        match = line[:24] if line.startswith("[") and "]" in line else None
        if not match:
            continue
        timestamp = _parse_restart_log_ts(match.strip("[]"))
        if timestamp is None:
            continue
        lowered = line.lower()
        if "restart failed" in lowered:
            event_at = timestamp
            event_state = "failed"
            event_line = line
        elif "restart attempt" in lowered:
            event_at = timestamp
            event_state = "attempting"
            event_line = line
        elif "restart succeeded" in lowered or "restart complete" in lowered:
            event_at = timestamp
            event_state = "recovered"
            event_line = line

    if event_at is None:
        return {
            "active": False,
            "state": "none",
            "last_event_at": None,
            "last_event": None,
        }

    active = event_state in {"attempting", "failed"} and datetime.now().astimezone() - event_at <= timedelta(seconds=window_seconds)
    return {
        "active": active,
        "state": event_state,
        "last_event_at": event_at.isoformat(timespec="seconds"),
        "last_event": event_line,
    }


def _merge_probe_state(probe: dict[str, Any]) -> dict[str, Any]:
    state_path = openclaw_gateway_probe_state_path()
    previous = read_json(state_path, default={}) or {}
    checked_at = now_iso()
    last_failure_at = previous.get("last_failure_at")
    last_failure_reason = previous.get("last_failure_reason")
    if probe.get("ok"):
        pass
    else:
        last_failure_at = checked_at
        last_failure_reason = probe.get("reason")
    history = {
        "checked_at": checked_at,
        "last_ok_at": checked_at if probe.get("ok") else previous.get("last_ok_at"),
        "last_failure_at": last_failure_at,
        "last_failure_reason": last_failure_reason,
    }
    stored = dict(probe)
    stored.update(history)
    write_json(state_path, stored)
    return history


def _gateway_shadow_telegram_enabled() -> bool | None:
    shadow_path = repo_root() / "state" / "openclaw" / "ubuntu-shadow" / "openclaw.json"
    shadow_config, _ = _load_config(shadow_path)
    if shadow_config is None:
        return None
    telegram = ((shadow_config.get("channels") or {}).get("telegram") or {})
    return bool(telegram.get("enabled")) if isinstance(telegram, dict) else None


def probe_openclaw_gateway(
    *,
    timeout_seconds: float = 5.0,
    port: int | None = None,
    host: str = "127.0.0.1",
    runtime: str = "windows-live",
) -> dict[str, Any]:
    port = port or _openclaw_gateway_port()
    base_url = f"http://{host}:{port}"
    pids = _find_openclaw_gateway_pids()
    port_open = _gateway_port_open(port, timeout=min(max(timeout_seconds, 0.1), 1.0))
    health_status, health_json, health_error = _http_get_json(
        f"{base_url}/health",
        timeout_seconds=timeout_seconds,
    )
    root_status, _, root_error = _http_get_json(
        f"{base_url}/",
        timeout_seconds=timeout_seconds,
    )
    health_ok = bool(health_status == 200 and isinstance(health_json, dict) and health_json.get("ok") is True)
    restart_window = _recent_restart_window()
    root_reachable = root_status is not None
    websocket_reachable = bool(port_open and runtime == "wsl-shadow")
    ok = bool(port_open and (health_ok or root_reachable or websocket_reachable))
    if ok:
        if health_ok:
            reason = "gateway-http-healthy"
        elif root_reachable:
            reason = "gateway-root-reachable"
        else:
            reason = "gateway-port-open-websocket"
    elif restart_window.get("active"):
        reason = "gateway-restart-window"
    else:
        reason = "gateway-http-unhealthy"
    qmd_index = build_qmd_index_health() if runtime == "wsl-shadow" else None
    telegram_enabled = _gateway_shadow_telegram_enabled() if runtime == "wsl-shadow" else None
    result = {
        "ok": ok,
        "reason": reason,
        "status": "healthy" if ok else ("restarting" if restart_window.get("active") else "unhealthy"),
        "runtime": runtime,
        "host": host,
        "port": port,
        "base_url": base_url,
        "pids": pids,
        "port_open": port_open,
        "websocket_reachable": websocket_reachable,
        "health_status": health_status,
        "health_json": health_json,
        "health_error": health_error,
        "root_status": root_status,
        "root_error": root_error,
        "auth_required": health_status in {401, 403} or root_status in {401, 403},
        "body_snippet": str(root_error or health_error or "")[:500],
        "telegram_enabled": telegram_enabled,
        "qmd_index_seen": bool(qmd_index and qmd_index.get("ok")),
        "qmd_index": qmd_index,
        "cli_bypass_recommended": ok,
        "transient_restart_window": bool(restart_window.get("active")),
        "restart_state": restart_window.get("state"),
        "restart_last_event_at": restart_window.get("last_event_at"),
        "restart_last_event": restart_window.get("last_event"),
    }
    result.update(_merge_probe_state(result))
    return result


def reload_openclaw_plugin_surface(*, wait_seconds: int = 30, hard_restart: bool = False) -> dict[str, Any]:
    live_path = live_openclaw_config_path()
    live_config, live_error = _load_config(live_path)
    if live_config is None:
        return {
            "ok": False,
            "reason": "live-config-unavailable",
            "live_config_path": str(live_path),
            "error": live_error,
        }

    config = _clone_json(live_config)
    meta = config.setdefault("meta", {})
    meta["lastTouchedAt"] = now_iso()
    meta["lastTouchedBy"] = "otto.plugin_reload"

    live_path.write_text(_normalize_json_text(config), encoding="utf-8")
    # Give the OpenClaw config watcher a small window to see the change before we probe/restart.
    time.sleep(1.0)

    probe_after_touch = probe_openclaw_gateway(timeout_seconds=5.0)
    restart_result: dict[str, Any] | None = None
    final_probe = probe_after_touch

    if hard_restart or not probe_after_touch.get("ok"):
        restart_result = restart_openclaw_gateway(wait_seconds=wait_seconds)
        final_probe = probe_openclaw_gateway(timeout_seconds=5.0)

    return {
        "ok": bool(final_probe.get("ok")),
        "reason": "plugin-surface-reloaded" if final_probe.get("ok") else "plugin-surface-reload-incomplete",
        "live_config_path": str(live_path),
        "touch_performed": True,
        "hard_restart": hard_restart,
        "probe_after_touch": probe_after_touch,
        "restart_attempted": restart_result is not None,
        "restart_result": restart_result,
        "final_probe": final_probe,
    }


def openclaw_capabilities_path() -> Path:
    return load_paths().state_root / "openclaw" / "capabilities.json"


def openclaw_env_contract_path() -> Path:
    return load_paths().state_root / "openclaw" / "env_contract.json"


def _build_capabilities(config: dict[str, Any]) -> dict[str, Any]:
    paths = load_paths()
    repo = getattr(paths, "repo_root", repo_root())
    vault_path = getattr(paths, "vault_path", None)
    plugins = ((config.get("plugins") or {}).get("entries") or {})
    return {
        "ottoVaultContext": bool(vault_path),
        "agentContextTuning": False,
        "ottoLoopReady": (repo / "otto.bat").exists(),
        "ottoInitialize": (repo / "scripts" / "shell" / "otto_bootstrap.bat").exists(),
        "dreamMemoryFeed": bool((((plugins.get("memory-core") or {}).get("config") or {}).get("dreaming") or {}).get("enabled")),
        "kairosTelemetry": (repo / "scripts" / "manage" / "run_kairos.py").exists(),
        "morpheusContinuity": (repo / "scripts" / "manage" / "run_dream.py").exists(),
        "ottoRepairMode": True,
    }


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


def openclaw_sync_status_path() -> Path:
    return load_paths().state_root / "openclaw" / "sync_status.json"


def openclaw_fallback_events_path() -> Path:
    return load_paths().state_root / "openclaw" / "fallback_events.jsonl"


def latest_openclaw_sync_status() -> dict[str, Any]:
    return read_json(openclaw_sync_status_path(), default={}) or {}


def qmd_refresh_status_path() -> Path:
    return load_paths().state_root / "openclaw" / "qmd_refresh_status.json"


def _extract_qmd_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    qmd = (config.get("memory") or {}).get("qmd", {})
    sources = qmd.get("sources")
    if isinstance(sources, list) and sources:
        return [item for item in sources if isinstance(item, dict)]

    paths = qmd.get("paths")
    normalized: list[dict[str, Any]] = []
    if not isinstance(paths, list):
        return normalized

    for item in paths:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": item.get("name") or item.get("id"),
                "path": item.get("path"),
                "pattern": item.get("pattern"),
            }
        )
    return normalized


def _qmd_source_host_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/")
    if sys.platform == "win32" and normalized.lower().startswith("/mnt/") and len(normalized) > 6:
        drive = normalized[5]
        if normalized[6] == "/" and drive.isalpha():
            windows_tail = normalized[7:].replace("/", "\\")
            return Path(f"{drive.upper()}:\\{windows_tail}")
    return Path(raw_path).expanduser()


def build_qmd_index_health(live_config_path: Path | None = None) -> dict[str, Any]:
    """Validate that QMD is configured and that all declared source paths exist with markdown files."""
    live_path = live_config_path or live_openclaw_config_path()
    registry_manifest = qmd_manifest_health(build_qmd_manifest()) if live_config_path is None else None
    candidate_paths = [live_path]
    repo_path = repo_openclaw_config_path()
    if repo_path != live_path:
        candidate_paths.append(repo_path)

    paths = load_paths()
    vault_fallback = str(getattr(paths, "vault_path", "") or "")
    chosen_config: dict[str, Any] | None = None
    chosen_source: Path | None = None
    chosen_error: str | None = None
    for candidate_path in candidate_paths:
        candidate_config, candidate_error = _load_config(candidate_path)
        if candidate_config is None:
            chosen_error = candidate_error
            continue
        if (candidate_config.get("memory") or {}).get("backend") == "qmd" or _extract_qmd_sources(candidate_config):
            chosen_config = candidate_config
            chosen_source = candidate_path
            break
        chosen_error = candidate_error

    if chosen_config is None:
        return {
            "ok": False,
            "error": chosen_error or "qmd config missing",
            "sources": [],
            "manifest": registry_manifest,
        }

    backend = (chosen_config.get("memory") or {}).get("backend")
    source_health: list[dict[str, Any]] = []
    for src in _extract_qmd_sources(chosen_config):
        raw_path = str(src.get("path", ""))
        for env_var, fallback in (("OTTO_VAULT_PATH", vault_fallback), ("QMD_SOCKET_PATH", "")):
            raw_path = raw_path.replace(f"${{{env_var}}}", os.environ.get(env_var) or fallback)
        src_path = _qmd_source_host_path(raw_path)
        exists = src_path.exists()
        md_count = len(list(src_path.rglob("*.md"))) if exists else 0
        source_health.append(
            {
                "id": src.get("id"),
                "path": raw_path,
                "host_path": str(src_path),
                "exists": exists,
                "md_file_count": md_count,
                "ok": exists,
                "populated": md_count > 0,
            }
        )

    all_ok = backend == "qmd" and bool(source_health) and all(item["ok"] for item in source_health)
    return {
        "ok": all_ok,
        "config_source": str(chosen_source) if chosen_source else None,
        "backend": backend,
        "backend_is_qmd": backend == "qmd",
        "manifest": registry_manifest,
        "sources": source_health,
        "source_count": len(source_health),
        "sources_all_ok": bool(source_health) and all(item["ok"] for item in source_health),
    }


def run_qmd_index_refresh(timeout_seconds: int = 60) -> dict[str, Any]:
    """Call the OpenClaw memory index command. Graceful no-op if the CLI is not present."""
    cooldown_seconds = 15 * 60
    state_path = qmd_refresh_status_path()
    refresh_state = read_json(state_path, default={}) or {}
    health = build_qmd_index_health()
    now_epoch = int(time.time())
    now_stamp = now_iso()

    def _write_state(payload: dict[str, Any]) -> None:
        write_json(state_path, payload)

    def _record_failure(kind: str, message: str, *, skipped: bool) -> dict[str, Any]:
        payload = {
            "last_attempt_at": now_stamp,
            "last_attempt_epoch": now_epoch,
            "last_failure_at": now_stamp,
            "last_failure_epoch": now_epoch,
            "last_success_at": refresh_state.get("last_success_at"),
            "last_success_epoch": refresh_state.get("last_success_epoch"),
            "failure_kind": kind,
            "failure_message": message,
            "consecutive_failures": int(refresh_state.get("consecutive_failures") or 0) + (0 if skipped else 1),
            "cooldown_seconds": cooldown_seconds,
        }
        _write_state(payload)
        return payload

    last_failure_epoch = int(refresh_state.get("last_failure_epoch") or 0)
    cooldown_remaining = max(cooldown_seconds - (now_epoch - last_failure_epoch), 0) if last_failure_epoch else 0

    if not health.get("backend_is_qmd"):
        state_payload = _record_failure("backend-not-qmd", "QMD backend is not active", skipped=True)
        return {
            "ok": False,
            "skipped": True,
            "reason": "qmd-backend-inactive",
            "stderr": "QMD backend is not active",
            "qmd_index": health,
            "state": state_payload,
        }

    if not health.get("ok"):
        message = "QMD index preflight is unhealthy"
        reason = "qmd-preflight-unhealthy"
        if cooldown_remaining > 0:
            reason = "qmd-cooldown-active"
            message = f"{message}; cooldown active for {cooldown_remaining}s"
        state_payload = _record_failure("preflight-unhealthy", message, skipped=True)
        return {
            "ok": False,
            "skipped": True,
            "reason": reason,
            "stderr": message,
            "cooldown_remaining_seconds": cooldown_remaining,
            "qmd_index": health,
            "state": state_payload,
        }

    if cooldown_remaining > 0 and str(refresh_state.get("failure_kind") or "") in {"command-failed", "timeout"}:
        state_payload = _record_failure(
            str(refresh_state.get("failure_kind") or "command-failed"),
            str(refresh_state.get("failure_message") or "Previous qmd refresh failed"),
            skipped=True,
        )
        return {
            "ok": False,
            "skipped": True,
            "reason": "qmd-cooldown-active",
            "stderr": f"Previous qmd refresh failed; cooldown active for {cooldown_remaining}s",
            "cooldown_remaining_seconds": cooldown_remaining,
            "qmd_index": health,
            "state": state_payload,
        }

    cli_path = shutil.which("openclaw")
    if not cli_path:
        state_payload = _record_failure("openclaw-missing", "openclaw not on PATH", skipped=True)
        return {
            "ok": False,
            "skipped": True,
            "reason": "openclaw-missing",
            "stderr": "openclaw not on PATH",
            "qmd_index": health,
            "state": state_payload,
        }
    try:
        proc = subprocess.run(
            [cli_path, "memory", "index"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        state_payload = _record_failure("timeout", f"timed out after {timeout_seconds}s", skipped=False)
        return {
            "ok": False,
            "skipped": False,
            "reason": "timeout",
            "stderr": f"timed out after {timeout_seconds}s",
            "qmd_index": health,
            "state": state_payload,
        }

    ok = proc.returncode == 0
    if ok:
        state_payload = {
            "last_attempt_at": now_stamp,
            "last_attempt_epoch": now_epoch,
            "last_success_at": now_stamp,
            "last_success_epoch": now_epoch,
            "last_failure_at": None,
            "last_failure_epoch": None,
            "failure_kind": None,
            "failure_message": None,
            "consecutive_failures": 0,
            "cooldown_seconds": cooldown_seconds,
        }
        _write_state(state_payload)
    else:
        failure_message = (proc.stderr or proc.stdout or "").strip() or f"qmd refresh failed with exit code {proc.returncode}"
        state_payload = _record_failure("command-failed", failure_message, skipped=False)
    return {
        "ok": ok,
        "skipped": False,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "qmd_index": health,
        "state": state_payload,
    }


def build_openclaw_health(
    repo_config_path: Path | None = None,
    live_config_path: Path | None = None,
) -> dict[str, Any]:
    repo_path = repo_config_path or repo_openclaw_config_path()
    live_path = live_config_path or live_openclaw_config_path()
    repo_config, repo_error = _load_config(repo_path)
    live_config, live_error = _load_config(live_path)
    if repo_config is not None:
        repo_config = _with_otto_contract(repo_config)
    if live_config is not None:
        live_config = _with_otto_contract(live_config)
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
        "reference_source": str(repo_path),
        "live_config_path": str(live_path),
        "repo_exists": repo_config is not None,
        "repo_parse_error": repo_error,
        "live_exists": live_config is not None,
        "live_parse_error": live_error,
        "repo_managed_hashes": repo_hashes,
        "live_managed_hashes": live_hashes,
        "managed_hashes_match": managed_hashes_match,
        "config_drift_free": managed_hashes_match,
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
        "otto_env_contract_path": str(openclaw_env_contract_path()),
        "otto_env_contract": read_json(openclaw_env_contract_path(), default=_otto_env_contract()) or _otto_env_contract(),
        "capabilities_path": str(openclaw_capabilities_path()),
        "capabilities": read_json(openclaw_capabilities_path(), default={}) or {},
        "qmd_index": build_qmd_index_health(live_path),
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
    live_data, live_error = _load_config(live_path)
    sync_ts = now_iso()
    changed_sections: list[str] = []
    backup_path: Path | None = None
    sync_performed = False
    boundary_mode = "managed-sync"
    use_live_boundary_guardrails = repo_config_path is None and live_config_path is None

    if source_data is None:
        source_data = {}
        boundary_mode = "observational"
        health = build_openclaw_health(repo_path, live_path)
    else:
        source_with_contract = _with_otto_contract(source_data)
        live_base = _clone_json(live_data) if live_data is not None else {}
        live_existing = live_path.read_text(encoding="utf-8") if live_path.exists() else None
        merged_live = _clone_json(live_base)

        for path_parts in MANAGED_SECTION_PATHS:
            source_section = _get_section(source_with_contract, path_parts)
            current_section = _get_section(merged_live, path_parts)
            if _normalize_json_text(current_section) != _normalize_json_text(source_section):
                changed_sections.append(".".join(path_parts))
            _set_section(merged_live, path_parts, source_section)

        source_memory = source_with_contract.get("memory")
        current_memory = merged_live.get("memory")
        if _normalize_json_text(current_memory) != _normalize_json_text(source_memory):
            merged_live["memory"] = _clone_json(source_memory) if source_memory is not None else None
            changed_sections.append("memory")

        merged_live = _with_otto_contract(merged_live)
        merged_live_text = _normalize_json_text(merged_live)
        if live_existing != merged_live_text:
            backup_path = _backup_live_config(live_path, sync_ts)
            live_path.parent.mkdir(parents=True, exist_ok=True)
            live_path.write_text(merged_live_text, encoding="utf-8")
            sync_performed = True

        health = build_openclaw_health(repo_path, live_path)

    result = {
        "ts": sync_ts,
        "reference_source": str(repo_path),
        "live_config_path": str(live_path),
        "boundary_mode": boundary_mode,
        "sync_performed": sync_performed,
        "config_drift_free": health["config_drift_free"],
        "openclaw_config_sync": health["config_drift_free"],
        "managed_hashes_match": health["managed_hashes_match"],
        "anthropic_ready": health["anthropic_ready"],
        "hf_fallback_ready": health["hf_fallback_ready"],
        "huggingface_provider_present": health["huggingface_provider_present"],
        "expected_hf_model_present": health["expected_hf_model_present"],
        "reference_parse_error": source_error,
        "live_parse_error": live_error,
        "backup_path": str(backup_path) if backup_path else None,
        "changed_sections": changed_sections,
        "otto_env_contract": _otto_env_contract(),
        "qmd_index": build_qmd_index_health(live_path),
        "cli_validation": {
            "skipped": True,
            "reason": "Otto no longer performs OpenClaw subprocess validation.",
        },
    }
    if use_live_boundary_guardrails:
        cron_sync = sync_openclaw_cron_contract(apply_fixes=True)
        dreaming_guardrails = sanitize_generated_dreaming_artifacts()
    else:
        cron_sync = {
            "ok": True,
            "reason": "cron-contract-skipped-for-custom-config-paths",
            "sync_performed": False,
        }
        dreaming_guardrails = {
            "ok": True,
            "reason": "dreaming-guardrails-skipped-for-custom-config-paths",
            "report_change_count": 0,
            "daily_note_change_count": 0,
        }
    result["cron_contract"] = cron_sync
    result["dreaming_guardrails"] = dreaming_guardrails

    write_json(paths.state_root / "openclaw" / "sync_status.json", result)
    write_json(openclaw_env_contract_path(), _otto_env_contract())
    write_json(openclaw_capabilities_path(), _build_capabilities(source_data))
    logger.info(
        "[openclaw] boundary-report repo=%s live=%s sync=%s drift_free=%s hf_ready=%s",
        repo_path,
        live_path,
        result["sync_performed"],
        result["config_drift_free"],
        result["hf_fallback_ready"],
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
