from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..events import Event, EventBus
from ..logging_utils import append_jsonl
from ..orchestration.dream import run_dream_once
from ..orchestration.kairos import run_kairos_once
from ..state import OttoState, now_iso, read_json, write_json
from .janitor import discover_targets, run_janitor
from .repair import run_repair


def _latest_mtime(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_mtime
    return max((p.stat().st_mtime for p in path.rglob("*") if p.is_file()), default=0.0)


def _loop_state_path(paths: Any) -> Path:
    return paths.state_root / "openclaw" / "loop_state.json"


def _intake(paths: Any) -> dict[str, Any]:
    state = OttoState.load()
    handoff = read_json(state.handoff_latest, default={}) or {}
    checkpoint = read_json(state.checkpoints, default={}) or {}
    gold = read_json(paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
    dream = read_json(paths.state_root / "dream" / "dream_state.json", default={}) or {}
    sync_status = read_json(paths.state_root / "openclaw" / "sync_status.json", default={}) or {}
    tasks = sorted(p.name for p in (paths.repo_root / "tasks" / "active").glob("*.md"))
    delta_sources = {
        "handoff": _latest_mtime(state.handoff_latest),
        "checkpoint": _latest_mtime(state.checkpoints),
        "gold": _latest_mtime(paths.artifacts_root / "summaries" / "gold_summary.json"),
        "bronze": _latest_mtime(paths.repo_root / "data" / "bronze" / "bronze_manifest.json"),
        "dream": _latest_mtime(paths.artifacts_root / "reports" / "dream_summary.md"),
    }
    fingerprint = hashlib.sha256(
        "|".join(f"{key}:{value}" for key, value in sorted(delta_sources.items())).encode("utf-8")
    ).hexdigest()
    return {
        "tasks": tasks,
        "handoff": handoff,
        "checkpoint": checkpoint,
        "gold": gold,
        "dream": dream,
        "sync_status": sync_status,
        "delta_sources": delta_sources,
        "fingerprint": fingerprint,
        "unresolved_count": len(handoff.get("next_actions") or []),
        "janitor_candidates": len(discover_targets(root=paths.repo_root)),
    }


def _decision(mode: str, intake: dict[str, Any], last_loop: dict[str, Any]) -> list[str]:
    decisions: list[str] = []
    fingerprint_changed = intake["fingerprint"] != last_loop.get("fingerprint")
    needs_sync = not intake["sync_status"].get("openclaw_config_sync")
    if mode == "heartbeat":
        decisions.append("kairos")
        decisions.append("morpheus")
        if needs_sync:
            decisions.append("repair")
        if intake["janitor_candidates"] >= 5:
            decisions.append("janitor")
        return decisions
    if mode == "kairos":
        return ["repair", "kairos"] if needs_sync else ["kairos"]
    if mode == "morpheus":
        return ["repair", "morpheus"] if needs_sync else ["morpheus"]
    if fingerprint_changed and intake["unresolved_count"] > 0:
        decisions.extend(["kairos", "morpheus"])
    elif needs_sync:
        decisions.append("repair")
    return decisions


def run_loop(*, root: Path, runtime_env: dict[str, str], mode: str = "pulse") -> dict[str, Any]:
    paths = load_paths()
    state = OttoState.load()
    intake = _intake(paths)
    last_loop = read_json(_loop_state_path(paths), default={}) or {}
    decisions = _decision(mode, intake, last_loop)

    executed: list[dict[str, Any]] = []
    if "repair" in decisions:
        executed.append({"action": "repair", "result": run_repair(root=root, runtime_env=runtime_env, dry_run=False)})
    if "kairos" in decisions:
        executed.append({"action": "kairos", "result": run_kairos_once()})
    if "morpheus" in decisions:
        executed.append({"action": "morpheus", "result": run_dream_once()})
    if "janitor" in decisions:
        executed.append({"action": "janitor", "result": run_janitor(root=root, dry_run=False)})

    cycle_id = f"loop-{mode}-{now_iso()}"
    payload = {
        "ts": now_iso(),
        "cycle_id": cycle_id,
        "mode": mode,
        "intake": {
            "tasks": intake["tasks"],
            "unresolved_count": intake["unresolved_count"],
            "fingerprint": intake["fingerprint"],
            "delta_sources": intake["delta_sources"],
        },
        "decisions": decisions,
        "executed": [item["action"] for item in executed],
    }
    append_jsonl(paths.state_root / "run_journal" / "events.jsonl", {
        "ts": payload["ts"],
        "cycle_id": cycle_id,
        "phase": "ABC",
        "source": "otto.loop",
        "mode": mode,
        "decisions": decisions,
        "engines_run": [item["action"] for item in executed],
        "next_action": (intake["handoff"].get("next_actions") or ["none"])[0],
    })

    merged_handoff = {
        **(intake["handoff"] or {}),
        "updated_at": now_iso(),
        "last_loop_mode": mode,
        "last_loop_decisions": decisions,
    }
    write_json(state.handoff_latest, merged_handoff)
    write_json(_loop_state_path(paths), {
        "ts": payload["ts"],
        "mode": mode,
        "fingerprint": intake["fingerprint"],
        "decisions": decisions,
    })
    EventBus().publish(Event(type="otto.loop", source="loop", payload=payload))
    return {
        "mode": mode,
        "intake": intake,
        "decisions": decisions,
        "executed": executed,
    }
