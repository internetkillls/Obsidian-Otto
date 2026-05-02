from __future__ import annotations

import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any


def _encode(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def build_advanced_uri(
    *,
    vault_name: str,
    command_name: str,
    filepath: str | None = None,
    line: int | None = None,
) -> str:
    params: list[str] = [f"vault={_encode(vault_name)}", f"commandname={_encode(command_name)}"]
    if filepath:
        params.append(f"filepath={_encode(filepath)}")
    if line is not None:
        params.append(f"line={int(line)}")
    return f"obsidian://adv-uri?{'&'.join(params)}"


def open_uri(uri: str) -> dict[str, Any]:
    if not uri.strip():
        return {"ok": False, "error": "empty-uri"}

    try:
        if os.name == "nt" and hasattr(os, "startfile"):
            os.startfile(uri)  # type: ignore[attr-defined]
            return {"ok": True, "method": "os.startfile", "uri": uri}

        result = subprocess.run(["xdg-open", uri], check=False)
        return {
            "ok": result.returncode == 0,
            "method": "xdg-open",
            "uri": uri,
            "exit_code": result.returncode,
        }
    except Exception as exc:  # pragma: no cover - defensive transport fallback
        return {"ok": False, "method": "exception", "uri": uri, "error": str(exc)}


def build_file_target(path: Path, vault_root: Path | None) -> str:
    if vault_root is None:
        return str(path).replace("\\", "/")
    try:
        return str(path.relative_to(vault_root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
