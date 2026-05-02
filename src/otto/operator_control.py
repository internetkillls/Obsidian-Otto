from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from .config import repo_root
from .governance_utils import state_root
from .openclaw_shadow import DEFAULT_SHADOW_PORT, build_ubuntu_live_config, build_ubuntu_shadow_config
from .openclaw_support import build_openclaw_health, probe_openclaw_gateway, restart_openclaw_gateway, sync_openclaw_config
from .orchestration.runtime_owner import STATE_WSL_LIVE, build_runtime_owner, decide_gateway_owner
from .orchestration.wsl_live_migration import rollback_wsl_live
from .state import now_iso, read_json, write_json


WSL_DISTRO = "Ubuntu"
WSL_GATEWAY_PORT = 18790
NATIVE_GATEWAY_PORT = 18789


def operator_state_path() -> Path:
    return state_root() / "operator" / "openclaw_runtime.json"


def _run(command: Sequence[str], *, timeout_seconds: int = 60, check: bool = False) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            list(command),
            cwd=repo_root(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=check,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "command": list(command),
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": 124,
            "command": list(command),
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": f"timeout after {timeout_seconds}s",
        }
    except OSError as exc:
        return {
            "ok": False,
            "exit_code": 127,
            "command": list(command),
            "stdout": "",
            "stderr": str(exc),
        }


def _run_input(command: Sequence[str], text: str, *, timeout_seconds: int = 60) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            list(command),
            cwd=repo_root(),
            input=text,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "command": list(command),
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": 124,
            "command": list(command),
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": f"timeout after {timeout_seconds}s",
        }
    except OSError as exc:
        return {
            "ok": False,
            "exit_code": 127,
            "command": list(command),
            "stdout": "",
            "stderr": str(exc),
        }


def _run_wsl_openclaw(args: Sequence[str], *, timeout_seconds: int = 60) -> dict[str, Any]:
    script = (
        "export PATH=\"/home/joshu/.local/bin:/home/joshu/.npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"; "
        f"/home/joshu/.npm-global/bin/openclaw {' '.join(args)}"
    )
    return _run(["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", script], timeout_seconds=timeout_seconds)


def _wsl_gateway_service_available() -> dict[str, Any]:
    status = _run_wsl_openclaw(["gateway", "status"], timeout_seconds=30)
    return {"ok": "Service: systemd" in str(status.get("stdout") or ""), "status": status}


def _json(path: Path) -> dict[str, Any]:
    data = read_json(path, default={}) or {}
    return data if isinstance(data, dict) else {}


def _canonical_wsl_config(native_config: dict[str, Any], runtime_state: str) -> dict[str, Any]:
    if runtime_state == STATE_WSL_LIVE:
        return build_ubuntu_live_config(native_config, port=WSL_GATEWAY_PORT)
    return build_ubuntu_shadow_config(native_config, port=WSL_GATEWAY_PORT)


def _qmd_paths(config: dict[str, Any]) -> list[dict[str, str]]:
    qmd = (config.get("memory") or {}).get("qmd") or {}
    raw_paths = qmd.get("paths") or qmd.get("sources") or []
    paths: list[dict[str, str]] = []
    if not isinstance(raw_paths, list):
        return paths
    for item in raw_paths:
        if not isinstance(item, dict):
            continue
        paths.append(
            {
                "name": str(item.get("name") or item.get("id") or ""),
                "path": str(item.get("path") or ""),
                "pattern": str(item.get("pattern") or ""),
            }
        )
    return sorted(paths, key=lambda item: item["name"])


