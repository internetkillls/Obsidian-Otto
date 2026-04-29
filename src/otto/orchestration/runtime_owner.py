from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..adapters.qmd.manifest import load_qmd_manifest
from ..config import load_paths, repo_root
from ..openclaw_support import qmd_refresh_status_path
from ..state import now_iso, read_json, write_json


OWNER_VERSION = 2
WINDOWS_GATEWAY_PORT = 18789
UBUNTU_GATEWAY_PORT = 18790
WSL_DISTRO = "Ubuntu"
WSL_OPENCLAW_CONFIG = "/home/joshu/.openclaw/openclaw.json"

STATE_WSL_SHADOW_MEMORY = "S2B_WSL_SHADOW_MEMORY_READY"
STATE_WSL_SHADOW_GATEWAY = "S2C_WSL_SHADOW_GATEWAY_READY"
STATE_WSL_LIVE = "S4_WSL_LIVE"
STATE_ROLLBACK_WINDOWS = "S5_ROLLBACK_WINDOWS"

SHADOW_CONFIG_DIR = Path("state") / "openclaw" / "ubuntu-shadow"


def runtime_owner_path() -> Path:
    return load_paths().state_root / "runtime" / "owner.json"


def single_owner_lock_path() -> Path:
    return load_paths().state_root / "runtime" / "single_owner_lock.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _telegram_enabled(config: dict[str, Any]) -> bool | None:
    channels = config.get("channels")
    if not isinstance(channels, dict):
        return None
    telegram = channels.get("telegram")
    if not isinstance(telegram, dict):
        return None
    return bool(telegram.get("enabled"))


def _gateway_ok() -> bool:
    gateway_probe = read_json(load_paths().state_root / "openclaw" / "gateway_probe.json", default={}) or {}
    return bool(gateway_probe.get("ok") and int(gateway_probe.get("port") or 0) == UBUNTU_GATEWAY_PORT)


