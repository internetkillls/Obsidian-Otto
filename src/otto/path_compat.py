from __future__ import annotations

import platform
import re
from pathlib import Path

_WINDOWS_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def is_wsl() -> bool:
    if platform.system().lower() != "linux":
        return False
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
    except OSError:
        release = platform.release().lower()
    return "microsoft" in release or "wsl" in release


def windows_path_to_wsl(value: str) -> str:
    match = _WINDOWS_DRIVE_RE.match(value)
    if not match:
        return value
    drive = match.group(1).lower()
    rest = match.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def normalize_platform_path(value: str) -> str:
    if is_wsl():
        return windows_path_to_wsl(value)
    return value
