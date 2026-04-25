from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app.status import build_status
from ..config import load_paths
from ..openclaw_support import sync_openclaw_config
from ..state import OttoState, read_json
from .runtime_support import clear_stale_runtime_pid, classify_runtime, runtime_pid_file
from .transducers import run_command


def _required_paths(root: Path) -> list[Path]:
    return [
        root / "tasks" / "active",
        root / "artifacts" / "summaries",
        root / "artifacts" / "reports",
        root / "state" / "handoff",
        root / "state" / "checkpoints",
        root / "state" / "run_journal",
    ]


def _intake(root: Path) -> dict[str, Any]:
    paths = load_paths()
    state = OttoState.load()
    runtime = classify_runtime(runtime_pid_file(root))
    handoff = read_json(state.handoff_latest, default={}) or {}
    checkpoint = read_json(state.checkpoints, default={}) or {}
    gold = read_json(paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
    return {
        "runtime_status": runtime.status,
        "runtime_pid": runtime.pid,
        "handoff_present": bool(handoff),
        "checkpoint_present": bool(checkpoint),
        "gold_present": bool(gold),
        "required_paths": {str(path): path.exists() for path in _required_paths(root)},
    }


def run_repair(
    *,
    root: Path,
    runtime_env: dict[str, str],
    scope: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    intake = _intake(root)
    issues: list[str] = []
    warnings: list[str] = []
    actions_taken: list[str] = []

    python_exe = root / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        issues.append("Virtual environment is missing.")
    for path_str, exists in intake["required_paths"].items():
        if not exists:
            issues.append(f"Missing required path: {path_str}")

    if intake["runtime_status"] == "STALE":
        warnings.append("Runtime PID file is stale.")
        if not dry_run:
            clear_stale_runtime_pid(runtime_pid_file(root))
            actions_taken.append("Cleared stale runtime PID file.")

    sanity = run_command(
        action="sanity-check",
        command=[str(python_exe), str(root / "scripts" / "manage" / "sanity_check.py"), "--write-report"],
        cwd=root,
        env=runtime_env,
        timeout=180,
    ) if python_exe.exists() else {"ok": False, "stderr": "missing python", "failure_class": "environment_missing"}

    if not sanity["ok"]:
        warnings.append("Sanity check reported issues.")

    pipeline = None
    if scope and not dry_run and python_exe.exists():
        pipeline = run_command(
            action="repair-pipeline",
            command=[str(python_exe), str(root / "scripts" / "manage" / "run_pipeline.py"), "--full", "--scope", scope],
            cwd=root,
            env=runtime_env,
            timeout=300,
        )
        if pipeline["ok"]:
            actions_taken.append(f"Ran scoped pipeline refresh for: {scope}")
        else:
            warnings.append("Scoped pipeline refresh failed.")

    openclaw = None
    if not dry_run:
        try:
            openclaw = sync_openclaw_config(validate_cli=False)
            actions_taken.append("Synced OpenClaw config and Otto env contract.")
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(f"OpenClaw sync failed: {exc}")

    status = build_status()
    if not status.get("openclaw_config_sync"):
        warnings.append("OpenClaw config is still not fully in sync.")
    if not status.get("vault_path"):
        issues.append("Vault path is not configured.")

    recommended_next_actions: list[str] = []
    if issues:
        recommended_next_actions.append("Resolve blocking environment issues before running heavy loops.")
    elif warnings:
        recommended_next_actions.append("Review warnings, then rerun `otto.bat loop --mode heartbeat`.")
    else:
        recommended_next_actions.append("Environment looks healthy; run `otto.bat loop` or `otto.bat run`.")
    if scope and dry_run:
        recommended_next_actions.append(f"Run `otto.bat repair --scope \"{scope}\"` to execute the scoped refresh.")

    return {
        "dry_run": dry_run,
        "scope": scope,
        "intake": intake,
        "issues": issues,
        "warnings": warnings,
        "actions_taken": actions_taken,
        "sanity": sanity,
        "pipeline": pipeline,
        "openclaw": openclaw,
        "status": status,
        "recommended_next_actions": recommended_next_actions,
        "safe_to_run_loop": not issues,
    }
