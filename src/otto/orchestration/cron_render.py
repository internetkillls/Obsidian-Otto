from __future__ import annotations

from pathlib import Path
from typing import Any

from ..creative.songforge import load_songforge_policy
from ..governance_utils import read_jsonl, state_root
from ..memento.policy import load_memento_policy
from ..research.paper_onboarding import load_paper_onboarding_policy
from .creative_heartbeat import load_creative_heartbeat_policy
from .cron_plan import planned_jobs_path, write_cron_plan


def cron_rendered_disabled_path() -> Path:
    return state_root() / "schedules" / "cron_rendered.disabled"


def _is_launcher_command(command: str) -> bool:
    normalized = command.strip()
    return (
        normalized.startswith("/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-cli-wsl.sh ")
        or normalized.startswith("/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/openclaw-wsl.sh ")
    )


def render_cron_disabled() -> dict[str, Any]:
    plan_path = planned_jobs_path()
    if not plan_path.exists():
        write_cron_plan()
    jobs = read_jsonl(plan_path)
    lines = [
        "# Otto creative heartbeat plan (disabled by design)",
        "# Do not install as OS cron without explicit enable step.",
        "",
    ]
    for job in jobs:
        name = str(job.get("name"))
        cadence = job.get("cadence") or {}
        command = str(job.get("command") or "")
        if "every_hours" in cadence:
            hours = int(cadence["every_hours"])
            expr = f"0 */{hours} * * *"
        else:
            expr = "0 * * * *"
        lines.append(f"# {expr} {command}  # {name}")
    content = "\n".join(lines) + "\n"
    target = cron_rendered_disabled_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": str(target), "disabled": True, "line_count": len(lines)}


def verify_cron_plan() -> dict[str, Any]:
    plan_path = planned_jobs_path()
    disabled_path = cron_rendered_disabled_path()
    errors: list[str] = []
    warnings: list[str] = []
    if not plan_path.exists():
        errors.append("planned_jobs_missing")
    jobs = read_jsonl(plan_path)
    if not jobs:
        errors.append("planned_jobs_empty")
    for job in jobs:
        command = str(job.get("command") or "")
        if not _is_launcher_command(command):
            errors.append(f"invalid_command_prefix:{job.get('name')}")
        if not job.get("expected_output"):
            errors.append(f"expected_output_missing:{job.get('name')}")
    if not disabled_path.exists():
        warnings.append("cron_rendered_disabled_missing")

    safety_checks = {
        "auto_publish": load_creative_heartbeat_policy()["safety"]["auto_publish"] is False,
        "auto_qmd_index_raw": load_creative_heartbeat_policy()["safety"]["auto_qmd_index_raw"] is False,
        "creative_auto_vault_write_unreviewed": load_creative_heartbeat_policy()["safety"].get("auto_vault_write_unreviewed") is False,
        "paper_auto_vault_write": load_paper_onboarding_policy()["paper_onboarding_policy"]["auto_vault_write"] is False,
        "song_auto_qmd_index": load_songforge_policy()["safety"]["auto_qmd_index"] is False,
        "memento_enabled": load_memento_policy()["memento_policy"]["enabled"] is True,
    }
    for key, passed in safety_checks.items():
        if not passed:
            errors.append(f"unsafe_setting:{key}")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "planned_jobs_count": len(jobs),
        "cron_rendered_disabled_exists": disabled_path.exists(),
        "os_cron_installed": False,
        "safety_checks": safety_checks,
    }
