from __future__ import annotations
import importlib.util
import sqlite3
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..docker_utils import docker_compose_status
from ..infra import build_infra_result
from ..launcher_state import LauncherStateStore
from ..models import model_matrix
from ..orchestration.graph_demotion import (
    GRAPH_CONTROLLER_FALLBACK_GOAL,
    graph_controller_handoff_fields,
    graph_handoff_is_active,
    load_graph_demotion_review,
)
from ..orchestration.morpheus_openclaw_bridge import load_morpheus_openclaw_bridge
from ..openclaw_support import build_openclaw_health, probe_openclaw_gateway
from ..schema_registry import schema_fingerprint, schema_registry
from ..state import OttoState, read_json
from .runtime_support import classify_runtime, runtime_pid_file


def _tail(path: Path, limit: int = 10) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def _sqlite_status(sqlite_path: Path) -> dict[str, Any]:
    exists = sqlite_path.exists()
    status = {
        "path": str(sqlite_path),
        "exists": exists,
        "size_bytes": sqlite_path.stat().st_size if exists else 0,
        "table_count": 0,
        "note_count": 0,
    }
    if not exists:
        return status

    try:
        conn = sqlite3.connect(sqlite_path)
        try:
            status["table_count"] = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table', 'view')"
            ).fetchone()[0]
            note_row = conn.execute("SELECT COUNT(*) FROM notes").fetchone()
            status["note_count"] = int(note_row[0] or 0) if note_row else 0
        finally:
            conn.close()
    except sqlite3.Error:
        status["read_error"] = True
    return status


def _vector_status(paths, gold: dict[str, Any], infra: dict[str, Any]) -> dict[str, Any]:
    chroma_installed = importlib.util.find_spec("chromadb") is not None
    vector_summary = read_json(paths.artifacts_root / "reports" / "vector_summary.json", default={}) or {}
    gold_vector = (gold.get("vector_cache") or {})
    running_services = set(infra.get("running_services") or [])
    configured_services = set(infra.get("configured_services") or [])
    running_services_known = bool(infra.get("running_services_known", True))

    note = vector_summary.get("note") or gold_vector.get("note")
    if not note and not chroma_installed:
        note = "chromadb Python package missing"

    service_configured = "chromadb" in configured_services
    service_running = ("chromadb" in running_services) if running_services_known else None
    return {
        "python_package_installed": chroma_installed,
        "service_configured": service_configured,
        "service_running_known": running_services_known,
        "service_running": service_running,
        "store_path": str(paths.chroma_path),
        "store_exists": paths.chroma_path.exists(),
        "enabled": bool(vector_summary.get("enabled", gold_vector.get("enabled", False))),
        "chunk_count": int(vector_summary.get("chunk_count", gold_vector.get("chunk_count", 0)) or 0),
        "note": note,
    }


