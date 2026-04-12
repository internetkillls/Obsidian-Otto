from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import load_kairos_config, load_paths
from ..events import Event, EventBus, EVENT_KAIROS
from ..logging_utils import append_jsonl, get_logger
from ..models import choose_model
from ..state import OttoState, now_iso, read_json, write_json


def _latest_mtime(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_mtime
    mtimes = [p.stat().st_mtime for p in path.rglob("*") if p.is_file()]
    return max(mtimes, default=0.0)


def run_kairos_once() -> dict[str, Any]:
    logger = get_logger("otto.kairos")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()
    cfg = load_kairos_config().get("kairos", {})
    model = choose_model("kairos_daily")

    gold = read_json(paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
    checkpoint = read_json(state.checkpoints, default={}) or {}
    events_path = paths.state_root / "run_journal" / "events.jsonl"

    top_folders = (gold.get("top_folders") or [])[:3]
    strategy_lines = [
        "# KAIROS Daily Strategy",
        "",
        f"- timestamp: {now_iso()}",
        f"- model_hint: {model.model}",
        f"- checkpoint_scope: {checkpoint.get('scope', 'n/a')}",
        f"- recent_events_present: {events_path.exists()}",
        "",
        "## Top folder risks",
    ]
    if top_folders:
        for item in top_folders:
            strategy_lines.append(
                f"- {item['folder']} risk={item['risk_score']} missing_frontmatter={item['missing_frontmatter']} duplicates={item['duplicate_titles']}"
            )
    else:
        strategy_lines.append("- no Gold data yet")

    next_actions = []
    for item in top_folders:
        next_actions.append(f"Repair metadata in {item['folder']}")
    if not next_actions:
        next_actions.append("Run the first pipeline or choose a vault")
    next_actions.append("Prefer fast retrieval first; escalate only when evidence is weak")
    next_actions.append("Keep training export gated behind reviewed Gold")

    strategy_lines.extend(["", "## Next actions"])
    strategy_lines.extend([f"- {line}" for line in next_actions])

    report_path = paths.artifacts_root / "reports" / "kairos_daily_strategy.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(strategy_lines) + "\n", encoding="utf-8")

    record = {
        "ts": now_iso(),
        "model_hint": model.model,
        "top_folder_count": len(top_folders),
        "next_actions": next_actions,
    }
    append_jsonl(state.kairos, record)
    write_json(state.handoff_latest, {
        **(read_json(state.handoff_latest, default={}) or {}),
        "updated_at": now_iso(),
        "status": "ready",
        "goal": "Maintain a stable Obsidian-Otto retrieval core",
        "artifacts": [
            "artifacts/summaries/gold_summary.json",
            "artifacts/reports/kairos_daily_strategy.md",
            "artifacts/reports/dream_summary.md",
        ],
        "next_actions": next_actions,
    })

    EventBus().publish(Event(type=EVENT_KAIROS, source="kairos", payload=record))
    logger.info("[kairos] heartbeat written")
    return record
