from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import os
from pathlib import Path
from typing import Any

from .config import load_paths, repo_root
from .docker_utils import docker_compose_status, docker_probe_diagnostics
from .openclaw_support import build_qmd_index_health
from .path_compat import is_wsl

LINUX_OPENCLAW_PATH = (
    "~/.local/bin",
    "~/.npm-global/bin",
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
)
EXPECTED_WSL_USER = "joshu"


def _run_probe(command: list[str], *, timeout: int = 10) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "status": "command-not-found",
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "status": "timeout",
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "command timed out",
        }
    except OSError as exc:
        return {
            "ok": False,
            "status": "probe-failed",
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "ok": completed.returncode == 0,
        "status": "ok" if completed.returncode == 0 else "probe-failed",
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _qmd_probe() -> dict[str, Any]:
    candidates: list[list[str]] = []
    if is_wsl():
        candidates.append(["/usr/bin/qmd"])
    detected = shutil.which("qmd")
    if detected:
        candidates.append([detected])
    bridge = repo_root() / "scripts" / "shell" / "qmd-wsl.js"
    if not is_wsl() and bridge.exists():
        node = shutil.which("node")
        candidates.append([node, str(bridge)] if node else [str(bridge)])

    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        key = tuple(candidate)
        if key in seen:
            continue
        seen.add(key)
        result = _run_probe([*candidate, "--version"], timeout=10)
        if result["ok"]:
            return {
                "available": True,
                "status": "ok",
                "command": candidate,
                "version": result["stdout"] or result["stderr"],
                "probe": result,
            }
    return {
        "available": False,
        "status": "qmd-not-found",
        "command": None,
        "version": None,
        "probe": None,
    }


def classify_openclaw_origin(path: str | None) -> str:
    if not path:
        return "missing"
    normalized = path.replace("\\", "/")
    lowered = normalized.lower()
    if lowered.startswith("/mnt/") or "windowsapps" in lowered or lowered.endswith(".exe"):
        return "windows-path"
    if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] == "/":
        return "windows-path"
    if normalized.startswith("/"):
        return "native-linux"
    return "unknown"


def _linux_openclaw_search_path() -> str:
    entries = [os.path.expanduser(item) for item in LINUX_OPENCLAW_PATH]
    return os.pathsep.join(entries)


def _openclaw_probe() -> dict[str, Any]:
    ambient = shutil.which("openclaw")
    quarantined = shutil.which("openclaw", path=_linux_openclaw_search_path()) if is_wsl() else None
    command = quarantined or ambient
    origin = classify_openclaw_origin(command)

    if not command:
        return {
            "available": False,
            "native": False,
            "origin": "missing",
            "status": "openclaw-not-found",
            "command": None,
            "version": None,
            "ambient_command": ambient,
            "probe": None,
        }

    native = origin == "native-linux"
    if is_wsl() and not native:
        return {
            "available": True,
            "native": False,
            "origin": origin,
            "status": "windows-openclaw-from-wsl-path" if origin == "windows-path" else "openclaw-not-native",
            "command": command,
            "version": None,
            "ambient_command": ambient,
            "probe": None,
        }

    result = _run_probe([command, "--version"], timeout=10)
    return {
        "available": True,
        "native": native,
        "origin": origin,
        "status": "ok" if result["ok"] else result["status"],
        "command": command,
        "version": result["stdout"] or result["stderr"] or None,
        "ambient_command": ambient,
        "probe": result,
    }


def _identity_probe() -> dict[str, Any]:
    if not is_wsl():
        return {
            "ok": True,
            "required": False,
            "expected_user": EXPECTED_WSL_USER,
            "user": None,
            "uid": None,
            "home": str(Path.home()),
            "expected_home": None,
            "is_root": False,
        }
    try:
        import pwd

        uid = os.getuid()
        current = pwd.getpwuid(uid)
        expected = pwd.getpwnam(EXPECTED_WSL_USER)
        user = current.pw_name
        expected_home = expected.pw_dir
        home = str(Path.home())
        ok = user == EXPECTED_WSL_USER and uid != 0 and home == expected_home
        return {
            "ok": ok,
            "required": True,
            "expected_user": EXPECTED_WSL_USER,
            "user": user,
            "uid": uid,
            "home": home,
            "expected_home": expected_home,
            "is_root": uid == 0,
        }
    except KeyError:
        return {
            "ok": False,
            "required": True,
            "expected_user": EXPECTED_WSL_USER,
            "user": None,
            "uid": os.getuid() if hasattr(os, "getuid") else None,
            "home": str(Path.home()),
            "expected_home": f"/home/{EXPECTED_WSL_USER}",
            "is_root": (os.getuid() == 0) if hasattr(os, "getuid") else False,
            "status": "expected-user-missing",
        }


def build_wsl_health() -> dict[str, Any]:
    paths = load_paths()
    identity = _identity_probe()
    qmd = _qmd_probe()
    openclaw = _openclaw_probe()
    qmd_index = build_qmd_index_health()
    docker = docker_probe_diagnostics()
    compose = docker_compose_status(probe=True)

    repo_readable = paths.repo_root.exists() and paths.repo_root.is_dir()
    vault_readable = bool(paths.vault_path and paths.vault_path.exists() and paths.vault_path.is_dir())
    docker_ok = bool(docker.get("daemon_running"))
    openclaw_ok = bool(openclaw.get("native")) if is_wsl() else True
    identity_ok = bool(identity.get("ok"))
    compose_visible = compose.get("status") == "ok"
    recommendations: list[str] = []
    if is_wsl() and not identity_ok:
        recommendations.append("Run Ubuntu as canonical user joshu with HOME=/home/joshu; do not run WSL shadow commands as root.")
    if not is_wsl():
        recommendations.append("Run this command from Ubuntu WSL for the canonical WSL health signal.")
    if not qmd.get("available"):
        recommendations.append("Install QMD inside Ubuntu: npm install -g @tobilu/qmd.")
    if is_wsl() and not openclaw.get("available"):
        recommendations.append("Install native OpenClaw inside Ubuntu before running shadow OpenClaw probes.")
    elif is_wsl() and not openclaw_ok:
        recommendations.append("Refusing Windows OpenClaw from WSL PATH; install native OpenClaw or fix PATH quarantine.")
    if not docker_ok:
        recommendations.append("Enable Docker Desktop WSL integration for the Ubuntu distro, then rerun docker-probe.")
    if is_wsl() and (not openclaw_ok or not docker_ok):
        recommendations.append("Treat WSL qmd-reindex as blocked until native OpenClaw and Docker are both green.")
    if not vault_readable:
        recommendations.append("Verify the vault is visible at /mnt/c/Users/joshu/Josh Obsidian from WSL.")

    return {
        "ok": bool(identity_ok and repo_readable and vault_readable and qmd.get("available") and docker_ok and openclaw_ok),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "is_wsl": is_wsl(),
        },
        "identity": identity,
        "paths": {
            "repo_root": str(paths.repo_root),
            "repo_readable": repo_readable,
            "vault_path": str(paths.vault_path) if paths.vault_path else None,
            "vault_readable": vault_readable,
        },
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
        },
        "qmd": qmd,
        "openclaw": openclaw,
        "qmd_index": qmd_index,
        "docker": docker,
        "compose": compose,
        "compose_visible": compose_visible,
        "recommendations": recommendations,
    }
