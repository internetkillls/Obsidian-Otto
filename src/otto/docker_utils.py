from __future__ import annotations

import subprocess
from pathlib import Path
import shutil
from datetime import datetime, timezone
from typing import Any

from .config import load_docker_config, repo_root

EPHEMERAL_MCP_NAME_MARKER = "obsidian-mcp-run-"
DEFAULT_EPHEMERAL_MCP_TTL_SECONDS = 300


def docker_available() -> bool:
    return shutil.which("docker") is not None


def classify_docker_probe_error(text: str | None) -> str:
    message = (text or "").strip().lower()
    if not message:
        return "probe-failed"
    if "access is denied" in message:
        return "access-denied"
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if "cannot find" in message or "not recognized" in message:
        return "command-not-found"
    if "could not be found in this wsl 2 distro" in message:
        return "command-not-found"
    return "probe-failed"


def _powershell_executable() -> str | None:
    candidates = [
        Path(r"C:\Program Files\PowerShell\7\pwsh.exe"),
        shutil.which("pwsh"),
        shutil.which("powershell"),
    ]
    for candidate in candidates:
        if isinstance(candidate, Path):
            if candidate.exists():
                return str(candidate)
            continue
        if candidate:
            return candidate
    return None


def _docker_powershell_command(args: list[str]) -> list[str] | None:
    shell = _powershell_executable()
    if not shell:
        return None
    raw_args = subprocess.list2cmdline(args)
    return [shell, "-NoProfile", "-Command", f"docker --% {raw_args}"]


def run_docker_command(
    args: list[str],
    *,
    timeout: int = 5,
    allow_powershell_fallback: bool = True,
) -> dict[str, Any]:
    if not docker_available():
        return {
            "ok": False,
            "status": "docker-not-found",
            "transport": "none",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "fallback_used": False,
            "direct_status": None,
        }

    try:
        direct = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "status": "docker-not-found",
            "transport": "none",
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "fallback_used": False,
            "direct_status": "docker-not-found",
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "status": "timeout",
            "transport": "direct",
            "returncode": None,
            "stdout": "",
            "stderr": "docker command timed out",
            "fallback_used": False,
            "direct_status": "timeout",
        }

    direct_error = (direct.stderr or direct.stdout or "").strip()
    direct_status = "ok" if direct.returncode == 0 else classify_docker_probe_error(direct_error)
    if direct.returncode == 0:
        return {
            "ok": True,
            "status": "ok",
            "transport": "direct",
            "returncode": direct.returncode,
            "stdout": direct.stdout,
            "stderr": direct.stderr,
            "fallback_used": False,
            "direct_status": "ok",
        }

    should_fallback = allow_powershell_fallback and direct_status in {"access-denied", "probe-failed"}
    powershell_cmd = _docker_powershell_command(args) if should_fallback else None
    if powershell_cmd:
        try:
            fallback = subprocess.run(
                powershell_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "status": "timeout",
                "transport": "powershell-fallback",
                "returncode": None,
                "stdout": "",
                "stderr": "powershell docker probe timed out",
                "fallback_used": True,
                "direct_status": direct_status,
            }
        fallback_error = (fallback.stderr or fallback.stdout or "").strip()
        fallback_status = "ok" if fallback.returncode == 0 else classify_docker_probe_error(fallback_error)
        return {
            "ok": fallback.returncode == 0,
            "status": "ok" if fallback.returncode == 0 else fallback_status,
            "transport": "powershell-fallback",
            "returncode": fallback.returncode,
            "stdout": fallback.stdout,
            "stderr": fallback.stderr,
            "fallback_used": True,
            "direct_status": direct_status,
        }

    return {
        "ok": False,
        "status": direct_status,
        "transport": "direct",
        "returncode": direct.returncode,
        "stdout": direct.stdout,
        "stderr": direct.stderr,
        "fallback_used": False,
        "direct_status": direct_status,
    }


def docker_daemon_running() -> bool:
    return bool(run_docker_command(["info"], timeout=5).get("ok"))


def docker_compose_status(*, probe: bool = True) -> dict[str, Any]:
    if not docker_available():
        return {"available": False, "status": "docker-not-found", "services": []}
    if not probe:
        return {"available": True, "status": "not-probed", "services": []}
    cfg = load_docker_config()
    compose_file = repo_root() / str(cfg.get("compose_file", "docker-compose.yml"))
    if not compose_file.exists():
        return {"available": True, "status": "compose-file-missing", "services": []}

    # Try docker compose v2 first, then docker-compose v1 as fallback
    probe_result = run_docker_command(["compose", "-f", str(compose_file), "ps", "--format", "json"], timeout=5)
    if not probe_result.get("ok"):
        status = probe_result.get("status") or "probe-failed"
        return {
            "available": True,
            "status": status,
            "services": [],
            "error": (probe_result.get("stderr") or probe_result.get("stdout") or "").strip() or None,
            "transport": probe_result.get("transport"),
            "fallback_used": probe_result.get("fallback_used", False),
            "direct_status": probe_result.get("direct_status"),
        }
    services: list[dict[str, Any]] = []
    if probe_result.get("stdout", "").strip():
        for line in str(probe_result.get("stdout") or "").strip().splitlines():
            try:
                import json
                services.append(json.loads(line))
            except Exception:
                services.append({"raw": line})
    return {
        "available": True,
        "status": "ok",
        "services": services,
        "transport": probe_result.get("transport"),
        "fallback_used": probe_result.get("fallback_used", False),
        "direct_status": probe_result.get("direct_status"),
    }