def _controller_issues(
    checkpoint: dict[str, Any],
    sqlite: dict[str, Any],
    openclaw: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if openclaw.get("config_drift_free") is False:
        issues.append("openclaw live config has drift relative to repo config")
    checkpoint_db = str(checkpoint.get("silver_db") or "").strip()
    sqlite_path = str(sqlite.get("path") or "").strip()
    if checkpoint_db and sqlite_path and Path(checkpoint_db) != Path(sqlite_path):
        issues.append("checkpoint silver_db points at a different database than the live sqlite path")
    return issues


def _infra_issues(
    runtime: dict[str, Any],
    sqlite: dict[str, Any],
    infra: dict[str, Any],
    vector: dict[str, Any],
    openclaw: dict[str, Any],
    gateway_probe: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if runtime.get("status") == "STALE":
        issues.append("runtime PID is stale; stop/start runtime to refresh control state")
    if not sqlite.get("exists"):
        issues.append("sqlite silver DB is missing")
    if vector.get("service_configured") and vector.get("service_running") is False:
        issues.append("chromadb service is configured but not running")
    if vector.get("service_configured") and not vector.get("service_running_known"):
        probe_status = infra.get("docker_probe_status") or "probe-failed"
        if probe_status == "access-denied":
            issues.append("Docker probe from Python is denied; chromadb runtime state cannot be verified")
        else:
            issues.append(f"Docker probe is not reliable ({probe_status}); chromadb runtime state cannot be verified")
    if not vector.get("python_package_installed"):
        issues.append("chromadb Python package is not installed; vector cache stays disabled")
    if not infra.get("postgres_reachable"):
        issues.append("postgres is not reachable")
    if openclaw.get("hf_fallback_ready") is False:
        issues.append("OpenClaw HF fallback is not ready in current live state")
    if gateway_probe.get("ok") is False and gateway_probe.get("transient_restart_window"):
        issues.append("OpenClaw gateway is in a transient restart window")
    elif gateway_probe.get("ok") is False:
        issues.append("OpenClaw gateway HTTP probe is unhealthy")
    return issues


def _state_label(value: bool | None, *, positive: str, negative: str, unknown: str = "unknown") -> str:
    if value is None:
        return unknown
    return positive if value else negative


def _effective_next_actions(gold: dict[str, Any], handoff: dict[str, Any]) -> list[str]:
    handoff_actions = [str(item).strip() for item in (handoff.get("next_actions") or []) if str(item).strip()]
    if handoff_actions:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in handoff_actions:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
    gold_actions = [str(item).strip() for item in (gold.get("next_actions") or []) if str(item).strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for item in gold_actions:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _controller_surface(handoff: dict[str, Any], gold: dict[str, Any], paths: Any) -> dict[str, Any]:
    graph_review = load_graph_demotion_review(paths)
    if graph_review:
        controller_fields = graph_controller_handoff_fields(
            graph_review,
            handoff=handoff,
            fallback_actions=[str(item).strip() for item in (gold.get("next_actions") or []) if str(item).strip()],
        )
        return {
            "source": "handoff" if graph_handoff_is_active(graph_review, handoff) else "graph_review",
            "goal": controller_fields["goal"],
            "next_actions": controller_fields["next_actions"],
            "graph_demotion_active": True,
        }
    return {
        "source": "gold",
        "goal": handoff.get("goal") or GRAPH_CONTROLLER_FALLBACK_GOAL,
        "next_actions": _effective_next_actions(gold, handoff),
        "graph_demotion_active": False,
    }


def build_status() -> dict[str, Any]:
    state = OttoState.load()
    state.ensure()
    paths = load_paths()
    launcher_state = LauncherStateStore()

    gold = read_json(paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
    checkpoint = read_json(state.checkpoints, default={}) or {}
    handoff = read_json(state.handoff_latest, default={}) or {}
    openclaw = build_openclaw_health()
    openclaw_gateway = probe_openclaw_gateway(timeout_seconds=1.5)
    morpheus_bridge = load_morpheus_openclaw_bridge(refresh=False)
    infra = build_infra_result().to_dict()
    docker = docker_compose_status(probe=True)
    runtime_snapshot = classify_runtime(runtime_pid_file(paths.repo_root))
    runtime = {"status": runtime_snapshot.status, "pid": runtime_snapshot.pid}
    sqlite = _sqlite_status(paths.sqlite_path)
    vector = _vector_status(paths, gold, infra)
    controller = _controller_surface(handoff, gold, paths)

    tasks_dir = paths.repo_root / "tasks" / "active"
    active_tasks = [p.name for p in sorted(tasks_dir.glob("*.md"))]

    status = {
        "repo_root": str(paths.repo_root),
        "vault_path": str(paths.vault_path) if paths.vault_path else None,
        "sqlite_path": str(paths.sqlite_path),
        "runtime": runtime,
        "sqlite": sqlite,
        "vector": vector,
        "training_ready": (gold.get("training_readiness") or {}).get("ready", False),
        "top_folders": (gold.get("top_folders") or [])[:5],
        "checkpoint": checkpoint,
        "handoff": handoff,
        "controller": controller,
        "goal": controller.get("goal"),
        "next_actions": controller.get("next_actions", []),
        "active_tasks": active_tasks,
        "infra": infra,
        "docker": docker,
        "openclaw": openclaw,
        "openclaw_gateway": openclaw_gateway,
        "morpheus_openclaw_bridge": morpheus_bridge,
        "openclaw_capabilities": openclaw.get("capabilities", {}),
        "openclaw_config_sync": openclaw.get("config_drift_free"),
        "anthropic_ready": openclaw.get("anthropic_ready"),
        "hf_fallback_ready": openclaw.get("hf_fallback_ready"),
        "launcher": {
            "current": read_json(launcher_state.current_path, default={}) or {},
            "last_action": read_json(launcher_state.last_action_path, default={}) or {},
            "mcp_last_run": read_json(launcher_state.mcp_last_run_path, default={}) or {},
        },
        "recent_logs": _tail(paths.logs_root / "app" / "otto.log", limit=12),
        "recent_events": _tail(paths.state_root / "run_journal" / "events.jsonl", limit=12),
        "model_matrix": model_matrix(),
        "schema": {
            "fingerprint": schema_fingerprint(),
            "registry": schema_registry(),
        },
    }
    controller_issues = _controller_issues(checkpoint, sqlite, openclaw)
    infra_issues = _infra_issues(runtime, sqlite, infra, vector, openclaw, openclaw_gateway)
    status["controller_issues"] = controller_issues
    status["infra_issues"] = infra_issues
    status["issues"] = controller_issues + infra_issues
    return status


def render_status_summary(status: dict[str, Any]) -> str:
    runtime = status.get("runtime", {}) or {}
    sqlite = status.get("sqlite", {}) or {}
    vector = status.get("vector", {}) or {}
    handoff = status.get("handoff", {}) or {}
    gateway = status.get("openclaw_gateway", {}) or {}
    controller = status.get("controller", {}) or {}
    infra = status.get("infra", {}) or {}
    morpheus_bridge = status.get("morpheus_openclaw_bridge", {}) or {}
    top_folder = ((status.get("top_folders") or [])[:1] or [{}])[0]
    lines = [
        "Obsidian-Otto Status",
        "",
        f"Runtime: {runtime.get('status', 'unknown')}" + (f" (PID {runtime.get('pid')})" if runtime.get("pid") else ""),
        f"Training ready: {status.get('training_ready')}",
        f"Active tasks: {', '.join(status.get('active_tasks', [])) if status.get('active_tasks') else 'none'}",
        f"SQLite notes: {sqlite.get('note_count', 'n/a')} @ {sqlite.get('path')}",
        f"Vector cache: {'enabled' if vector.get('enabled') else 'disabled'} - {vector.get('note') or 'n/a'}",
        f"OpenClaw gateway: {gateway.get('status', 'unknown')} - {gateway.get('reason', 'n/a')}",
        "Morpheus bridge: "
        f"{morpheus_bridge.get('bridge_mode', 'unavailable')} "
        f"(candidates={morpheus_bridge.get('candidate_count', 'n/a')}, ready={morpheus_bridge.get('ready_for_openclaw_dreaming', 'n/a')})",
    ]
    if gateway.get("checked_at"):
        lines.append(f"OpenClaw probe checked: {gateway.get('checked_at')}")
    if gateway.get("last_failure_at"):
        lines.append(f"OpenClaw last failed probe: {gateway.get('last_failure_at')}")
    docker_probe_status = str(infra.get("docker_probe_status") or "").strip()
    docker_probe_transport = str(infra.get("docker_probe_transport") or "").strip()
    if docker_probe_status and (docker_probe_status != "ok" or docker_probe_transport not in {"", "direct"}):
        probe_line = docker_probe_status
        if docker_probe_transport:
            probe_line = f"{probe_line} via {docker_probe_transport}"
        lines.append(f"Docker probe: {probe_line}")
    if top_folder.get("folder"):
        lines.append(
            f"Top folder risk: {top_folder.get('folder')} (risk={top_folder.get('risk_score')}, missing_fm={top_folder.get('missing_frontmatter')}, dupes={top_folder.get('duplicate_titles')})"
        )
    if handoff.get("graph_demotion_review_path"):
        lines.extend(
            [
                "",
                "Graph demotion",
                f"- mode: {handoff.get('graph_demotion_next_apply_mode')}",
                f"- hotspot: {handoff.get('graph_demotion_hotspot_family')}",
                f"- quality: {handoff.get('graph_demotion_quality_verdict')}",
                f"- next: {handoff.get('graph_demotion_next_action')}",
            ]
        )
    if controller.get("goal"):
        lines.extend(["", f"Controller goal: {controller.get('goal')}"])
    next_actions = (status.get("next_actions") or [])[:3]
    if next_actions:
        lines.extend(["", "Next actions"])
        lines.extend([f"- {item}" for item in next_actions])
    controller_issues = (status.get("controller_issues") or [])[:4]
    lines.extend(["", "Controller Issues"])
    lines.extend([f"- {item}" for item in controller_issues] or ["- none"])
    infra_issues = (status.get("infra_issues") or [])[:4]
    lines.extend(["", "Infra Issues"])
    lines.extend([f"- {item}" for item in infra_issues] or ["- none"])
    return "\n".join(lines) + "\n"
