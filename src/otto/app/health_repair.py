from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from ..config import load_docker_config, load_paths
from ..db import init_pg_schema
from ..docker_utils import (
    DEFAULT_EPHEMERAL_MCP_TTL_SECONDS,
    cleanup_ephemeral_mcp_containers,
    docker_available,
    docker_daemon_running,
)
from ..infra import build_infra_result
from ..openclaw_support import probe_openclaw_gateway, restart_openclaw_gateway, sync_openclaw_config
from ..state import now_iso, write_json
from .runtime_support import classify_runtime, clear_stale_runtime_pid, runtime_pid_file


RUNTIME_SCRIPT = Path("scripts/manage/runtime_loop.py")


def _runtime_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src = str(root / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not existing else f"{src}{os.pathsep}{existing}"
    return env


def _compose_profile_args() -> list[str]:
    cfg = load_docker_config()
    services = set(cfg.get("services") or [])
    profiles: list[str] = []

    if "chromadb" in services:
        profiles.append("vector")
    if "otto-indexer" in services:
        profiles.append("worker")
    if "obsidian-mcp" in services:
        profiles.extend(list((cfg.get("mcp") or {}).get("profiles") or []))

    unique_profiles: list[str] = []
    for profile in profiles:
        if profile and profile not in unique_profiles:
            unique_profiles.append(profile)

    args: list[str] = []
    for profile in unique_profiles:
        args.extend(["--profile", profile])
    return args


def _run_command(root: Path, command: Sequence[str], *, timeout: int | None = None) -> dict[str, Any]:
    result = subprocess.run(list(command), cwd=root, check=False, timeout=timeout)
    return {"command": list(command), "exit_code": result.returncode}


def _ensure_docker_desktop(*, wait_seconds: int = 90) -> dict[str, Any]:
    if docker_daemon_running():
        return {"ok": True, "reason": "docker-daemon-running"}
    if os.name != "nt":
        return {"ok": False, "reason": "docker-daemon-not-running"}

    candidates = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Docker" / "Docker" / "Docker Desktop.exe",
        Path(os.environ.get("LocalAppData", "")) / "Docker" / "Docker Desktop.exe",
    ]
    executable = next((path for path in candidates if path.exists()), None)
    if executable is None:
        return {"ok": False, "reason": "docker-desktop-exe-missing", "checked": [str(path) for path in candidates]}

    start_result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Start-Process -FilePath '{executable}' -WindowStyle Hidden",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if start_result.returncode != 0:
        return {
            "ok": False,
            "reason": "docker-desktop-start-failed",
            "exit_code": start_result.returncode,
            "stderr": start_result.stderr.strip(),
        }

    deadline = time.time() + max(wait_seconds, 1)
    while time.time() < deadline:
        time.sleep(3)
        if docker_daemon_running():
            return {"ok": True, "reason": "docker-desktop-started", "executable": str(executable)}
    return {"ok": False, "reason": "docker-daemon-timeout", "executable": str(executable)}


def _ensure_runtime(root: Path, env: dict[str, str]) -> dict[str, Any]:
    pid_path = runtime_pid_file(root)
    snapshot = classify_runtime(pid_path)
    if snapshot.status == "RUNNING":
        return {"ok": True, "reason": "runtime-already-running", "pid": snapshot.pid}
    if snapshot.status == "STALE":
        clear_stale_runtime_pid(pid_path)

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [sys.executable, str(root / RUNTIME_SCRIPT)],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    confirmed = classify_runtime(pid_path)
    for _ in range(20):
        time.sleep(0.25)
        confirmed = classify_runtime(pid_path)
        if confirmed.status == "RUNNING":
            return {"ok": True, "reason": "runtime-started", "pid": confirmed.pid}
    return {"ok": False, "reason": "runtime-start-unconfirmed", "status": confirmed.status}


def _write_run_journal(root: Path, result: dict[str, Any]) -> None:
    paths = load_paths()
    state_root = getattr(paths, "state_root", root / "state")
    ts = now_iso()
    safe_ts = ts.replace(":", "").replace("-", "").replace("+", "_")
    journal_dir = state_root / "run_journal" / "health_repair"
    write_json(journal_dir / "latest.json", result)
    write_json(journal_dir / f"{safe_ts}.json", result)


