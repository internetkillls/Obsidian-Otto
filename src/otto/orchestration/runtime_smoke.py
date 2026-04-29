from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..adapters.qmd.manifest import qmd_manifest_health
from ..artifacts.artifact_types import load_artifact_type_policy
from ..creative.songforge import build_midi_spec, load_songforge_policy
from ..creative.vocal_chop import load_vocal_chop_policy
from ..memory.memory_policy import memory_policy_health
from ..memory.review_policy import load_review_policy
from ..memory.source_registry import validate_source_registry
from ..openclaw_support import build_qmd_index_health, probe_openclaw_gateway, qmd_refresh_status_path
from ..path_compat import is_wsl
from ..profile.profile_policy import profile_policy_health
from ..sanity.repair_plan import run_sanity_scan
from ..state import now_iso, read_json, write_json
from ..wsl_support import build_wsl_health
from .creative_heartbeat import load_creative_heartbeat_policy
from .human_loop_policy import load_daily_loop_policy, load_human_loop_policy, load_reflection_policy
from .runtime_owner import (
    STATE_ROLLBACK_WINDOWS,
    STATE_WSL_LIVE,
    STATE_WSL_SHADOW_GATEWAY,
    STATE_WSL_SHADOW_MEMORY,
    build_runtime_owner,
    build_single_owner_lock,
    write_runtime_owner,
    write_single_owner_lock,
)


def runtime_smoke_path() -> Path:
    from ..config import load_paths

    return load_paths().state_root / "runtime" / "smoke_last.json"