def _load_ubuntu_runtime_config() -> dict[str, Any]:
    script = f"test -f {WSL_OPENCLAW_CONFIG} && cat {WSL_OPENCLAW_CONFIG} || true"
    if Path("/proc/version").exists():
        command = ["bash", "-lc", script]
    else:
        command = ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", script]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except OSError:
        return {}
    if proc.returncode != 0:
        return {}
    stdout = (proc.stdout or "").strip()
    if not stdout:
        return {}
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def detect_windows_openclaw_process() -> dict[str, Any]:
    if Path("/proc/version").exists():
        powershell = "powershell.exe"
    else:
        powershell = "powershell"
    command = (
        "$procs = Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -match 'openclaw' }; "
        "$items = @(); "
        "foreach ($proc in $procs) { "
        "$items += [PSCustomObject]@{ pid=$proc.ProcessId; name=$proc.Name; commandLine=$proc.CommandLine } "
        "}; "
        "$items | ConvertTo-Json -Depth 4 -Compress"
    )
    try:
        proc = subprocess.run(
            [powershell, "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except OSError as exc:
        return {"ok": False, "running": False, "reason": str(exc), "processes": []}
    if proc.returncode != 0:
        return {"ok": False, "running": False, "reason": (proc.stderr or "").strip(), "processes": []}
    raw = (proc.stdout or "").strip()
    if not raw:
        return {"ok": True, "running": False, "processes": []}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "running": False, "reason": "invalid-json", "stdout": raw, "processes": []}
    if isinstance(data, dict):
        processes = [data]
    elif isinstance(data, list):
        processes = [item for item in data if isinstance(item, dict)]
    else:
        processes = []
    filtered: list[dict[str, Any]] = []
    for item in processes:
        command_line = str(item.get("commandLine") or "")
        lowered = command_line.lower()
        name = str(item.get("name") or "").lower()
        if "openclaw" not in lowered:
            continue
        if name in {"powershell.exe", "pwsh.exe", "python.exe", "python3.exe", "wsl.exe"}:
            continue
        if any(
            token in lowered
            for token in (
                "convertto-json",
                "get-ciminstance win32_process",
                "select-object -expandproperty processid",
                "config validate",
                "plugins doctor",
                "memory status --deep",
                "wsl.exe -d ubuntu -- bash -lc",
                "wsl -d ubuntu -- bash -lc",
                "python -m otto.cli",
                "$env:pythonpath",
                "invoke-webrequest",
                "runtime-smoke",
                "wsl-live-status",
                "command -v openclaw",
            )
        ):
            continue
        if not any(token in lowered for token in ("gateway", "telegram", "bot", "poll")) and name != "node.exe":
            continue
        filtered.append(
            {
                "pid": item.get("pid"),
                "name": item.get("name"),
                "command_line": command_line,
                "gateway": "gateway" in lowered,
                "telegram": "telegram" in lowered,
            }
        )
    return {
        "ok": True,
        "running": bool(filtered),
        "gateway_running": any(bool(item.get("gateway")) for item in filtered),
        "processes": filtered,
    }


def _build_auto_owner() -> dict[str, Any]:
    repo = repo_root()
    windows_config = _load_json(repo / ".openclaw" / "openclaw.json")
    ubuntu_config = _load_ubuntu_runtime_config() or _load_json(repo / SHADOW_CONFIG_DIR / "openclaw.json")
    qmd_manifest = load_qmd_manifest() or {}
    qmd_refresh = read_json(qmd_refresh_status_path(), default={}) or {}
    gateway_ok = _gateway_ok()

    windows_telegram = _telegram_enabled(windows_config)
    ubuntu_telegram = _telegram_enabled(ubuntu_config)
    telegram_owner = "none"
    if windows_telegram and not ubuntu_telegram:
        telegram_owner = "windows_openclaw"
    elif ubuntu_telegram and not windows_telegram:
        telegram_owner = "ubuntu_openclaw"
    elif ubuntu_telegram and windows_telegram:
        telegram_owner = "conflict"

    runtime_state = STATE_WSL_SHADOW_GATEWAY if gateway_ok else STATE_WSL_SHADOW_MEMORY
    gateway_owner = "windows_openclaw"
    if runtime_state == STATE_WSL_SHADOW_GATEWAY:
        gateway_owner = "ubuntu_openclaw"

    return {
        "version": OWNER_VERSION,
        "runtime_state": runtime_state,
        "gateway_owner": gateway_owner,
        "telegram_owner": telegram_owner,
        "qmd_owner": "ubuntu_wsl",
        "updated_at": now_iso(),
        "windows_openclaw": {
            "role": "live_or_rollback",
            "gateway_owner": gateway_owner == "windows_openclaw",
            "config_path": str(repo / ".openclaw" / "openclaw.json"),
            "telegram_enabled": windows_telegram,
        },
        "ubuntu_openclaw": {
            "role": "shadow",
            "user": "joshu",
            "home": "/home/joshu",
            "binary": "/home/joshu/.npm-global/bin/openclaw",
            "gateway_port": UBUNTU_GATEWAY_PORT,
            "gateway_reachable": gateway_ok,
            "config_path": str(repo / SHADOW_CONFIG_DIR / "openclaw.json"),
            "telegram_enabled": ubuntu_telegram,
        },
        "qmd": {
            "owner": "ubuntu_wsl",
            "command": "/usr/bin/qmd",
            "binary": "/usr/bin/qmd",
            "version": "2.1.0",
            "manifest_ok": bool(qmd_manifest.get("ok")),
            "last_reindex_ok": bool(qmd_refresh.get("last_success_at")),
            "last_reindex_at": qmd_refresh.get("last_success_at"),
        },
        "docker": {
            "owner": "ubuntu_wsl",
        },
        "vault": {
            "host": "windows_filesystem",
            "mounted_in_wsl": True,
        },
        "safety": {
            "cutover": False,
            "telegram_single_owner_required": True,
            "raw_social_to_qmd_allowed": False,
            "raw_social_to_vault_allowed": False,
        },
    }


def build_runtime_owner() -> dict[str, Any]:
    auto = _build_auto_owner()
    existing = _load_json(runtime_owner_path())
    runtime_state = str(existing.get("runtime_state") or "")
    if runtime_state not in {STATE_WSL_LIVE, STATE_ROLLBACK_WINDOWS}:
        return auto

    owner = auto
    owner["runtime_state"] = runtime_state
    owner["gateway_owner"] = existing.get("gateway_owner") or owner.get("gateway_owner")
    owner["telegram_owner"] = existing.get("telegram_owner") or owner.get("telegram_owner")
    owner["qmd_owner"] = existing.get("qmd_owner") or owner.get("qmd_owner")
    owner["updated_at"] = now_iso()

    for key in ("windows_openclaw", "ubuntu_openclaw", "qmd", "docker", "vault", "safety"):
        existing_section = existing.get(key)
        if isinstance(existing_section, dict):
            section = owner.setdefault(key, {})
            if isinstance(section, dict):
                section.update(existing_section)

    owner["windows_openclaw"]["observed_telegram_enabled"] = auto["windows_openclaw"].get("telegram_enabled")
    owner["ubuntu_openclaw"]["observed_telegram_enabled"] = auto["ubuntu_openclaw"].get("telegram_enabled")
    owner["ubuntu_openclaw"]["gateway_reachable"] = auto["ubuntu_openclaw"].get("gateway_reachable")
    owner["qmd"]["manifest_ok"] = auto["qmd"].get("manifest_ok")
    owner["qmd"]["last_reindex_ok"] = auto["qmd"].get("last_reindex_ok")
    owner["qmd"]["last_reindex_at"] = auto["qmd"].get("last_reindex_at")
    return owner


def write_runtime_owner(owner: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = owner or build_runtime_owner()
    payload["version"] = OWNER_VERSION
    payload["updated_at"] = now_iso()
    write_json(runtime_owner_path(), payload)
    return {"ok": True, "path": str(runtime_owner_path()), "owner": payload}


def build_single_owner_lock() -> dict[str, Any]:
    owner = build_runtime_owner()
    windows_process = detect_windows_openclaw_process()
    windows_enabled = owner.get("windows_openclaw", {}).get("telegram_enabled")
    ubuntu_enabled = owner.get("ubuntu_openclaw", {}).get("telegram_enabled")
    telegram_enabled = [
        name
        for name, enabled in (("windows_openclaw", windows_enabled), ("ubuntu_openclaw", ubuntu_enabled))
        if enabled is True
    ]
    unknown = [
        name
        for name, enabled in (("windows_openclaw", windows_enabled), ("ubuntu_openclaw", ubuntu_enabled))
        if enabled is None
    ]

    failures: list[str] = []
    runtime_state = owner.get("runtime_state")
    gateway_owner = owner.get("gateway_owner")
    telegram_owner = owner.get("telegram_owner")

    if len(telegram_enabled) > 1:
        failures.append("dual-telegram-owner")
    if runtime_state == STATE_WSL_SHADOW_GATEWAY and ubuntu_enabled is True:
        failures.append("shadow-runtime-has-ubuntu-telegram-enabled")
    if runtime_state == STATE_WSL_LIVE and ubuntu_enabled is not True:
        failures.append("wsl-live-requires-ubuntu-telegram-enabled")
    if runtime_state == STATE_WSL_LIVE and windows_enabled is True:
        failures.append("wsl-live-requires-windows-telegram-disabled")
    if runtime_state == STATE_WSL_LIVE and gateway_owner != "ubuntu_openclaw":
        failures.append("wsl-live-requires-ubuntu-gateway-owner")
    if runtime_state == STATE_ROLLBACK_WINDOWS and gateway_owner != "windows_openclaw":
        failures.append("rollback-requires-windows-gateway-owner")
    if runtime_state == STATE_ROLLBACK_WINDOWS and ubuntu_enabled is True:
        failures.append("rollback-requires-ubuntu-telegram-disabled")
    if telegram_owner == "ubuntu_openclaw" and windows_process.get("running"):
        failures.append("windows-openclaw-process-running-during-ubuntu-telegram-ownership")
    if gateway_owner not in {"windows_openclaw", "ubuntu_openclaw"}:
        failures.append("invalid-gateway-owner")
    if telegram_owner not in {"windows_openclaw", "ubuntu_openclaw", "none", "conflict"}:
        failures.append("invalid-telegram-owner")
    if telegram_owner == "conflict":
        failures.append("telegram-owner-conflict")

    ok = not failures
    if runtime_state == STATE_WSL_LIVE and ok:
        classification = "safe-wsl-live"
    elif runtime_state == STATE_ROLLBACK_WINDOWS and ok:
        classification = "safe-rollback"
    elif runtime_state in {STATE_WSL_SHADOW_MEMORY, STATE_WSL_SHADOW_GATEWAY} and ok:
        classification = "safe-shadow"
    else:
        classification = "unsafe-owner-conflict"

    return {
        "version": OWNER_VERSION,
        "checked_at": now_iso(),
        "ok": ok,
        "runtime_state": runtime_state,
        "gateway_owner": gateway_owner,
        "telegram_owner": telegram_owner,
        "telegram_single_owner": len(telegram_enabled) <= 1,
        "telegram_enabled_owners": telegram_enabled,
        "unknown_telegram_owners": unknown,
        "ubuntu_shadow_telegram_disabled": owner.get("ubuntu_openclaw", {}).get("telegram_enabled") is not True,
        "windows_openclaw_process": windows_process,
        "gateway_ports": {
            "windows_openclaw": WINDOWS_GATEWAY_PORT,
            "ubuntu_openclaw": owner.get("ubuntu_openclaw", {}).get("gateway_port"),
        },
        "cutover": runtime_state == STATE_WSL_LIVE,
        "classification": classification,
        "failures": failures,
    }


def write_single_owner_lock(lock: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = lock or build_single_owner_lock()
    write_json(single_owner_lock_path(), payload)
    return {"ok": bool(payload.get("ok")), "path": str(single_owner_lock_path()), "lock": payload}