def run_health_repair(
    *,
    root: Path,
    runtime_env: dict[str, str] | None = None,
    fresh: bool = False,
    scheduled: bool = False,
    ensure_runtime: bool = True,
) -> dict[str, Any]:
    env = runtime_env or _runtime_env(root)
    started_at = now_iso()
    steps: list[dict[str, Any]] = []
    errors: list[str] = []

    def add_step(name: str, data: dict[str, Any]) -> None:
        steps.append({"name": name, **data})

    docker_ready = False
    if not docker_available():
        add_step("docker", {"ok": False, "reason": "docker-cli-not-found"})
        errors.append("docker-cli-not-found")
    else:
        docker_start = _ensure_docker_desktop()
        add_step("docker", docker_start)
        docker_ready = bool(docker_start.get("ok"))
        if not docker_ready:
            errors.append(str(docker_start.get("reason") or "docker-not-ready"))

    if docker_ready:
        stale_cleanup = cleanup_ephemeral_mcp_containers(
            remove_running=True,
            running_ttl_seconds=DEFAULT_EPHEMERAL_MCP_TTL_SECONDS,
        )
        add_step("mcp-clean", stale_cleanup)
        if not stale_cleanup.get("ok", True):
            errors.append("mcp-clean-failed")

        compose_command = ["docker", "compose", "-f", "docker-compose.yml", *_compose_profile_args(), "up", "-d"]
        if fresh:
            compose_command.append("--force-recreate")
        compose_up = _run_command(root, compose_command)
        add_step("docker-compose-up", compose_up)
        if compose_up["exit_code"] != 0:
            errors.append("docker-compose-up-failed")

        infra_after_up = build_infra_result().to_dict()
        add_step("infra-after-compose", {"ok": True, "infra": infra_after_up})
        if not infra_after_up.get("postgres_reachable") and "postgres" in (infra_after_up.get("configured_services") or []):
            pg_up = _run_command(root, ["docker", "compose", "-f", "docker-compose.yml", "up", "-d", "postgres"])
            add_step("postgres-up", pg_up)
            pg_restart = _run_command(root, ["docker", "compose", "-f", "docker-compose.yml", "restart", "postgres"])
            add_step("postgres-restart", pg_restart)
            if pg_up["exit_code"] != 0 or pg_restart["exit_code"] != 0:
                errors.append("postgres-repair-failed")
            else:
                time.sleep(2)
                try:
                    init_pg_schema()
                    add_step("postgres-schema", {"ok": True, "reason": "schema-init-attempted"})
                except Exception as exc:
                    add_step("postgres-schema", {"ok": False, "reason": type(exc).__name__, "message": str(exc)})

    try:
        sync_result = sync_openclaw_config()
        add_step("openclaw-config-sync", {"ok": bool(sync_result.get("config_drift_free")), "result": sync_result})
    except Exception as exc:
        add_step("openclaw-config-sync", {"ok": False, "reason": type(exc).__name__, "message": str(exc)})

    gateway_probe = probe_openclaw_gateway(timeout_seconds=2.0)
    add_step("openclaw-gateway-probe", gateway_probe)
    if fresh or not gateway_probe.get("ok"):
        gateway_restart = restart_openclaw_gateway(wait_seconds=45)
        add_step("openclaw-gateway-restart", gateway_restart)
        if not gateway_restart.get("ok"):
            errors.append(str(gateway_restart.get("reason") or "openclaw-gateway-restart-failed"))

    if ensure_runtime:
        runtime_result = _ensure_runtime(root, env)
        add_step("runtime", runtime_result)
        if not runtime_result.get("ok"):
            errors.append(str(runtime_result.get("reason") or "runtime-start-failed"))

    final_infra = build_infra_result().to_dict()
    add_step("infra-final", {"ok": True, "infra": final_infra})
    if docker_ready and "postgres" in (final_infra.get("configured_services") or []) and not final_infra.get("postgres_reachable"):
        errors.append("postgres-still-unreachable")

    result = {
        "ok": not errors,
        "mode": "fresh" if fresh else "health",
        "scheduled": scheduled,
        "started_at": started_at,
        "finished_at": now_iso(),
        "steps": steps,
        "errors": errors,
    }
    _write_run_journal(root, result)
    return result