def _normalize_path_for_parity(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.lower().startswith("c:/"):
        normalized = "/mnt/c/" + normalized[3:]
    return normalized.rstrip("/")


def _qmd_path_signature(config: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [
        (item["name"], _normalize_path_for_parity(item["path"]), item["pattern"])
        for item in _qmd_paths(config)
    ]


def _cron_summary() -> dict[str, Any]:
    cron = _json(state_root() / "openclaw" / "cron_contract_v1.json")
    jobs = cron.get("jobs") if isinstance(cron.get("jobs"), list) else []
    enabled = [job for job in jobs if isinstance(job, dict) and job.get("enabled") is True]
    unsafe = [
        job.get("job_key")
        for job in enabled
        if isinstance(job, dict)
        and (job.get("schedule") or {}).get("tz") not in {"Asia/Bangkok", None}
    ]
    return {
        "exists": bool(cron),
        "drift_free": bool((cron.get("validation") or {}).get("drift_free", False)),
        "job_count": len(jobs),
        "enabled_job_count": len(enabled),
        "timezone_issues": unsafe,
    }


def _heartbeat_summary() -> dict[str, Any]:
    heartbeat = _json(state_root() / "openclaw" / "heartbeat" / "otto_heartbeat_manifest.json")
    tools = heartbeat.get("tools") if isinstance(heartbeat.get("tools"), list) else []
    return {
        "exists": bool(heartbeat),
        "tool_count": len(tools),
        "tools": [tool.get("name") for tool in tools if isinstance(tool, dict)],
    }


def wsl_environment_status() -> dict[str, Any]:
    check = _run(
        [
            "wsl.exe",
            "-d",
            WSL_DISTRO,
            "--",
            "bash",
            "-lc",
            (
                "export PATH=\"/usr/local/bin:/usr/bin:/bin:/home/joshu/.npm-global/bin:/home/joshu/.local/bin\"; "
                "printf 'openclaw='; if command -v openclaw >/dev/null 2>&1; then command -v openclaw; "
                "elif [ -x /home/joshu/.npm-global/bin/openclaw ]; then echo /home/joshu/.npm-global/bin/openclaw; else echo; fi; "
                "printf 'qmd='; if command -v qmd >/dev/null 2>&1; then command -v qmd; "
                "elif [ -x /usr/bin/qmd ]; then echo /usr/bin/qmd; else echo; fi; "
                "printf 'repo='; test -d /mnt/c/Users/joshu/Obsidian-Otto && echo ok || echo missing; "
                "printf 'vault='; test -d '/mnt/c/Users/joshu/Josh Obsidian' && echo ok || echo missing"
            ),
        ],
        timeout_seconds=20,
    )
    stdout = str(check.get("stdout") or "")
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    openclaw_bin = fields.get("openclaw", "")
    qmd_bin = fields.get("qmd", "")
    return {
        "ok": bool(check.get("ok") and openclaw_bin and qmd_bin and fields.get("repo") == "ok" and fields.get("vault") == "ok"),
        "openclaw_bin": openclaw_bin,
        "qmd_bin": qmd_bin,
        "repo_visible": fields.get("repo") == "ok",
        "vault_visible": fields.get("vault") == "ok",
        "raw": check,
    }


def install_wsl_shadow_config() -> dict[str, Any]:
    config_path = state_root() / "openclaw" / "ubuntu-shadow" / "openclaw.json"
    source_path = repo_root() / ".openclaw" / "openclaw.json"
    if not source_path.exists():
        return {"ok": False, "reason": "missing-native-config", "path": str(source_path)}
    native_config = _json(source_path)
    shadow_config = build_ubuntu_shadow_config(native_config, port=DEFAULT_SHADOW_PORT)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(shadow_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    config_text = config_path.read_text(encoding="utf-8")
    install = _run_input(
        [
            "wsl.exe",
            "-d",
            WSL_DISTRO,
            "--",
            "bash",
            "-lc",
            "mkdir -p \"$HOME/.openclaw\" && cat > \"$HOME/.openclaw/openclaw.json\"",
        ],
        config_text,
        timeout_seconds=20,
    )
    return {
        "ok": bool(install.get("ok")),
        "source": str(config_path),
        "target": "~/.openclaw/openclaw.json",
        "install": install,
    }


def _set_telegram_enabled(config: dict[str, Any], enabled: bool) -> None:
    channels = config.setdefault("channels", {})
    telegram = channels.setdefault("telegram", {})
    telegram["enabled"] = enabled


def set_telegram_owner(owner: str) -> dict[str, Any]:
    if owner not in {"windows", "wsl"}:
        return {"ok": False, "reason": "invalid-owner", "owner": owner}
    native_path = repo_root() / ".openclaw" / "openclaw.json"
    wsl_path = state_root() / "openclaw" / "ubuntu-shadow" / "openclaw.json"
    native_config = _json(native_path)
    wsl_config = _json(wsl_path)
    if not native_config or not wsl_config:
        return {"ok": False, "reason": "missing-config", "native_path": str(native_path), "wsl_path": str(wsl_path)}
    _set_telegram_enabled(native_config, owner == "windows")
    _set_telegram_enabled(wsl_config, owner == "wsl")
    native_path.write_text(json.dumps(native_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    wsl_path.write_text(json.dumps(wsl_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {
        "ok": True,
        "owner": owner,
        "windows_telegram_enabled": owner == "windows",
        "wsl_telegram_enabled": owner == "wsl",
        "updated_at": now_iso(),
        "native_config": str(native_path),
        "wsl_shadow_config": str(wsl_path),
    }
    write_json(state_root() / "openclaw" / "telegram_owner_last.json", result)
    return result


def stop_native_gateway_for_wsl_cutover() -> dict[str, Any]:
    command = (
        "$procs = Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -match 'openclaw' -and $_.CommandLine -match 'gateway' }; "
        "$ids = @($procs | ForEach-Object { $_.ProcessId }); "
        "foreach ($id in $ids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }; "
        "$ids -join ','"
    )
    result = _run(["powershell", "-NoProfile", "-Command", command], timeout_seconds=20)
    return {
        "ok": bool(result.get("ok") or result.get("exit_code") == 1),
        "stopped_pids": [int(item) for item in str(result.get("stdout") or "").split(",") if item.strip().isdigit()],
        "raw": result,
    }


def operator_status(*, write: bool = True) -> dict[str, Any]:
    runtime_owner = build_runtime_owner()
    runtime_state = str(runtime_owner.get("runtime_state") or "")
    native_config = _json(repo_root() / ".openclaw" / "openclaw.json")
    wsl_config_path = state_root() / "openclaw" / ("ubuntu-live" if runtime_state == STATE_WSL_LIVE else "ubuntu-shadow") / ("openclaw.json.preview" if runtime_state == STATE_WSL_LIVE else "openclaw.json")
    wsl_config = _canonical_wsl_config(native_config, runtime_state)
    native_qmd = (native_config.get("memory") or {}).get("qmd") or {}
    wsl_qmd = (wsl_config.get("memory") or {}).get("qmd") or {}
    native_signature = _qmd_path_signature(native_config)
    wsl_signature = _qmd_path_signature(wsl_config)
    telegram_native = bool(((native_config.get("channels") or {}).get("telegram") or {}).get("enabled"))
    telegram_wsl = bool(((wsl_config.get("channels") or {}).get("telegram") or {}).get("enabled"))
    telegram_owners = [
        name
        for name, enabled in (("windows_openclaw", telegram_native), ("ubuntu_openclaw", telegram_wsl))
        if enabled
    ]
    parity = {
        "native_config": str(repo_root() / ".openclaw" / "openclaw.json"),
        "wsl_shadow_config": str(wsl_config_path),
        "qmd_backend_match": (native_config.get("memory") or {}).get("backend") == (wsl_config.get("memory") or {}).get("backend") == "qmd",
        "qmd_sources_match": native_signature == wsl_signature,
        "native_qmd_command": native_qmd.get("command"),
        "wsl_qmd_command": wsl_qmd.get("command"),
        "wsl_qmd_command_native": wsl_qmd.get("command") == "/usr/bin/qmd",
        "native_telegram_enabled": telegram_native,
        "wsl_telegram_enabled": telegram_wsl,
        "telegram_single_owner": len(telegram_owners) <= 1,
        "telegram_enabled_owners": telegram_owners,
        "gateway_ports": {
            "native": ((native_config.get("gateway") or {}).get("port") or NATIVE_GATEWAY_PORT),
            "wsl_shadow": ((wsl_config.get("gateway") or {}).get("port") or WSL_GATEWAY_PORT),
        },
    }
    cron = _cron_summary()
    heartbeat = _heartbeat_summary()
    wsl_env = wsl_environment_status()
    openclaw_health = build_openclaw_health()
    gateway = probe_openclaw_gateway(
        port=WSL_GATEWAY_PORT,
        runtime="wsl-live" if runtime_state == STATE_WSL_LIVE else "wsl-shadow",
        timeout_seconds=15.0,
    )
    ok = bool(
        parity["qmd_backend_match"]
        and parity["qmd_sources_match"]
        and parity["wsl_qmd_command_native"]
        and parity["telegram_single_owner"]
        and cron["exists"]
        and not cron["timezone_issues"]
        and heartbeat["exists"]
        and heartbeat["tool_count"] > 0
        and wsl_env["ok"]
        and gateway.get("ok")
    )
    result = {
        "ok": ok,
        "state": "OO_OPERATOR_PARITY_READY" if ok else "OO_OPERATOR_PARITY_NEEDS_REPAIR",
        "checked_at": now_iso(),
        "runtime_state": runtime_state,
        "parity": parity,
        "cron": cron,
        "heartbeat": heartbeat,
        "wsl_environment": {
            "ok": wsl_env.get("ok"),
            "openclaw_bin": wsl_env.get("openclaw_bin"),
            "qmd_bin": wsl_env.get("qmd_bin"),
            "repo_visible": wsl_env.get("repo_visible"),
            "vault_visible": wsl_env.get("vault_visible"),
            "stderr": (wsl_env.get("raw") or {}).get("stderr"),
        },
        "openclaw_health": {
            "config_drift_free": openclaw_health.get("config_drift_free"),
            "qmd_index_ok": (openclaw_health.get("qmd_index") or {}).get("ok"),
            "qmd_source_count": (openclaw_health.get("qmd_index") or {}).get("source_count"),
        },
        "wsl_gateway": {
            "ok": gateway.get("ok"),
            "reason": gateway.get("reason"),
            "port": gateway.get("port"),
            "telegram_enabled": gateway.get("telegram_enabled"),
            "qmd_index_seen": gateway.get("qmd_index_seen"),
        },
        "next_required_action": None if ok else "run operator-doctor or operator-repair",
    }
    if write:
        write_json(operator_state_path(), result)
    return result


def start_wsl_gateway(*, port: int = WSL_GATEWAY_PORT, wait_seconds: int = 60) -> dict[str, Any]:
    runtime_owner = build_runtime_owner()
    live_mode = runtime_owner.get("runtime_state") == STATE_WSL_LIVE
    log_dir = repo_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    out_log = log_dir / "openclaw-wsl-gateway.out.log"
    err_log = log_dir / "openclaw-wsl-gateway.err.log"
    owner = None
    native_stop = {"ok": True, "stopped_pids": []}
    installed = {"ok": True, "skipped": live_mode, "reason": "live-config-already-installed" if live_mode else None}
    if not live_mode:
        installed = install_wsl_shadow_config()
    script = (
        "export PATH=\"/home/joshu/.local/bin:/home/joshu/.npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"; "
        f"cd /home/joshu && exec /home/joshu/.npm-global/bin/openclaw gateway run --port {port}{' --auth none' if not live_mode else ''}"
    )
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    service = _wsl_gateway_service_available()
    if service.get("ok"):
        status_stdout = str((service.get("status") or {}).get("stdout") or "")
        if "Runtime: running" in status_stdout:
            start = {
                "ok": True,
                "exit_code": 0,
                "command": ["openclaw", "gateway", "start"],
                "stdout": "service already running; start skipped",
                "stderr": "",
                "service_mode": True,
                "idempotent": True,
            }
        else:
            start = _run_wsl_openclaw(["gateway", "start"], timeout_seconds=60)
            start["service_mode"] = True
    else:
        stdout_handle = out_log.open("w", encoding="utf-8")
        stderr_handle = err_log.open("w", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", script],
                cwd=repo_root(),
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=creationflags,
            )
            start = {
                "ok": True,
                "exit_code": None,
                "pid": proc.pid,
                "command": ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", script],
                "stdout": "",
                "stderr": "",
                "service_mode": False,
            }
        except OSError as exc:
            start = {
                "ok": False,
                "exit_code": 127,
                "pid": None,
                "command": ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", script],
                "stdout": "",
                "stderr": str(exc),
                "service_mode": False,
            }
        finally:
            stdout_handle.close()
            stderr_handle.close()
    deadline = time.time() + max(wait_seconds, 1)
    probe: dict[str, Any] = {}
    while time.time() < deadline:
        probe = probe_openclaw_gateway(port=port, runtime="wsl-shadow", timeout_seconds=3.0)
        if probe.get("ok"):
            break
        time.sleep(1.0)
    wsl_env = wsl_environment_status()
    result = {
        "ok": bool(installed.get("ok") and start.get("ok") and probe.get("ok") and wsl_env.get("ok")),
        "state": "WSL_GATEWAY_READY" if installed.get("ok") and start.get("ok") and probe.get("ok") and wsl_env.get("ok") else "WSL_GATEWAY_START_FAILED",
        "started_at": now_iso(),
        "runtime_state": runtime_owner.get("runtime_state"),
        "live_mode": live_mode,
        "telegram_owner": owner,
        "native_stop_after_owner_flip": {
            "ok": native_stop.get("ok"),
            "stopped_pids": native_stop.get("stopped_pids"),
        },
        "installed_config": installed,
        "service": service,
        "start": start,
        "wsl_environment": {
            "ok": wsl_env.get("ok"),
            "repo_visible": wsl_env.get("repo_visible"),
            "vault_visible": wsl_env.get("vault_visible"),
            "openclaw_bin": wsl_env.get("openclaw_bin"),
            "qmd_bin": wsl_env.get("qmd_bin"),
            "stderr": (wsl_env.get("raw") or {}).get("stderr"),
        },
        "probe": {
            "ok": probe.get("ok"),
            "reason": probe.get("reason"),
            "port": probe.get("port"),
        },
        "logs": {
            "windows_stdout": str(out_log),
            "windows_stderr": str(err_log),
            "wsl_stdout": "~/.openclaw/logs/otto-wsl-gateway.out.log",
            "wsl_stderr": "~/.openclaw/logs/otto-wsl-gateway.err.log",
        },
    }
    write_json(state_root() / "openclaw" / "wsl_gateway_start_last.json", result)
    return result


def stop_wsl_gateway(*, port: int = WSL_GATEWAY_PORT) -> dict[str, Any]:
    service = _wsl_gateway_service_available()
    service_stop = _run_wsl_openclaw(["gateway", "stop"], timeout_seconds=60) if service.get("ok") else None
    stop_script = f"""
{{ ss -ltnp 2>/dev/null | grep ':{int(port)} ' | sed -n 's/.*pid=\\([0-9][0-9]*\\).*/\\1/p'; pgrep -f '^openclaw-gateway$' 2>/dev/null || true; }} | sort -u > /tmp/otto-wsl-gateway-{int(port)}.pids
cat /tmp/otto-wsl-gateway-{int(port)}.pids
if [ -s /tmp/otto-wsl-gateway-{int(port)}.pids ]; then
  xargs -r kill -TERM < /tmp/otto-wsl-gateway-{int(port)}.pids 2>/dev/null || true
  sleep 1
  xargs -r kill -KILL < /tmp/otto-wsl-gateway-{int(port)}.pids 2>/dev/null || true
fi
sleep 1
"""
    stop = _run(["wsl.exe", "-d", WSL_DISTRO, "--", "bash", "-lc", stop_script], timeout_seconds=20)
    time.sleep(1.0)
    probe = probe_openclaw_gateway(port=port, runtime="wsl-shadow", timeout_seconds=5.0)
    stop_ok = bool(stop.get("ok") or (service_stop or {}).get("ok"))
    result = {
        "ok": bool(stop_ok and not probe.get("ok")),
        "state": "WSL_GATEWAY_STOPPED" if stop_ok and not probe.get("ok") else "WSL_GATEWAY_STILL_REACHABLE",
        "stopped_at": now_iso(),
        "service": service,
        "service_stop": service_stop,
        "stop": stop,
        "stopped_pids": [int(item) for item in str(stop.get("stdout") or "").splitlines() if item.strip().isdigit()],
        "probe": {"ok": probe.get("ok"), "reason": probe.get("reason"), "port": probe.get("port")},
    }
    write_json(state_root() / "openclaw" / "wsl_gateway_stop_last.json", result)
    return result


def restart_wsl_gateway(*, port: int = WSL_GATEWAY_PORT) -> dict[str, Any]:
    service = _wsl_gateway_service_available()
    if service.get("ok"):
        restart = _run_wsl_openclaw(["gateway", "restart"], timeout_seconds=90)
        deadline = time.time() + 90
        probe: dict[str, Any] = {}
        while time.time() < deadline:
            probe = probe_openclaw_gateway(port=port, runtime="wsl-live", timeout_seconds=15.0)
            if probe.get("ok"):
                break
            time.sleep(2.0)
        stopped = {"ok": bool(restart.get("ok")), "state": "WSL_GATEWAY_SERVICE_RESTART_REQUESTED", "service": service, "restart": restart}
        wsl_env = wsl_environment_status()
        started = {
            "ok": bool(restart.get("ok") and probe.get("ok") and wsl_env.get("ok")),
            "state": "WSL_GATEWAY_READY" if restart.get("ok") and probe.get("ok") and wsl_env.get("ok") else "WSL_GATEWAY_START_FAILED",
            "service_mode": True,
            "start": restart,
            "probe": {"ok": probe.get("ok"), "reason": probe.get("reason"), "port": probe.get("port")},
            "wsl_environment": {
                "ok": wsl_env.get("ok"),
                "openclaw_bin": wsl_env.get("openclaw_bin"),
                "qmd_bin": wsl_env.get("qmd_bin"),
            },
        }
    else:
        stopped = stop_wsl_gateway(port=port)
        started = start_wsl_gateway(port=port)
    return {
        "ok": bool(started.get("ok")),
        "state": "WSL_GATEWAY_RESTARTED" if started.get("ok") else "WSL_GATEWAY_RESTART_FAILED",
        "stopped": stopped,
        "started": started,
    }


def fallback_to_native() -> dict[str, Any]:
    """Return to the native gateway when WSL shadow is unhealthy.

    This intentionally does not enable WSL Telegram. Native remains the live owner.
    """
    runtime_owner = build_runtime_owner()
    decision = decide_gateway_owner()
    if decision.get("active") == "wsl":
        result = {
            "ok": False,
            "state": "NATIVE_FALLBACK_BLOCKED",
            "reason": "wsl-active",
            "created_at": now_iso(),
            "runtime_state_before_fallback": runtime_owner.get("runtime_state"),
            "gateway_decision": decision,
        }
        write_json(state_root() / "openclaw" / "native_fallback_last.json", result)
        return result
    wsl_probe = probe_openclaw_gateway(
        port=WSL_GATEWAY_PORT,
        runtime="wsl-live" if runtime_owner.get("runtime_state") == STATE_WSL_LIVE else "wsl-shadow",
        timeout_seconds=3.0,
    )
    rollback = rollback_wsl_live(gateway_port=WSL_GATEWAY_PORT, write=True) if runtime_owner.get("runtime_state") == STATE_WSL_LIVE else None
    owner = set_telegram_owner("windows") if runtime_owner.get("runtime_state") != STATE_WSL_LIVE else rollback.get("owner") if rollback else None
    if runtime_owner.get("runtime_state") != STATE_WSL_LIVE:
        install_wsl_shadow_config()
    native_restart = None
    native_probe = None
    if decision.get("active") in {"native", "unknown"} and not wsl_probe.get("ok"):
        native_restart = restart_openclaw_gateway(wait_seconds=30)
        native_probe = probe_openclaw_gateway(port=NATIVE_GATEWAY_PORT, runtime="windows-live", timeout_seconds=5.0)
    result = {
        "ok": bool((native_restart or {}).get("ok") or (native_probe or {}).get("ok") or wsl_probe.get("ok")),
        "state": "NATIVE_GATEWAY_ACTIVE"
        if (native_restart or {}).get("ok") or (native_probe or {}).get("ok")
        else ("WSL_GATEWAY_ACTIVE" if wsl_probe.get("ok") else "NATIVE_GATEWAY_UNHEALTHY"),
        "created_at": now_iso(),
        "runtime_state_before_fallback": runtime_owner.get("runtime_state"),
        "gateway_decision": decision,
        "rollback": rollback,
        "telegram_owner": owner,
        "wsl_probe": {"ok": wsl_probe.get("ok"), "reason": wsl_probe.get("reason"), "port": wsl_probe.get("port")},
        "native_restart": native_restart,
        "native_probe": {"ok": native_probe.get("ok"), "reason": native_probe.get("reason"), "port": native_probe.get("port")} if native_probe else None,
        "telegram_owner": "windows_openclaw",
    }
    write_json(state_root() / "openclaw" / "native_fallback_last.json", result)
    return result


def operator_doctor() -> dict[str, Any]:
    sync = sync_openclaw_config()
    status = operator_status()
    return {
        "ok": bool(status.get("ok")),
        "state": "OO_OPERATOR_DOCTOR_GREEN" if status.get("ok") else "OO_OPERATOR_DOCTOR_NEEDS_REPAIR",
        "checked_at": now_iso(),
        "sync": {
            "config_drift_free": sync.get("config_drift_free"),
            "sync_performed": sync.get("sync_performed"),
            "qmd_index_ok": (sync.get("qmd_index") or {}).get("ok"),
        },
        "status": status,
    }


def operator_update() -> dict[str, Any]:
    tool_manifest = _run([sys.executable, "-m", "otto.cli", "openclaw-tool-manifest"], timeout_seconds=60)
    context_pack = _run([sys.executable, "-m", "otto.cli", "openclaw-context-pack"], timeout_seconds=60)
    qmd_manifest = _run([sys.executable, "-m", "otto.cli", "qmd-manifest", "--write"], timeout_seconds=60)
    sync = sync_openclaw_config()
    status = operator_status()
    return {
        "ok": bool(tool_manifest["ok"] and context_pack["ok"] and qmd_manifest["ok"] and status.get("ok")),
        "state": "OO_OPERATOR_UPDATED" if status.get("ok") else "OO_OPERATOR_UPDATE_NEEDS_REPAIR",
        "updated_at": now_iso(),
        "tool_manifest": tool_manifest,
        "context_pack": context_pack,
        "qmd_manifest": qmd_manifest,
        "sync": {
            "config_drift_free": sync.get("config_drift_free"),
            "sync_performed": sync.get("sync_performed"),
        },
        "status": status,
    }