def _parse_container_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        container_id, name = parts[0].strip(), parts[1].strip()
        if container_id and name:
            rows.append({"id": container_id, "name": name})
    return rows


def _parse_docker_timestamp(raw: str | None) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _inspect_ephemeral_mcp_containers(ids: list[str], *, timeout: int = 10) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    result = run_docker_command(["inspect", *ids], timeout=timeout)
    if not result.get("ok"):
        return {}
    try:
        import json

        payload = json.loads(str(result.get("stdout") or "[]"))
    except Exception:
        return {}

    details: dict[str, dict[str, Any]] = {}
    now = datetime.now(timezone.utc)
    for item in payload:
        if not isinstance(item, dict):
            continue
        container_id = str(item.get("Id") or "")
        state = item.get("State") or {}
        created_at = _parse_docker_timestamp(item.get("Created"))
        age_seconds: int | None = None
        if created_at is not None:
            try:
                age_seconds = max(int((now - created_at).total_seconds()), 0)
            except Exception:
                age_seconds = None
        details[container_id] = {
            "running": bool(state.get("Running")),
            "status": state.get("Status"),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
            "created_at": item.get("Created"),
            "age_seconds": age_seconds,
        }
    return details


def list_ephemeral_mcp_containers(*, include_details: bool = False) -> dict[str, Any]:
    result = run_docker_command(["ps", "-a", "--format", "{{.ID}}\t{{.Names}}"], timeout=10)
    if not result.get("ok"):
        return {
            "ok": False,
            "status": result.get("status") or "probe-failed",
            "containers": [],
            "error": (result.get("stderr") or result.get("stdout") or "").strip() or None,
            "transport": result.get("transport"),
        }
    containers = [
        row
        for row in _parse_container_rows(str(result.get("stdout") or ""))
        if EPHEMERAL_MCP_NAME_MARKER in row["name"]
    ]
    if include_details and containers:
        inspected = _inspect_ephemeral_mcp_containers([str(item["id"]) for item in containers], timeout=10)
        for item in containers:
            item.update(inspected.get(str(item["id"]), {}))
    return {
        "ok": True,
        "status": "ok",
        "containers": containers,
        "count": len(containers),
        "transport": result.get("transport"),
    }


def cleanup_ephemeral_mcp_containers(
    *,
    remove_running: bool = True,
    running_ttl_seconds: int | None = None,
) -> dict[str, Any]:
    inspect_needed = (not remove_running) or running_ttl_seconds is not None
    listed = list_ephemeral_mcp_containers(include_details=inspect_needed)
    if not listed.get("ok"):
        return {**listed, "removed": []}
    containers = list(listed.get("containers") or [])
    skipped_names: list[str] = []
    if inspect_needed:
        eligible: list[dict[str, Any]] = []
        for item in containers:
            is_running = bool(item.get("running"))
            age_seconds = item.get("age_seconds")
            should_remove = not is_running
            if is_running and remove_running:
                if running_ttl_seconds is None:
                    should_remove = True
                elif age_seconds is not None and age_seconds >= running_ttl_seconds:
                    should_remove = True
            if should_remove:
                eligible.append(item)
            else:
                skipped_names.append(str(item.get("name") or ""))
        containers = eligible
    ids = [str(item["id"]) for item in containers if item.get("id")]
    if not ids:
        return {
            **listed,
            "removed": [],
            "skipped": skipped_names,
            "remove_status": "nothing-to-remove",
        }
    removed_names = [str(item["name"]) for item in containers]
    result = run_docker_command(["rm", "-f", *ids], timeout=30)
    return {
        "ok": bool(result.get("ok")),
        "status": "ok" if result.get("ok") else (result.get("status") or "remove-failed"),
        "containers": containers,
        "count": len(containers),
        "removed": removed_names if result.get("ok") else [],
        "skipped": skipped_names,
        "remove_stdout": str(result.get("stdout") or "").strip(),
        "remove_stderr": str(result.get("stderr") or "").strip(),
        "transport": result.get("transport"),
    }


def docker_probe_diagnostics() -> dict[str, Any]:
    info = run_docker_command(["info"], timeout=5)
    containers = run_docker_command(["ps", "--format", "{{.Names}}\t{{.Status}}"], timeout=5)
    stale_mcp = list_ephemeral_mcp_containers()
    return {
        "docker_available": docker_available(),
        "daemon_running": bool(info.get("ok")),
        "info_probe": info,
        "container_probe": containers,
        "ephemeral_mcp_containers": stale_mcp,
    }
