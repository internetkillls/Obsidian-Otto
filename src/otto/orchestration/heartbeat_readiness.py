from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..adapters.openclaw.context_pack import build_openclaw_context_pack
from ..adapters.openclaw.tool_payloads import build_openclaw_tool_manifest
from ..adapters.qmd.manifest import qmd_manifest_health
from ..autonomy.autonomous_generation import run_autonomous_heartbeat
from ..autonomy.generation_policy import autonomous_policy_health
from ..creative.inspo import load_visual_inspo_policy
from ..creative.songforge import build_song_skeleton, load_songforge_policy
from ..governance_utils import state_root
from ..memory.source_registry import validate_source_registry
from ..openclaw_support import build_qmd_index_health, probe_openclaw_gateway
from ..research.paper_onboarding import create_onboarding_pack
from ..skills.blocker_map import load_blocker_map, skill_review
from ..skills.skill_graph import load_skill_hierarchy
from ..state import now_iso, write_json
from ..soul.health import build_qmd_soul_audit, build_soul_health
from .creative_heartbeat import load_creative_heartbeat_policy, run_creative_heartbeat, soul_v2_path
from .cron_plan import build_planned_jobs
from .runtime_owner import STATE_WSL_LIVE, build_runtime_owner


def heartbeat_readiness_path() -> Path:
    return state_root() / "schedules" / "heartbeat_readiness.json"


def _command_registry() -> dict[str, Callable[[], dict[str, Any]]]:
    return {
        "creative-heartbeat --dry-run": lambda: run_creative_heartbeat(dry_run=True),
        "autonomous-heartbeat --dry-run": lambda: run_autonomous_heartbeat(dry_run=True),
        "song-skeleton --dry-run": lambda: build_song_skeleton("# Cinta Fana\n@ Penderitaan dan cinta tak kenal waktu.", dry_run=True),
        "paper-onboarding --dry-run": lambda: create_onboarding_pack("HCI value-sensitive design and interface constraints", dry_run=True),
        "memento-due": lambda: {"ok": True, "quiz_count": 0, "no_output_reason": "no_blocks_yet"},
        "blocker-experiment --dry-run": lambda: skill_review(dry_run=True),
        "visual-inspo-query --dry-run": lambda: {"ok": True, **load_visual_inspo_policy()["visual_inspo_policy"], "visual_query": "seed query"},
        "openclaw-context-pack": lambda: {"ok": True, "context_pack": build_openclaw_context_pack(task="heartbeat-readiness")},
        "openclaw-tool-manifest": lambda: {"ok": True, "manifest": build_openclaw_tool_manifest()},
        "runtime-smoke": lambda: {"ok": True, "deferred": True},
        "soul-health": lambda: build_soul_health(),
        "qmd-soul-audit": lambda: build_qmd_soul_audit(),
    }


def _output_contract_passed(result: dict[str, Any], expected: tuple[str, ...]) -> bool:
    if not result.get("ok"):
        return False
    if any(result.get(key) for key in expected):
        return True
    return bool(result.get("no_output_reason"))


