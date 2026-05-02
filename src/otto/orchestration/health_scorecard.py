from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import state_root
from ..state import now_iso, read_json, write_json


def health_scorecard_path() -> Path:
    return state_root() / "ops" / "health_scorecard.json"


def daily_review_path() -> Path:
    return state_root() / "ops" / "daily_review.md"


def _status(passed: bool, *, warn: bool = False) -> str:
    if passed:
        return "green"
    return "yellow" if warn else "red"


def build_health_scorecard(
    *,
    runtime_smoke: dict[str, Any] | None = None,
    soul_health: dict[str, Any] | None = None,
    sanity: dict[str, Any] | None = None,
    heartbeat_readiness: dict[str, Any] | None = None,
    cron_health: dict[str, Any] | None = None,
    golden_paths: dict[str, Any] | None = None,
    rollback: dict[str, Any] | None = None,
    roundtrip: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    runtime_smoke = runtime_smoke or (read_json(state_root() / "runtime" / "smoke_last.json", default={}) or {})
    soul_health = soul_health or (read_json(state_root() / "soul" / "soul_health.json", default={}) or {})
    sanity = sanity or (read_json(state_root() / "sanity" / "sanity_last.json", default={}) or {})
    heartbeat_readiness = heartbeat_readiness or (read_json(state_root() / "schedules" / "heartbeat_readiness.json", default={}) or {})
    cron_health = cron_health or (read_json(state_root() / "ops" / "cron_health_last.json", default={}) or {})
    golden_paths = golden_paths or (read_json(state_root() / "ops" / "golden_path_results.json", default={}) or {})
    rollback = rollback or (read_json(state_root() / "ops" / "rollback_drill_last.json", default={}) or {})
    roundtrip = roundtrip or (read_json(state_root() / "ops" / "qmd_vault_roundtrip_last.json", default={}) or {})

    runtime_section = {
        "wsl_live": _status(runtime_smoke.get("ok") is True),
        "openclaw_gateway": _status(bool((runtime_smoke.get("gates") or {}).get("gateway_live") or (runtime_smoke.get("gates") or {}).get("gateway_shadow"))),
        "telegram_single_owner": _status(bool((runtime_smoke.get("gates") or {}).get("single_owner_lock"))),
        "qmd_native": _status(bool((runtime_smoke.get("gates") or {}).get("qmd_native"))),
    }

    memory_section = {
        "source_registry": _status(bool((runtime_smoke.get("gates") or {}).get("source_registry"))),
        "qmd_manifest": _status(bool((runtime_smoke.get("gates") or {}).get("qmd_manifest"))),
        "review_queue": _status((sanity.get("ok") is True), warn=int(sanity.get("warning_count", 0) or 0) > 0),
        "gold_promotion": _status(bool(roundtrip.get("gold_present"))),
        "vault_writeback": _status(bool(roundtrip.get("vault_writeback_present")), warn=not bool(roundtrip.get("vault_writeback_present"))),
        "qmd_roundtrip": _status(bool(roundtrip.get("ok")), warn=bool(roundtrip.get("no_output_reason"))),
    }

    soul_section = {
        "soul_manifest": _status(bool((soul_health.get("checks") or {}).get("soul_manifest_exists"))),
        "identity_docs": _status(bool((soul_health.get("checks") or {}).get("profile_snapshot_exists"))),
        "heartbeats": _status(bool((soul_health.get("checks") or {}).get("heartbeats_dir_exists"))),
        "context_pack": _status(bool((golden_paths.get("checks") or {}).get("context_pack_has_soul"))),
    }

    creative_section = {
        "song_skeleton": _status(bool((golden_paths.get("checks") or {}).get("telegram_song_route"))),
        "paper_onboarding": _status(bool((golden_paths.get("checks") or {}).get("telegram_paper_route"))),
        "memento": _status(bool((golden_paths.get("checks") or {}).get("memento_route"))),
        "blocker_experiment": _status(bool((golden_paths.get("checks") or {}).get("telegram_weakness_route"))),
        "visual_inspo": _status(bool((heartbeat_readiness.get("optional_checks") or {}).get("visual_sources_declared")), warn=True),
    }

    cron_section = {
        "planned_jobs": _status(bool(cron_health.get("planned_job_count", 0))),
        "enabled_jobs": _status(bool(cron_health.get("ok"))),
        "last_runs": _status(not any(str(item).startswith("last_run_missing:") for item in (cron_health.get("warnings") or [])), warn=True),
        "no_silent_failures": _status(not any(str(item).startswith("no_output_contract:") for item in (cron_health.get("errors") or []))),
    }

    safety_section = {
        "no_auto_publish": _status(not any("unsafe_setting:auto_publish" in str(item) for item in (cron_health.get("errors") or []))),
        "no_raw_qmd": _status(bool((runtime_smoke.get("gates") or {}).get("memory_policy_blocks_raw_to_qmd"))),
        "no_unreviewed_vault": _status(bool((runtime_smoke.get("gates") or {}).get("reflection_policy_safe"))),
        "no_youtube_rip": _status(not any("forbidden_media_job" in str(item) for item in (cron_health.get("errors") or []))),
        "no_diagnostic_claims": _status(bool((golden_paths.get("checks") or {}).get("telegram_weakness_non_diagnostic"))),
    }

    rollback_section = {
        "dry_run_ready": _status(bool(rollback.get("ok"))),
        "no_state_mutation": _status(rollback.get("state_mutation_performed") is False),
    }

    all_sections = [runtime_section, memory_section, soul_section, creative_section, cron_section, safety_section, rollback_section]
    flat_statuses = [status for section in all_sections for status in section.values()]
    overall = "green" if all(status == "green" for status in flat_statuses) else ("yellow" if "red" not in flat_statuses else "red")

    scorecard = {
        "version": 1,
        "generated_at": now_iso(),
        "overall": overall,
        "runtime": runtime_section,
        "memory": memory_section,
        "soul": soul_section,
        "creative": creative_section,
        "cron": cron_section,
        "safety": safety_section,
        "rollback": rollback_section,
    }
    if write:
        write_json(health_scorecard_path(), scorecard)
    return scorecard


def write_daily_review(*, write: bool = True) -> dict[str, Any]:
    lines = [
        "# Otto Daily Review Ritual",
        "",
        "## Morning",
        "- `otto-wsl ops-health --strict`",
        "- `otto-wsl daily-handoff`",
        "- `otto-wsl next-due-jobs`",
        "- `otto-wsl blocker-experiment --dry-run`",
        "",
        "## Midday",
        "- `otto-wsl paper-onboarding --dry-run`",
        "- `otto-wsl song-skeleton --dry-run`",
        "- `otto-wsl memento-due`",
        "",
        "## Night",
        "- `otto-wsl review-queue`",
        "- `otto-wsl memory-promote-reviewed --review-id <id> --dry-run`",
        "- `otto-wsl qmd-reindex --timeout-seconds 300`",
        "- `otto-wsl reflection-candidate --from-outcome <id>`",
        "",
    ]
    markdown = "\n".join(lines)
    target = daily_review_path()
    if write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(markdown, encoding="utf-8")
    return {
        "ok": True,
        "path": str(target),
        "updated_at": now_iso(),
        "line_count": len(lines),
    }
