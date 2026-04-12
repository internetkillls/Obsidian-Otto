from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..docker_utils import docker_compose_status
from ..models import model_matrix
from ..state import OttoState, read_json


def _tail(path: Path, limit: int = 10) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def build_status() -> dict[str, Any]:
    state = OttoState.load()
    state.ensure()
    paths = load_paths()

    gold = read_json(paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
    checkpoint = read_json(state.checkpoints, default={}) or {}
    handoff = read_json(state.handoff_latest, default={}) or {}

    tasks_dir = paths.repo_root / "tasks" / "active"
    active_tasks = [p.name for p in sorted(tasks_dir.glob("*.md"))]

    status = {
        "repo_root": str(paths.repo_root),
        "vault_path": str(paths.vault_path) if paths.vault_path else None,
        "sqlite_path": str(paths.sqlite_path),
        "training_ready": (gold.get("training_readiness") or {}).get("ready", False),
        "top_folders": (gold.get("top_folders") or [])[:5],
        "checkpoint": checkpoint,
        "handoff": handoff,
        "active_tasks": active_tasks,
        "docker": docker_compose_status(),
        "recent_logs": _tail(paths.logs_root / "app" / "otto.log", limit=12),
        "recent_events": _tail(paths.state_root / "run_journal" / "events.jsonl", limit=12),
        "model_matrix": model_matrix(),
    }
    return status
