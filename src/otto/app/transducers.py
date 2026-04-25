from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any


def result_envelope(
    *,
    action: str,
    ok: bool,
    returncode: int = 0,
    duration_ms: int = 0,
    stdout: str = "",
    stderr: str = "",
    parsed: Any | None = None,
    warnings: list[str] | None = None,
    failure_class: str | None = None,
    next_safe_action: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "action": action,
        "returncode": returncode,
        "duration_ms": duration_ms,
        "stdout": stdout,
        "stderr": stderr,
        "parsed": parsed if parsed is not None else {},
        "warnings": warnings or [],
        "failure_class": failure_class,
        "next_safe_action": next_safe_action,
    }


def run_command(
    *,
    action: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return result_envelope(
            action=action,
            ok=False,
            returncode=127,
            duration_ms=int((time.time() - started) * 1000),
            stderr=str(exc),
            failure_class="command_not_found",
            next_safe_action="Verify the command exists and the virtual environment is ready.",
        )
    except subprocess.TimeoutExpired as exc:
        return result_envelope(
            action=action,
            ok=False,
            returncode=124,
            duration_ms=int((time.time() - started) * 1000),
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"{action} timed out",
            failure_class="timeout",
            next_safe_action="Retry with a narrower scope or inspect the current process state.",
        )

    duration_ms = int((time.time() - started) * 1000)
    return result_envelope(
        action=action,
        ok=proc.returncode == 0,
        returncode=proc.returncode,
        duration_ms=duration_ms,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        failure_class=None if proc.returncode == 0 else "nonzero_exit",
    )
