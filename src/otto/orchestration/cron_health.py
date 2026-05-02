from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import read_jsonl, state_root
from ..state import now_iso, write_json
from .cron_plan import planned_jobs_path
from .cron_render import verify_cron_plan


def cron_health_path() -> Path:
    return state_root() / "ops" / "cron_health_last.json"


def _uses_stable_wsl_launcher(command: str) -> bool:
    normalized = command.strip()
    return (
        normalized.startswith("/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-cli-wsl.sh ")
        or normalized.startswith("/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/openclaw-wsl.sh ")
    )


def _last_run_by_job() -> dict[str, dict[str, Any]]:
    runs = read_jsonl(state_root() / "runtime" / "heartbeat_router_runs.jsonl")
    latest: dict[str, dict[str, Any]] = {}
    for row in runs:
        name = str(row.get("job_name") or "").strip()
        if not name:
            continue
        latest[name] = row
    return latest


def build_cron_health(*, write: bool = True) -> dict[str, Any]:
    verify = verify_cron_plan()
    jobs = read_jsonl(planned_jobs_path())
    latest_runs = _last_run_by_job()

    errors: list[str] = []
    warnings: list[str] = []
    job_checks: list[dict[str, Any]] = []

    if not jobs:
        errors.append("planned_jobs_missing_or_empty")

    for job in jobs:
        name = str(job.get("name") or "")
        command = str(job.get("command") or "")
        expected_output = str(job.get("expected_output") or "")

        if not _uses_stable_wsl_launcher(command):
            errors.append(f"launcher_missing_or_fragile:{name}")
        if not expected_output:
            errors.append(f"expected_output_missing:{name}")

        command_lc = command.lower()
        if "youtube" in command_lc or "yt-dlp" in command_lc or "youtube-dl" in command_lc:
            errors.append(f"forbidden_media_job:{name}")

        last = latest_runs.get(name)
        if not last:
            warnings.append(f"last_run_missing:{name}")
            job_checks.append(
                {
                    "name": name,
                    "has_last_run": False,
                    "expected_output": expected_output,
                    "output_contract_ok": False,
                    "no_output_reason": "never_run",
                }
            )
            continue

        output_contract_ok = bool(last.get("actual_outputs")) or bool(last.get("no_output_reason"))
        if not output_contract_ok:
            errors.append(f"no_output_contract:{name}")

        if last.get("ok") is False:
            errors.append(f"last_run_failed:{name}")

        job_checks.append(
            {
                "name": name,
                "has_last_run": True,
                "last_run_at": last.get("timestamp"),
                "ok": bool(last.get("ok")),
                "expected_output": expected_output,
                "actual_outputs": last.get("actual_outputs") or [],
                "no_output_reason": last.get("no_output_reason"),
                "output_contract_ok": output_contract_ok,
            }
        )

    for error in verify.get("errors") or []:
        errors.append(f"verify:{error}")
    for warning in verify.get("warnings") or []:
        warnings.append(f"verify:{warning}")

    ok = len(errors) == 0
    result = {
        "ok": ok,
        "checked_at": now_iso(),
        "state": "CRON1_PROACTIVE_CREATIVE_CRON_ENABLED" if ok else "CRON1_BLOCKED",
        "planned_jobs_path": str(planned_jobs_path()),
        "planned_job_count": len(jobs),
        "job_checks": job_checks,
        "errors": errors,
        "warnings": warnings,
        "verify": verify,
    }
    if write:
        write_json(cron_health_path(), result)
    return result
