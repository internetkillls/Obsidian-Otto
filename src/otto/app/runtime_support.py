from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import repo_root


@dataclass
class RuntimeSnapshot:
    status: str
    pid: int | None


def runtime_pid_file(root: Path | None = None) -> Path:
    base = root or repo_root()
    return base / "state" / "pids" / "runtime.pid"


def _windows_process_running(pid: int) -> bool:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ProcessName",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    output = result.stdout.lower().strip()
    if result.returncode != 0 or not output:
        return False
    return output in {"python", "pythonw", "python.exe", "pythonw.exe"}


def _generic_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def classify_runtime(
    pid_path: Path | None = None,
    *,
    process_checker: Callable[[int], bool] | None = None,
) -> RuntimeSnapshot:
    path = pid_path or runtime_pid_file()
    if not path.exists():
        return RuntimeSnapshot(status="STOPPED", pid=None)

    raw_pid = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw_pid:
        return RuntimeSnapshot(status="STALE", pid=None)

    try:
        pid = int(raw_pid)
    except ValueError:
        return RuntimeSnapshot(status="STALE", pid=None)

    checker = process_checker
    if checker is None:
        checker = _windows_process_running if os.name == "nt" else _generic_process_running
    return RuntimeSnapshot(status="RUNNING" if checker(pid) else "STALE", pid=pid)


def clear_stale_runtime_pid(pid_path: Path | None = None) -> None:
    path = pid_path or runtime_pid_file()
    if path.exists():
        path.unlink()
