from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any

from ..config import load_paths, repo_root
from ..logging_utils import append_jsonl
from ..openclaw_shadow import build_ubuntu_live_config, build_ubuntu_shadow_config
from ..openclaw_support import build_qmd_index_health, probe_openclaw_gateway
from ..path_compat import is_wsl
from ..state import now_iso, write_json
from ..wsl_support import build_wsl_health
from .runtime_owner import (
    STATE_ROLLBACK_WINDOWS,
    STATE_WSL_LIVE,
    STATE_WSL_SHADOW_GATEWAY,
    build_runtime_owner,
    build_single_owner_lock,
    detect_windows_openclaw_process,
    write_runtime_owner,
    write_single_owner_lock,
)


WSL_DISTRO = "Ubuntu"
WSL_OPENCLAW_CONFIG = "/home/joshu/.openclaw/openclaw.json"
WSL_OPENCLAW_HOME = "/home/joshu/.openclaw"
WSL_OPENCLAW_BINARY = "/home/joshu/.npm-global/bin/openclaw"
WSL_QMD_BINARY = "/usr/bin/qmd"
WSL_BRIDGE_SOURCE_PATH = "/mnt/c/Users/joshu/Obsidian-Otto/packages/openclaw-otto-bridge"
WSL_BRIDGE_INSTALL_PATH = "/home/joshu/.openclaw/plugins-local/obsidian-otto-bridge"


def _runtime_dir() -> Path:
    return load_paths().state_root / "runtime"


def _ubuntu_live_dir() -> Path:
    return load_paths().state_root / "openclaw" / "ubuntu-live"


def migration_last_path() -> Path:
    return _runtime_dir() / "wsl_live_migration_last.json"


def migration_runs_path() -> Path:
    return _runtime_dir() / "wsl_live_migration_runs.jsonl"


def rollback_plan_path() -> Path:
    return _runtime_dir() / "rollback_plan.json"


def preview_config_path() -> Path:
    return _ubuntu_live_dir() / "openclaw.json.preview"


def live_meta_path() -> Path:
    return _ubuntu_live_dir() / "openclaw.live.meta.json"


def _run(command: list[str], *, timeout_seconds: int = 60, input_text: str | None = None) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            input=input_text,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "command": command,
            "exit_code": 124,
            "stdout": "",
            "stderr": f"timeout after {timeout_seconds}s",
        }
    except OSError as exc:
        return {
            "ok": False,
            "command": command,
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "ok": proc.returncode == 0,
        "command": command,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }


def _run_wsl_bash(script: str, *, timeout_seconds: int = 60, input_text: str | None = None) -> dict[str, Any]:
    if is_wsl():
        command = ["bash", "-lc", script]
    else:
        command = ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", script]
    return _run(command, timeout_seconds=timeout_seconds, input_text=input_text)


def _wsl_env_script(body: str) -> str:
    return (
        "export PATH=\"/usr/local/bin:/usr/bin:/bin:$HOME/.npm-global/bin:$HOME/.local/bin\"; "
        f"{body}"
    )


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("token", "secret", "password", "apikey", "api_key")):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = _redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _write_preview(config: dict[str, Any]) -> Path:
    path = preview_config_path()
    write_json(path, _redact_secrets(config))
    return path