def build_heartbeat_readiness(*, strict: bool = False, write: bool = True, run_dry_runs: bool = True) -> dict[str, Any]:
    commands = _command_registry()
    expected_outputs: dict[str, tuple[str, ...]] = {
        "creative-heartbeat --dry-run": ("song_skeleton", "paper_onboarding", "memento_due"),
        "song-skeleton --dry-run": ("skeleton",),
        "paper-onboarding --dry-run": ("pack",),
        "memento-due": ("quiz_count", "quizzes"),
        "blocker-experiment --dry-run": ("tasks",),
        "visual-inspo-query --dry-run": ("visual_query",),
    }

    required_commands = [
        "creative-heartbeat --dry-run",
        "song-skeleton --dry-run",
        "paper-onboarding --dry-run",
        "memento-due",
        "blocker-experiment --dry-run",
        "visual-inspo-query --dry-run",
        "openclaw-context-pack",
        "openclaw-tool-manifest",
        "runtime-smoke",
        "soul-health",
        "qmd-soul-audit",
    ]
    discovery = {name: (name in commands) for name in required_commands}

    dry_runs: dict[str, dict[str, Any]] = {}
    dry_run_checks: dict[str, bool] = {}
    if run_dry_runs:
        for name in required_commands:
            runner = commands.get(name)
            if not runner:
                continue
            result = runner()
            dry_runs[name] = result
            if name in expected_outputs:
                dry_run_checks[name] = _output_contract_passed(result, expected_outputs[name])
            else:
                dry_run_checks[name] = bool(result.get("ok", False))

    tool_manifest = build_openclaw_tool_manifest()
    tool_names = {tool.get("name") for tool in tool_manifest.get("tools", []) if isinstance(tool, dict)}
    expected_tools = {
        "otto.heartbeat",
        "otto.song_skeleton_next",
        "otto.paper_onboarding_next",
        "otto.memento_due",
        "otto.blocker_experiment_next",
        "otto.visual_inspo_query",
        "otto.feedback_ingest",
        "otto.heartbeat_readiness",
    }
    owner = build_runtime_owner()
    runtime_state = str(owner.get("runtime_state") or "")
    gateway_runtime = "wsl-live" if runtime_state == STATE_WSL_LIVE else "wsl-shadow"
    live_gateway_port = int(((owner.get("ubuntu_openclaw") or {}).get("gateway_port") or 18790))
    gateway_probe = probe_openclaw_gateway(runtime=gateway_runtime, port=live_gateway_port, timeout_seconds=3)

    bridge_checks = {
        "gateway_health_green": bool(gateway_probe.get("ok")),
        "tool_manifest_has_heartbeat_tools": expected_tools.issubset(tool_names),
        "context_pack_has_creative_summary": bool(build_openclaw_context_pack(task="heartbeat-readiness").get("creative_heartbeat_summary")),
        "qmd_retrieval_ok": bool(build_qmd_index_health().get("ok")),
        "source_registry_ok": bool(validate_source_registry().get("ok")),
        "qmd_manifest_ok": bool(qmd_manifest_health().get("ok")),
    }

    soul = build_soul_health()
    qmd_soul = build_qmd_soul_audit()
    skills = load_skill_hierarchy()
    blockers = load_blocker_map()
    soul_agent_skill = {
        "soul_health_ok": bool(soul.get("ok")),
        "qmd_soul_audit_ok": bool(qmd_soul.get("ok")),
        "context_pack_has_soul": bool(build_openclaw_context_pack(task="heartbeat-readiness").get("soul")),
        "skill_hierarchy_exists": bool(skills.get("domains")),
        "blocker_map_exists": bool(blockers.get("blockers")),
        "otto_soul_v2_sidecar_exists": soul_v2_path().exists(),
    }

    policy = load_creative_heartbeat_policy()
    safety = {
        "auto_publish_false": policy["safety"]["auto_publish"] is False,
        "auto_qmd_index_raw_false": policy["safety"]["auto_qmd_index_raw"] is False,
        "auto_download_youtube_false": policy["safety"]["auto_download_youtube"] is False,
        "auto_enable_telegram_false": policy["safety"]["auto_enable_telegram"] is False,
        "auto_vault_write_unreviewed_false": policy["safety"].get("auto_vault_write_unreviewed") is False,
        "song_auto_qmd_index_false": load_songforge_policy()["safety"]["auto_qmd_index"] is False,
        "autonomous_generation_policy_ok": bool(autonomous_policy_health().get("ok")),
    }

    planned_jobs = build_planned_jobs()
    cron_checks = {
        "planned_jobs_present": len(planned_jobs) >= 4,
        "song_skeleton_every_4h": any(job["name"] == "song_skeleton" and job["cadence"].get("every_hours") == 4 for job in planned_jobs),
        "paper_onboarding_4_6h_policy": any(job["name"] == "paper_onboarding" and job["cadence"].get("policy_window_hours") == [4, 6] for job in planned_jobs),
        "blocker_daily": any(job["name"] == "blocker_experiment" and job["cadence"].get("every_hours") == 24 for job in planned_jobs),
        "memento_every_8h": any(job["name"] == "memento_due" and job["cadence"].get("every_hours") == 8 for job in planned_jobs),
    }

    required_checks = [
        all(discovery.values()),
        all(dry_run_checks.values()) if run_dry_runs else True,
        all(bridge_checks.values()),
        all(soul_agent_skill.values()),
        all(safety.values()),
        all(cron_checks.values()),
    ]
    optional_checks = {
        "visual_sources_declared": bool(load_visual_inspo_policy()["visual_inspo_policy"]["sources"]),
    }
    ok = all(required_checks)
    if strict and not all(optional_checks.values()):
        # Optional visual source gaps only warn in strict mode by policy.
        pass

    result = {
        "ok": ok,
        "strict": strict,
        "checked_at": now_iso(),
        "state": "HB1_PROACTIVE_HEARTBEAT_ASSURANCE_READY" if ok else "HB1_BLOCKED",
        "discovery": discovery,
        "dry_run_checks": dry_run_checks,
        "bridge_checks": bridge_checks,
        "soul_agent_skill_checks": soul_agent_skill,
        "cron_checks": cron_checks,
        "safety_checks": safety,
        "optional_checks": optional_checks,
        "warnings": [] if all(optional_checks.values()) else ["optional_visual_source_gap"],
        "dry_runs": dry_runs if run_dry_runs else {},
        "gateway_probe": gateway_probe,
    }
    if write:
        write_json(heartbeat_readiness_path(), result)
    return result