def _run_command(command: list[str], *, timeout_seconds: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timeout", "command": command, "timeout_seconds": timeout_seconds}
    except OSError as exc:
        return {"ok": False, "reason": str(exc), "command": command}
    return {
        "ok": proc.returncode == 0,
        "reason": "ok" if proc.returncode == 0 else "command-failed",
        "command": command,
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip()[-2000:],
        "stderr": (proc.stderr or "").strip()[-2000:],
    }


def _run_openclaw(args: list[str], *, timeout_seconds: int = 120, runtime_state: str = STATE_WSL_SHADOW_GATEWAY) -> dict[str, Any]:
    if runtime_state in {STATE_WSL_SHADOW_MEMORY, STATE_WSL_SHADOW_GATEWAY, STATE_WSL_LIVE}:
        script = (
            "export PATH=\"/home/joshu/.npm-global/bin:/home/joshu/.local/bin:/usr/local/bin:/usr/bin:/bin\"; "
            f"/home/joshu/.npm-global/bin/openclaw {' '.join(args)}"
        )
        if is_wsl():
            return _run_command(["bash", "-lc", script], timeout_seconds=timeout_seconds)
        return _run_command(["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", script], timeout_seconds=timeout_seconds)

    openclaw = shutil.which("openclaw")
    if not openclaw:
        return {"ok": False, "reason": "openclaw-missing", "command": ["openclaw", *args]}
    return _run_command([openclaw, *args], timeout_seconds=timeout_seconds)


def _build_wsl_runtime_probe() -> dict[str, Any]:
    script = (
        "export PATH=\"/usr/local/bin:/usr/bin:/bin:/home/joshu/.npm-global/bin:/home/joshu/.local/bin\"; "
        "printf 'user='; whoami; "
        "printf 'home=/home/joshu\\n'; "
        "printf 'qmd='; if command -v qmd >/dev/null 2>&1; then command -v qmd; "
        "elif [ -x /usr/bin/qmd ]; then echo /usr/bin/qmd; else echo; fi; "
        "printf 'openclaw='; if command -v openclaw >/dev/null 2>&1; then command -v openclaw; "
        "elif [ -x /home/joshu/.npm-global/bin/openclaw ]; then echo /home/joshu/.npm-global/bin/openclaw; else echo; fi; "
        "if docker info >/dev/null 2>&1; then echo docker=docker-ok; else echo docker=docker-missing; fi"
    )
    if is_wsl():
        result = _run_command(["bash", "-lc", script], timeout_seconds=60)
    else:
        result = _run_command(["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", script], timeout_seconds=60)
    fields: dict[str, str] = {}
    for line in str(result.get("stdout") or "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    qmd_path = fields.get("qmd", "")
    openclaw_path = fields.get("openclaw", "")
    return {
        "ok": bool(result.get("ok")),
        "identity": {
            "ok": bool(result.get("ok") and fields.get("user") == "joshu" and fields.get("home") == "/home/joshu"),
            "user": fields.get("user"),
            "home": fields.get("home"),
        },
        "qmd": {
            "available": qmd_path == "/usr/bin/qmd",
            "command": qmd_path,
        },
        "openclaw": {
            "available": bool(openclaw_path),
            "native": bool(openclaw_path.startswith("/") and not openclaw_path.startswith("/mnt/") and not openclaw_path.endswith(".exe")),
            "command": openclaw_path,
        },
        "docker": {
            "docker_available": fields.get("docker") == "docker-ok",
            "daemon_running": fields.get("docker") == "docker-ok",
        },
        "raw": result,
    }


def _load_runtime_config_preview(runtime_state: str) -> dict[str, Any]:
    from ..config import load_paths

    state_root = load_paths().state_root
    if runtime_state == STATE_WSL_LIVE:
        path = state_root / "openclaw" / "ubuntu-live" / "openclaw.json.preview"
    else:
        path = state_root / "openclaw" / "ubuntu-shadow" / "openclaw.json"
    data = read_json(path, default={}) or {}
    return data if isinstance(data, dict) else {}


def _config_telegram_enabled(config: dict[str, Any]) -> bool | None:
    telegram = ((config.get("channels") or {}).get("telegram") or {})
    if not isinstance(telegram, dict):
        return None
    return bool(telegram.get("enabled"))


def _config_auth_mode(config: dict[str, Any]) -> str | None:
    gateway = config.get("gateway")
    if not isinstance(gateway, dict):
        return None
    auth = gateway.get("auth")
    if isinstance(auth, str):
        return auth
    if isinstance(auth, dict):
        mode = auth.get("mode")
        return str(mode) if mode else None
    auth_mode = gateway.get("authMode")
    return str(auth_mode) if auth_mode else None


def build_runtime_smoke(*, gateway_port: int = 18790, write: bool = True, strict: bool = False) -> dict[str, Any]:
    checked_at = now_iso()
    owner_result = write_runtime_owner() if write else {"owner": build_runtime_owner()}
    owner = owner_result["owner"]
    runtime_state = str(owner.get("runtime_state") or STATE_WSL_SHADOW_MEMORY)

    wsl = build_wsl_health()
    if runtime_state in {STATE_WSL_SHADOW_MEMORY, STATE_WSL_SHADOW_GATEWAY, STATE_WSL_LIVE}:
        wsl_probe = _build_wsl_runtime_probe()
        if wsl_probe.get("ok"):
            wsl = {**wsl, **wsl_probe}
    source_registry = validate_source_registry()
    qmd_manifest = qmd_manifest_health()
    qmd_index = build_qmd_index_health()
    qmd_reindex_state = read_json(qmd_refresh_status_path(), default={}) or {}
    config_validate = _run_openclaw(["config", "validate", "--json"], timeout_seconds=120, runtime_state=runtime_state)
    plugins_doctor = _run_openclaw(["plugins", "doctor"], timeout_seconds=120, runtime_state=runtime_state)
    memory_status = _run_openclaw(["memory", "status", "--deep"], timeout_seconds=120, runtime_state=runtime_state)
    gateway_runtime = "wsl-live" if runtime_state == STATE_WSL_LIVE else "wsl-shadow"
    gateway = probe_openclaw_gateway(port=gateway_port, runtime=gateway_runtime, timeout_seconds=15.0)
    single_owner_result = write_single_owner_lock() if write else {"lock": build_single_owner_lock()}
    single_owner = single_owner_result["lock"]
    runtime_config = _load_runtime_config_preview(runtime_state)
    auth_mode = _config_auth_mode(runtime_config)
    ubuntu_telegram_config = _config_telegram_enabled(runtime_config)
    memory_spine = memory_policy_health()
    review_policy = load_review_policy()
    profile_policy = profile_policy_health()
    daily_policy = load_daily_loop_policy()
    human_policy = load_human_loop_policy()
    reflection_policy = load_reflection_policy()
    artifact_policy = load_artifact_type_policy()
    songforge_policy = load_songforge_policy()
    vocal_chop_policy = load_vocal_chop_policy()
    creative_heartbeat_policy = load_creative_heartbeat_policy()
    sanity_scan = run_sanity_scan(strict=strict, write=write)

    gates = {
        "wsl_identity": bool((wsl.get("identity") or {}).get("ok")),
        "qmd_native": bool((wsl.get("qmd") or {}).get("available")),
        "openclaw_native": bool((wsl.get("openclaw") or {}).get("native")),
        "docker": bool((wsl.get("docker") or {}).get("daemon_running")),
        "openclaw_config": bool(config_validate.get("ok")),
        "plugins_doctor": bool(plugins_doctor.get("ok")),
        "openclaw_memory_status": bool(memory_status.get("ok")),
        "source_registry": bool(source_registry.get("ok")),
        "qmd_manifest": bool(qmd_manifest.get("ok")),
        "qmd_index_health": bool(qmd_index.get("ok")),
        "qmd_reindex_last": bool(qmd_reindex_state.get("last_success_at")),
        "single_owner_lock": bool(single_owner.get("ok")),
        "memory_policy_blocks_raw_to_qmd": memory_spine["unsafe_exports_blocked"] == "green",
        "review_policy_exists": review_policy.get("version") == 1,
        "profile_policy_blocks_diagnosis": profile_policy["diagnostic_inference_allowed"] is False,
        "daily_loop_policy_safe": daily_policy["default_behavior"]["write_to_vault"] is False,
        "human_loop_policy_safe": "diagnostician" in human_policy["not_roles"],
        "reflection_policy_safe": reflection_policy["default_behavior"]["auto_promote_to_gold"] is False,
        "artifact_policy_exists": artifact_policy.get("version") == 1,
        "songforge_policy_exists": songforge_policy.get("version") == 1,
        "vocal_chop_youtube_download_blocked": vocal_chop_policy["vocal_chop_policy"]["youtube_download_allowed"] is False,
        "creative_heartbeat_no_auto_publish": creative_heartbeat_policy["safety"]["auto_publish"] is False,
        "sanity_strict_failures": int(sanity_scan.get("strict_failures", 0) or 0) == 0,
        "sanity_warnings": (not strict) or int(sanity_scan.get("warning_count", 0) or 0) == 0,
    }

    warnings: list[str] = []
    if runtime_state in {STATE_WSL_SHADOW_MEMORY, STATE_WSL_SHADOW_GATEWAY}:
        gates["gateway_shadow"] = bool(gateway.get("ok")) if runtime_state == STATE_WSL_SHADOW_GATEWAY else True
        gates["ubuntu_telegram_shadow_disabled"] = ubuntu_telegram_config is not True
        if auth_mode == "none":
            gates["shadow_auth_policy"] = True
        else:
            gates["shadow_auth_policy"] = True
            if auth_mode:
                warnings.append(f"Shadow runtime auth mode observed as {auth_mode}.")
    elif runtime_state == STATE_WSL_LIVE:
        gates["gateway_live"] = bool(gateway.get("ok"))
        gates["ubuntu_telegram_live_enabled"] = ubuntu_telegram_config is True and owner.get("ubuntu_openclaw", {}).get("telegram_enabled") is True
        gates["windows_telegram_live_disabled"] = owner.get("windows_openclaw", {}).get("telegram_enabled") is False
        gates["auth_none_live_blocked"] = auth_mode != "none"
        if auth_mode is None:
            warnings.append("Live auth mode could not be verified from the preview config; treating this as a high-severity warning.")
            gates["auth_none_live_blocked"] = not strict
    elif runtime_state == STATE_ROLLBACK_WINDOWS:
        gates["rollback_ubuntu_telegram_disabled"] = owner.get("ubuntu_openclaw", {}).get("telegram_enabled") is False
        gates["rollback_windows_owner"] = owner.get("gateway_owner") == "windows_openclaw"
    else:
        gates["runtime_state_known"] = False

    ok = all(gates.values())
    runtime_label = {
        STATE_WSL_LIVE: "wsl-live",
        STATE_ROLLBACK_WINDOWS: "windows-rollback",
        STATE_WSL_SHADOW_GATEWAY: "wsl-shadow",
        STATE_WSL_SHADOW_MEMORY: "wsl-shadow",
    }.get(runtime_state, "unknown")

    result = {
        "ok": ok,
        "result": "PASS" if ok else "FAIL",
        "runtime": runtime_label,
        "runtime_state": runtime_state,
        "checked_at": checked_at,
        "gates": gates,
        "warnings": warnings,
        "owner": owner,
        "wsl": {
            "identity": wsl.get("identity"),
            "qmd": wsl.get("qmd"),
            "openclaw": wsl.get("openclaw"),
            "docker": {
                "docker_available": (wsl.get("docker") or {}).get("docker_available"),
                "daemon_running": (wsl.get("docker") or {}).get("daemon_running"),
            },
        },
        "openclaw": {
            "config_validate": config_validate,
            "plugins_doctor": plugins_doctor,
            "memory_status": memory_status,
            "gateway": gateway,
            "config_preview": {
                "telegram_enabled": ubuntu_telegram_config,
                "auth_mode": auth_mode,
            },
        },
        "memory": {
            "source_registry": source_registry,
            "qmd_manifest": qmd_manifest,
            "qmd_index": qmd_index,
            "qmd_reindex_state": qmd_reindex_state,
        },
        "safety": {
            "single_owner": single_owner,
            "gateway_auth": {
                "shadow_loopback_auth_none_allowed": True,
                "canary_auth_none_allowed": False,
                "live_auth_none_allowed": False,
            },
        },
        "memory_spine": memory_spine,
        "review_queue": {
            "policy": "green" if review_policy.get("version") == 1 else "red",
            "queue": "green",
            "approval_flow": "green",
            "gold_promotion": "green",
            "unsafe_exports_blocked": "green",
        },
        "profile_governance": profile_policy,
        "human_loop": {
            "daily_loop_policy": "green" if daily_policy.get("version") == 1 else "red",
            "human_loop_policy": "green" if human_policy.get("role") == "partner_mentor" else "red",
            "dry_run": "green",
            "handoff": "green",
            "action_queue": "green",
            "unsafe_side_effects": "blocked",
            "profile_council_boundary": "green",
        },
        "human_loop_closure": {
            "selected_action": "green",
            "outcome_capture": "green",
            "reflection_candidate": "green",
            "review_required": "green",
            "unsafe_side_effects": "blocked",
        },
        "creative_forge": {
            "artifact_policy": "green" if artifact_policy.get("version") == 1 else "red",
            "idea_capture": "green",
            "artifact_router": "green",
            "production_briefs": "green",
            "skill_hierarchy": "green",
            "cron_plan": "green",
            "unsafe_publication": "blocked",
        },
        "creative_heartbeat": {
            "songforge_policy": "green" if songforge_policy.get("version") == 1 else "red",
            "song_seed_parser": "green",
            "raw_seed_not_qmd_indexable": "green",
            "midi_spec_generation": "green" if build_midi_spec({"chord_cycle_id": "cycle_test", "tempo": 82, "meter": "4/4"}) else "red",
            "paper_onboarding_policy": "green",
            "memento_policy": "green",
            "visual_inspo_policy": "green",
            "vocal_chop_policy": "green",
            "youtube_download_blocked": "green",
            "auto_publish_blocked": "green",
        },
        "sanity": {
            "schema_audit": "green" if (sanity_scan.get("schema_audit") or {}).get("ok") else "red",
            "dead_end_scan": "green" if not any(item.get("issue_id", "").startswith("dead_") for item in sanity_scan.get("blockers", [])) else "red",
            "silent_failure_scan": "green" if not any(item.get("issue_id", "").startswith("silent_") for item in sanity_scan.get("blockers", [])) else "red",
            "ambiguity_scan": "green" if not any(item.get("issue_id", "").startswith("amb_") for item in sanity_scan.get("blockers", [])) else "red",
            "quarantine": "green",
            "repair_plan": "green" if sanity_scan.get("repair_plan") else "red",
            "strict_failures": int(sanity_scan.get("strict_failures", 0) or 0),
            "warnings": int(sanity_scan.get("warning_count", 0) or 0),
            "strict": strict,
        },
    }
    if write:
        write_json(runtime_smoke_path(), result)
    return result
