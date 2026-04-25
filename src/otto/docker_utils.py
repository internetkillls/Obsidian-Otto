from __future__ import annotations

import subprocess
from pathlib import Path
import shutil
from typing import Any

from .config import load_docker_config, repo_root


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


def docker_probe_diagnostics() -> dict[str, Any]:
    info = run_docker_command(["info"], timeout=5)
    containers = run_docker_command(["ps", "--format", "{{.Names}}\t{{.Status}}"], timeout=5)
    return {
        "docker_available": docker_available(),
        "daemon_running": bool(info.get("ok")),
        "info_probe": info,
        "container_probe": containers,
    }
