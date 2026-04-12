from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_paths
from ..events import Event, EventBus, EVENT_DREAM
from ..logging_utils import get_logger
from ..models import choose_model
from ..state import OttoState, now_iso, read_json, write_json
from .brain import run_brain_self_model


def _tail(path: Path, limit: int = 20) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def run_dream_once() -> dict[str, Any]:
    logger = get_logger("otto.dream")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()
    model = choose_model("dream_consolidation")
    handoff = read_json(state.handoff_latest, default={}) or {}
    checkpoint = read_json(state.checkpoints, default={}) or {}

    log_tail = _tail(paths.logs_root / "app" / "otto.log", limit=12)
    event_tail = _tail(paths.state_root / "run_journal" / "events.jsonl", limit=12)

    stable_facts = []
    if checkpoint:
        stable_facts.append(f"Last pipeline scope: {checkpoint.get('scope', '.')}")
        stable_facts.append(f"Training ready: {checkpoint.get('training_ready', False)}")
    if handoff.get("goal"):
        stable_facts.append(f"Goal: {handoff['goal']}")

    unresolved = handoff.get("next_actions") or ["No explicit next action captured yet"]
    repeated_failures = []
    if not checkpoint:
        repeated_failures.append("Pipeline has not yet produced a checkpoint")

    report_lines = [
        "# Dream Summary",
        "",
        f"- timestamp: {now_iso()}",
        f"- model_hint: {model.model}",
        "",
        "## Stable facts",
    ]
    report_lines.extend([f"- {item}" for item in stable_facts] or ["- none"])
    report_lines.extend(["", "## Unresolved"])
    report_lines.extend([f"- {item}" for item in unresolved] or ["- none"])
    report_lines.extend(["", "## Repeated operational failures"])
    report_lines.extend([f"- {item}" for item in repeated_failures] or ["- none"])
    report_lines.extend(["", "## Recent log tail"])
    report_lines.extend([f"- {item}" for item in log_tail] or ["- no logs yet"])
    report_lines.extend(["", "## Recent event tail"])
    report_lines.extend([f"- {item}" for item in event_tail] or ["- no events yet"])

    report_path = paths.artifacts_root / "reports" / "dream_summary.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    dream_state = {
        "ts": now_iso(),
        "model_hint": model.model,
        "stable_fact_count": len(stable_facts),
        "unresolved_count": len(unresolved),
    }
    write_json(state.dream, dream_state)
    EventBus().publish(Event(type=EVENT_DREAM, source="dream", payload=dream_state))
    sm_result = run_brain_self_model()
    logger.info("[dream] summary written")
    return dream_state
