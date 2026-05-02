from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import state_root
from ..state import now_iso, read_json, write_json
from .runtime_owner import build_runtime_owner, build_single_owner_lock


def rollback_drill_last_path() -> Path:
    return state_root() / "ops" / "rollback_drill_last.json"


def run_rollback_drill(*, dry_run: bool = True, write: bool = True) -> dict[str, Any]:
    owner = build_runtime_owner()
    lock = build_single_owner_lock()
    rollback_plan_path = state_root() / "runtime" / "rollback_plan.json"
    rollback_plan = read_json(rollback_plan_path, default={}) or {}

    last_good_candidates = [
        Path("C:/Users/joshu/.openclaw/openclaw.json.last-good"),
        Path.home() / ".openclaw" / "openclaw.json.last-good",
    ]
    last_good_exists = any(path.exists() for path in last_good_candidates)

    steps = [
        {
            "step": "stop_wsl_gateway",
            "command": "/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/openclaw-wsl.sh gateway stop",
            "dry_run": dry_run,
        },
        {
            "step": "disable_ubuntu_telegram_owner",
            "command": "/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-cli-wsl.sh wsl-live-rollback --write",
            "dry_run": dry_run,
        },
        {
            "step": "restore_windows_last_good_config",
            "command": "Copy C:/Users/joshu/.openclaw/openclaw.json.last-good -> C:/Users/joshu/.openclaw/openclaw.json",
            "dry_run": dry_run,
        },
        {
            "step": "reassert_single_owner_lock",
            "command": "/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-cli-wsl.sh single-owner-lock",
            "dry_run": dry_run,
        },
    ]

    checks = {
        "rollback_plan_exists": bool(rollback_plan),
        "last_good_config_exists": last_good_exists,
        "single_owner_lock_available": bool(lock.get("ok", False)),
        "owner_snapshot_available": bool(owner),
    }

    ok = all(checks.values())
    result = {
        "ok": ok,
        "checked_at": now_iso(),
        "state": "OPS3_ROLLBACK_DRILL_READY" if ok else "OPS3_BLOCKED",
        "dry_run": dry_run,
        "state_mutation_performed": False,
        "checks": checks,
        "steps": steps,
        "owner": owner,
        "single_owner_lock": lock,
        "rollback_plan": rollback_plan,
    }
    if write:
        write_json(rollback_drill_last_path(), result)
    return result