def _load_repo_openclaw_config() -> dict[str, Any]:
    path = repo_root() / ".openclaw" / "openclaw.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _load_wsl_config() -> dict[str, Any]:
    result = _run_wsl_bash(
        _wsl_env_script(f"test -f {WSL_OPENCLAW_CONFIG} && cat {WSL_OPENCLAW_CONFIG} || true"),
        timeout_seconds=20,
    )
    stdout = str(result.get("stdout") or "").strip()
    if not stdout:
        return {}
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_wsl_config(config: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    return _run_wsl_bash(
        _wsl_env_script(f"mkdir -p {WSL_OPENCLAW_HOME} && cat > {WSL_OPENCLAW_CONFIG}"),
        timeout_seconds=30,
        input_text=payload,
    )


def _sync_wsl_bridge_package() -> dict[str, Any]:
    script = (
        f"test -d {WSL_BRIDGE_SOURCE_PATH} || exit 9; "
        f"rm -rf {WSL_BRIDGE_INSTALL_PATH}; "
        f"mkdir -p $(dirname {WSL_BRIDGE_INSTALL_PATH}); "
        f"cp -R {WSL_BRIDGE_SOURCE_PATH} {WSL_BRIDGE_INSTALL_PATH}; "
        f"chmod -R go-w {WSL_BRIDGE_INSTALL_PATH}; "
        f"echo {WSL_BRIDGE_INSTALL_PATH}"
    )
    result = _run_wsl_bash(_wsl_env_script(script), timeout_seconds=60)
    return {
        "ok": result.get("ok"),
        "install_path": (result.get("stdout") or "").strip() or WSL_BRIDGE_INSTALL_PATH,
        "raw": result,
    }


def _backup_wsl_config(timestamp: str) -> dict[str, Any]:
    backup_path = f"{WSL_OPENCLAW_CONFIG}.bak.{timestamp.replace(':', '').replace('-', '')}"
    result = _run_wsl_bash(
        _wsl_env_script(
            f"if test -f {WSL_OPENCLAW_CONFIG}; then cp {WSL_OPENCLAW_CONFIG} {backup_path}; echo {backup_path}; fi"
        ),
        timeout_seconds=20,
    )
    return {
        "ok": result.get("ok"),
        "backup_path": (result.get("stdout") or "").strip() or None,
        "raw": result,
    }


def _wsl_telegram_enabled(config: dict[str, Any]) -> bool | None:
    telegram = ((config.get("channels") or {}).get("telegram") or {})
    if not isinstance(telegram, dict):
        return None
    return bool(telegram.get("enabled"))


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        try:
            return sock.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


def _rollback_available() -> bool:
    return (repo_root() / ".openclaw" / "openclaw.json").exists() and (repo_root() / "scripts" / "shell" / "native-fallback.bat").exists()


def _make_owner_payload(*, gateway_port: int, live: bool) -> dict[str, Any]:
    runtime_state = STATE_WSL_LIVE if live else STATE_ROLLBACK_WINDOWS
    return {
        "version": 2,
        "runtime_state": runtime_state,
        "gateway_owner": "ubuntu_openclaw" if live else "windows_openclaw",
        "telegram_owner": "ubuntu_openclaw" if live else "windows_openclaw",
        "qmd_owner": "ubuntu_wsl",
        "windows_openclaw": {
            "role": "rollback" if live else "live",
            "gateway_owner": not live,
            "config_path": str(repo_root() / ".openclaw" / "openclaw.json"),
            "telegram_enabled": not live,
        },
        "ubuntu_openclaw": {
            "role": "live" if live else "shadow",
            "user": "joshu",
            "home": "/home/joshu",
            "binary": WSL_OPENCLAW_BINARY,
            "gateway_port": gateway_port,
            "gateway_reachable": False,
            "config_path": WSL_OPENCLAW_CONFIG,
            "telegram_enabled": live,
        },
        "qmd": {
            "owner": "ubuntu_wsl",
            "command": WSL_QMD_BINARY,
            "binary": WSL_QMD_BINARY,
            "version": "2.1.0",
        },
        "docker": {
            "owner": "ubuntu_wsl",
        },
        "vault": {
            "host": "windows_filesystem",
            "mounted_in_wsl": True,
        },
        "safety": {
            "cutover": live,
            "telegram_single_owner_required": True,
            "raw_social_to_qmd_allowed": False,
            "raw_social_to_vault_allowed": False,
        },
    }


def _record_run(result: dict[str, Any]) -> None:
    write_json(migration_last_path(), result)
    append_jsonl(migration_runs_path(), result)


def _write_rollback_plan(gateway_port: int) -> dict[str, Any]:
    plan = {
        "version": 1,
        "generated_at": now_iso(),
        "runtime_state_target": STATE_ROLLBACK_WINDOWS,
        "gateway_port": gateway_port,
        "steps": [
            "Stop Ubuntu OpenClaw gateway if it is still running.",
            "Run python3 -m otto.cli wsl-live-rollback --gateway-port 18790 --write.",
            "Restart Windows OpenClaw manually or via otto.bat native-fallback.",
            "Verify runtime-smoke and single-owner-lock after rollback.",
        ],
    }
    write_json(rollback_plan_path(), plan)
    return plan


def build_wsl_live_preflight(*, gateway_port: int = 18790, write: bool = True) -> dict[str, Any]:
    checked_at = now_iso()
    health = build_wsl_health()
    config = _load_wsl_config()
    telegram_enabled = _wsl_telegram_enabled(config)
    user_check = _run_wsl_bash(_wsl_env_script("whoami"), timeout_seconds=10)
    home_check = _run_wsl_bash(_wsl_env_script("printf %s \"$HOME\""), timeout_seconds=10)
    qmd_path_check = _run_wsl_bash(_wsl_env_script("command -v qmd"), timeout_seconds=10)
    qmd_binary_check = _run_wsl_bash(_wsl_env_script(f"test -x {WSL_QMD_BINARY} && echo qmd-binary-ok || echo qmd-binary-missing"), timeout_seconds=10)
    openclaw_path_check = _run_wsl_bash(_wsl_env_script("command -v openclaw"), timeout_seconds=10)
    docker_check = _run_wsl_bash(_wsl_env_script("docker info >/dev/null 2>&1 && echo docker-ok || echo docker-missing"), timeout_seconds=20)
    qmd_version = _run_wsl_bash(_wsl_env_script(f"{WSL_QMD_BINARY} --version"), timeout_seconds=20)
    openclaw_version = _run_wsl_bash(_wsl_env_script("openclaw --version"), timeout_seconds=20)
    config_validate = _run_wsl_bash(_wsl_env_script("openclaw config validate --json"), timeout_seconds=60)
    plugins_doctor = _run_wsl_bash(_wsl_env_script("openclaw plugins doctor"), timeout_seconds=180)
    memory_status = _run_wsl_bash(_wsl_env_script("openclaw memory status --deep"), timeout_seconds=60)
    bridge_probe = _run_wsl_bash(_wsl_env_script(f"test -d {WSL_BRIDGE_SOURCE_PATH} && echo installable || echo missing"), timeout_seconds=10)
    gateway = probe_openclaw_gateway(port=gateway_port, runtime="wsl-live", timeout_seconds=3.0)
    windows_process = detect_windows_openclaw_process()
    owner = build_runtime_owner()
    lock = build_single_owner_lock()
    rollback_plan = _write_rollback_plan(gateway_port)
    qmd_index = build_qmd_index_health()

    port_free = not _port_open(gateway_port)
    qmd_path = str(qmd_path_check.get("stdout") or "").strip()
    openclaw_path = str(openclaw_path_check.get("stdout") or "").strip()
    checks = {
        "wsl_user": "green" if str(user_check.get("stdout") or "").strip() == "joshu" else "red",
        "home": "green" if str(home_check.get("stdout") or "").strip() == "/home/joshu" else "red",
        "qmd_native": "green" if qmd_path == WSL_QMD_BINARY and "qmd-binary-ok" in str(qmd_binary_check.get("stdout") or "") and qmd_version.get("ok") else "red",
        "qmd_version": "green" if qmd_version.get("ok") else "red",
        "openclaw_native": "green" if openclaw_path.startswith("/") and not openclaw_path.startswith("/mnt/") and not openclaw_path.endswith(".exe") else "red",
        "openclaw_version": "green" if openclaw_version.get("ok") else "red",
        "docker": "green" if "docker-ok" in str(docker_check.get("stdout") or "") else "red",
        "config_validate": "green" if config_validate.get("ok") else "red",
        "plugin_doctor": "green" if plugins_doctor.get("ok") else "red",
        "bridge_installable": "green" if "installable" in str(bridge_probe.get("stdout") or "") else "red",
        "qmd_memory": "green" if memory_status.get("ok") and qmd_index.get("ok") else "red",
        "gateway_port": "green" if port_free or gateway.get("ok") else "red",
        "windows_openclaw_stopped": "green" if not windows_process.get("running") else "red",
        "single_owner_lock": "green" if lock.get("ok") else "red",
        "ubuntu_telegram_disabled_before_promote": "green" if telegram_enabled is not True else "red",
        "telegram_owner_valid": "green" if owner.get("telegram_owner") in {"windows_openclaw", "none"} else "red",
        "rollback_path": "green" if _rollback_available() else "red",
    }

    blockers: list[str] = []
    if checks["windows_openclaw_stopped"] == "red":
        blockers.append("Windows OpenClaw appears to be running; stop it before enabling Ubuntu Telegram.")
    if checks["ubuntu_telegram_disabled_before_promote"] == "red":
        blockers.append("Ubuntu OpenClaw already has Telegram enabled; preflight refuses to promote from an ambiguous state.")
    if checks["single_owner_lock"] == "red":
        blockers.append("Single-owner lock is already violated or runtime owner state is inconsistent.")
    for key in ("wsl_user", "home", "qmd_native", "qmd_version", "openclaw_native", "openclaw_version", "docker", "config_validate", "plugin_doctor", "bridge_installable", "qmd_memory", "gateway_port", "telegram_owner_valid", "rollback_path"):
        if checks[key] != "green":
            blockers.append(f"Preflight check failed: {key}")

    warnings: list[str] = []
    if gateway.get("ok"):
        warnings.append("Gateway port is already reachable; promote will only update ownership/config state and will not auto-start a second gateway.")
    if owner.get("runtime_state") == STATE_WSL_LIVE:
        warnings.append("Owner state already says S4_WSL_LIVE; verify the current lock and gateway health before re-promoting.")

    result = {
        "ok": not blockers,
        "state": "PREFLIGHT_PASS" if not blockers else "PREFLIGHT_BLOCKED",
        "checked_at": checked_at,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "next_required_action": None if not blockers else "Stop Windows OpenClaw and repair any red preflight checks before promote.",
        "owner": owner,
        "single_owner_lock": lock,
        "windows_openclaw": windows_process,
        "wsl_facts": {
            "user": user_check,
            "home": home_check,
            "qmd_path": qmd_path_check,
            "qmd_binary": qmd_binary_check,
            "openclaw_path": openclaw_path_check,
            "docker": docker_check,
            "health": health,
        },
        "gateway": gateway,
        "rollback_plan": rollback_plan,
        "wsl_openclaw_config_path": WSL_OPENCLAW_CONFIG,
    }
    if write:
        _record_run(result)
    return result


def _write_live_sidecar(*, gateway_port: int, backup_path: str | None, start_command: str) -> Path:
    metadata = {
        "version": 1,
        "generated_at": now_iso(),
        "runtime_state": STATE_WSL_LIVE,
        "gateway_port": gateway_port,
        "config_path": WSL_OPENCLAW_CONFIG,
        "backup_path": backup_path,
        "bridge_install_command": f"openclaw plugins install -l {WSL_BRIDGE_INSTALL_PATH}",
        "start_command": start_command,
        "notes": [
            "Do not commit Telegram secrets.",
            "Do not add plugins.local or _otto_shadow metadata to openclaw.json.",
            "Windows OpenClaw must remain stopped while Ubuntu owns Telegram.",
            "Mirror the Otto bridge into a WSL-local plugin directory before linking it.",
        ],
    }
    path = live_meta_path()
    write_json(path, metadata)
    return path


def promote_wsl_live(*, gateway_port: int = 18790, write: bool = False) -> dict[str, Any]:
    preflight = build_wsl_live_preflight(gateway_port=gateway_port, write=False)
    repo_config = _load_repo_openclaw_config()
    live_config = build_ubuntu_live_config(repo_config, port=gateway_port)
    preview_path = _write_preview(live_config)
    owner_preview = _make_owner_payload(gateway_port=gateway_port, live=True)
    manual_commands = [
        "Stop Windows OpenClaw before enabling Ubuntu Telegram.",
        f"wsl -d Ubuntu -- bash -lc 'export PATH=\"$HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin\"; openclaw gateway run --port {gateway_port}'",
        f"otto.bat native-fallback  # rollback macro if WSL live fails",
    ]

    if not write:
        return {
            "ok": preflight.get("ok"),
            "state": "PROMOTE_DRY_RUN_READY" if preflight.get("ok") else "PROMOTE_DRY_RUN_BLOCKED",
            "state_changed": False,
            "created_ids": [],
            "updated_ids": [],
            "warnings": preflight.get("warnings", []),
            "blockers": preflight.get("blockers", []),
            "quarantined": [],
            "next_required_action": None if preflight.get("ok") else preflight.get("next_required_action"),
            "preflight": preflight,
            "owner_preview": owner_preview,
            "config_preview_path": str(preview_path),
            "config_delta": {
                "gateway.port": gateway_port,
                "channels.telegram.enabled": True,
                "channels.telegram.shadowDisabled_removed": True,
                "memory.qmd.command": WSL_QMD_BINARY,
                "plugins.local_present": False,
                "_otto_shadow_present": False,
            },
            "manual_commands": manual_commands,
        }

    if not preflight.get("ok"):
        result = {
            "ok": False,
            "state": "PROMOTE_BLOCKED",
            "state_changed": False,
            "created_ids": [],
            "updated_ids": [],
            "warnings": preflight.get("warnings", []),
            "blockers": preflight.get("blockers", []),
            "quarantined": [],
            "next_required_action": preflight.get("next_required_action"),
        }
        _record_run(result)
        return result

    timestamp = now_iso()
    backup = _backup_wsl_config(timestamp)
    config_write = _write_wsl_config(live_config)
    bridge_sync = _sync_wsl_bridge_package()
    plugin_install = _run_wsl_bash(
        _wsl_env_script(f"openclaw plugins install -l {WSL_BRIDGE_INSTALL_PATH}"),
        timeout_seconds=180,
    )
    config_validate = _run_wsl_bash(_wsl_env_script("openclaw config validate --json"), timeout_seconds=60)
    plugins_doctor = _run_wsl_bash(_wsl_env_script("openclaw plugins doctor"), timeout_seconds=180)
    memory_status = _run_wsl_bash(_wsl_env_script("openclaw memory status --deep"), timeout_seconds=60)
    start_command = f"openclaw gateway run --port {gateway_port}"
    sidecar = _write_live_sidecar(gateway_port=gateway_port, backup_path=backup.get("backup_path"), start_command=start_command)

    post_checks = [config_write.get("ok"), bridge_sync.get("ok"), plugin_install.get("ok"), config_validate.get("ok"), plugins_doctor.get("ok"), memory_status.get("ok")]
    owner_result = None
    lock_result = None
    if all(post_checks):
        owner_result = write_runtime_owner(owner_preview)
        lock_result = write_single_owner_lock()

    blockers: list[str] = []
    if not config_write.get("ok"):
        blockers.append("Failed to write Ubuntu live openclaw.json.")
    if not bridge_sync.get("ok"):
        blockers.append("Failed to sync the Otto bridge package into a WSL-local plugin path.")
    if not plugin_install.get("ok"):
        blockers.append("Failed to link Otto bridge plugin in Ubuntu OpenClaw.")
    if not config_validate.get("ok"):
        blockers.append("Ubuntu OpenClaw config validation failed after live promotion.")
    if not plugins_doctor.get("ok"):
        blockers.append("OpenClaw plugins doctor failed after live promotion.")
    if not memory_status.get("ok"):
        blockers.append("OpenClaw memory status --deep failed after live promotion.")
    if lock_result is not None and not lock_result.get("ok"):
        blockers.append("Single-owner lock failed after owner state update.")

    result = {
        "ok": not blockers,
        "state": "PROMOTE_WRITTEN" if not blockers else "PROMOTE_FAILED",
        "state_changed": True,
        "created_ids": [],
        "updated_ids": ["state/runtime/owner.json", "state/runtime/single_owner_lock.json"] if not blockers else [],
        "warnings": preflight.get("warnings", []),
        "blockers": blockers,
        "quarantined": [],
        "next_required_action": None if not blockers else "Inspect the failed promote checks before starting the gateway.",
        "config_preview_path": str(preview_path),
        "live_sidecar_path": str(sidecar),
        "backup": backup,
        "config_write": config_write,
        "bridge_sync": bridge_sync,
        "plugin_install": plugin_install,
        "plugin_install_retry": None,
        "config_validate": config_validate,
        "plugins_doctor": plugins_doctor,
        "memory_status": memory_status,
        "owner": owner_result.get("owner") if owner_result else owner_preview,
        "single_owner_lock": lock_result.get("lock") if lock_result else None,
        "start_command": start_command,
        "launcher_hint": "otto.bat wsl-gateway-start",
        "manual_commands": manual_commands,
    }
    _record_run(result)
    return result


def rollback_wsl_live(*, gateway_port: int = 18790, write: bool = False) -> dict[str, Any]:
    if not write:
        return {
            "ok": False,
            "state": "ROLLBACK_REQUIRES_WRITE",
            "state_changed": False,
            "created_ids": [],
            "updated_ids": [],
            "warnings": [],
            "blockers": ["Rollback is destructive to live ownership state and requires --write."],
            "quarantined": [],
            "next_required_action": "Rerun with --write after stopping the Ubuntu gateway.",
        }

    repo_config = _load_repo_openclaw_config()
    shadow_config = build_ubuntu_shadow_config(repo_config, port=gateway_port)
    shadow_preview_path = repo_root() / "state" / "openclaw" / "ubuntu-shadow" / "openclaw.json"
    shadow_preview_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(shadow_preview_path, _redact_secrets(shadow_config))
    preview_path = _write_preview(shadow_config)
    backup = _backup_wsl_config(now_iso())
    config_write = _write_wsl_config(shadow_config)
    owner_payload = _make_owner_payload(gateway_port=gateway_port, live=False)
    owner_result = write_runtime_owner(owner_payload) if config_write.get("ok") else None
    lock_result = write_single_owner_lock() if config_write.get("ok") else None

    blockers: list[str] = []
    if not config_write.get("ok"):
        blockers.append("Failed to disable Ubuntu Telegram in WSL config.")
    if lock_result is not None and not lock_result.get("ok"):
        blockers.append("Single-owner lock failed after rollback owner update.")

    result = {
        "ok": not blockers,
        "state": "ROLLBACK_WRITTEN" if not blockers else "ROLLBACK_FAILED",
        "state_changed": True,
        "created_ids": [],
        "updated_ids": ["state/runtime/owner.json", "state/runtime/single_owner_lock.json"] if not blockers else [],
        "warnings": [],
        "blockers": blockers,
        "quarantined": [],
        "next_required_action": None if not blockers else "Inspect rollback config write and owner lock state.",
        "config_preview_path": str(preview_path),
        "backup": backup,
        "config_write": config_write,
        "owner": owner_result.get("owner") if owner_result else owner_payload,
        "single_owner_lock": lock_result.get("lock") if lock_result else None,
        "manual_windows_restart": "Restart Windows OpenClaw manually or run otto.bat native-fallback.",
    }
    _record_run(result)
    return result


def build_wsl_live_status(*, gateway_port: int = 18790) -> dict[str, Any]:
    from .runtime_smoke import build_runtime_smoke

    owner = build_runtime_owner()
    lock = build_single_owner_lock()
    config = _load_wsl_config()
    gateway = probe_openclaw_gateway(port=gateway_port, runtime="wsl-live", timeout_seconds=3.0)
    windows_process = detect_windows_openclaw_process()
    smoke = build_runtime_smoke(gateway_port=gateway_port, write=False)
    rollback_available = _rollback_available()

    return {
        "ok": bool(lock.get("ok")),
        "state": "WSL_LIVE_STATUS_READY",
        "runtime_state": owner.get("runtime_state"),
        "gateway_owner": owner.get("gateway_owner"),
        "telegram_owner": owner.get("telegram_owner"),
        "qmd_owner": owner.get("qmd_owner"),
        "current_config_telegram_enabled": _wsl_telegram_enabled(config),
        "gateway": {
            "ok": gateway.get("ok"),
            "reason": gateway.get("reason"),
            "port": gateway.get("port"),
        },
        "windows_openclaw_process": windows_process,
        "single_owner_lock": lock,
        "runtime_smoke": {
            "ok": smoke.get("ok"),
            "result": smoke.get("result"),
        },
        "rollback_available": rollback_available,
        "rollback_plan": str(rollback_plan_path()) if rollback_plan_path().exists() else None,
    }
