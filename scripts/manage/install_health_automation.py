from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTH_TASK = "Obsidian-Otto Health Repair"
STARTUP_TASK = "Obsidian-Otto Fresh Startup"
STARTUP_RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"


def _task_action(batch_name: str, *args: str) -> str:
    batch = REPO_ROOT / batch_name
    extra = " ".join(args)
    suffix = f" {extra}" if extra else ""
    return f'cmd.exe /c ""{batch}"{suffix}"'


def _run(command: Sequence[str]) -> dict[str, object]:
    result = subprocess.run(list(command), cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return {
        "command": list(command),
        "exit_code": result.returncode,
        "ok": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def install_tasks() -> list[dict[str, object]]:
    health = _run(
        [
            "schtasks",
            "/Create",
            "/TN",
            HEALTH_TASK,
            "/SC",
            "HOURLY",
            "/MO",
            "3",
            "/TR",
            _task_action("health-repair.bat", "--scheduled"),
            "/F",
        ]
    )
    startup = _run(
        [
            "schtasks",
            "/Create",
            "/TN",
            STARTUP_TASK,
            "/SC",
            "ONLOGON",
            "/TR",
            _task_action("fresh-everything.bat", "--scheduled"),
            "/F",
        ]
    )
    if not startup["ok"]:
        fallback = _run(
            [
                "reg",
                "add",
                STARTUP_RUN_KEY,
                "/v",
                STARTUP_TASK,
                "/t",
                "REG_SZ",
                "/d",
                _task_action("fresh-everything.bat", "--scheduled"),
                "/f",
            ]
        )
        startup["fallback"] = "hkcu-run"
        startup["fallback_result"] = fallback
        startup["ok"] = bool(fallback["ok"])
    return [health, startup]


def _ignore_missing(result: dict[str, object]) -> dict[str, object]:
    stderr = str(result.get("stderr") or "")
    stdout = str(result.get("stdout") or "")
    if result["ok"] or "cannot find" in stderr.lower() or "unable to find" in stdout.lower():
        result["ok"] = True
    return result


def uninstall_tasks() -> list[dict[str, object]]:
    return [
        _ignore_missing(_run(["schtasks", "/Delete", "/TN", HEALTH_TASK, "/F"])),
        _ignore_missing(_run(["schtasks", "/Delete", "/TN", STARTUP_TASK, "/F"])),
        _ignore_missing(_run(
            [
                "reg",
                "delete",
                STARTUP_RUN_KEY,
                "/v",
                STARTUP_TASK,
                "/f",
            ]
        )),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install or remove Obsidian-Otto scheduled health automation.")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    results = uninstall_tasks() if args.uninstall else install_tasks()
    for item in results:
        print(item)
    return 0 if all(item.get("ok") for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
