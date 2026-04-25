from __future__ import annotations

import time as time_module
from typing import Any

from .tooling.obsidian_scan import scan_vault
from .tooling.normalize import build_silver
from .tooling.gold_builder import build_gold
from .events import (
    Event,
    EventBus,
    EVENT_PIPELINE_BRONZE,
    EVENT_PIPELINE_SILVER,
    EVENT_PIPELINE_GOLD,
    EVENT_CACHE_RAW_READY,
    EVENT_CACHE_SQL_READY,
    EVENT_CACHE_VECTOR_READY,
    EVENT_DATASET_GOLD_READY,
    EVENT_TRAINING_REVIEW_REQUIRED,
)
from .logging_utils import get_logger
from .orchestration.graph_demotion import graph_controller_handoff_fields, load_graph_demotion_review
from .state import OttoState, now_iso, read_json, write_json


_pipeline_lock_file: Any = None


def _acquire_pipeline_lock(paths: Any) -> bool:
    global _pipeline_lock_file
    lock_path = paths.state_root / "pids" / "pipeline.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import os
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        _pipeline_lock_file = lock_path
        return True
    except FileExistsError:
        return False


def _release_pipeline_lock() -> None:
    global _pipeline_lock_file
    if _pipeline_lock_file and _pipeline_lock_file.exists():
        _pipeline_lock_file.unlink()
        _pipeline_lock_file = None


def _clean_artifacts(paths: Any) -> None:
    """Remove stale artifacts older than 7 days, preserving gold summaries."""
    now = time_module.time()
    max_age_seconds = 7 * 24 * 3600

    for directory in [paths.bronze_root, paths.artifacts_root / "reports"]:
        if not directory.exists():
            continue
        for entry in directory.iterdir():
            if entry.suffix not in (".json", ".md"):
                continue
            if entry.name in ("gold_summary.json", "gold_summary.md"):
                continue
            try:
                if now - entry.stat().st_mtime > max_age_seconds:
                    entry.unlink()
            except OSError:
                pass


def _dedupe_text(items: list[str], *, limit: int = 16) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        cleaned = str(item or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def run_pipeline(scope: str | None = None, full: bool = True) -> dict[str, Any]:
    logger = get_logger("otto.pipeline")
    state = OttoState.load()
    state.ensure()
    paths = state.paths
    bus = EventBus(paths)

    if not _acquire_pipeline_lock(paths):
        raise RuntimeError(
            "Another pipeline run is already in progress. "
            f"Lock file: {paths.state_root / 'pids' / 'pipeline.lock'}"
        )
    try:
        _clean_artifacts(paths)
        bronze = scan_vault(scope=scope)
        bus.publish(Event(type=EVENT_PIPELINE_BRONZE, source="pipeline", payload={"scope": scope, "note_count": bronze["note_count"]}))
        bus.publish(Event(type=EVENT_CACHE_RAW_READY, source="pipeline", payload={"scope": scope, "note_count": bronze["note_count"]}))

        silver = build_silver(bronze)
        bus.publish(Event(type=EVENT_PIPELINE_SILVER, source="pipeline", payload=silver))
        bus.publish(Event(type=EVENT_CACHE_SQL_READY, source="pipeline", payload={"db_path": silver["db_path"], "note_count": silver["note_count"]}))

        gold = build_gold()
        bus.publish(Event(type=EVENT_PIPELINE_GOLD, source="pipeline", payload={"top_folders": len(gold.get("top_folders", []))}))
        bus.publish(Event(type=EVENT_CACHE_VECTOR_READY, source="pipeline", payload=gold.get("vector_cache", {})))
        bus.publish(Event(type=EVENT_DATASET_GOLD_READY, source="pipeline", payload={"training_readiness": gold.get("training_readiness", {})}))
        bus.publish(Event(type=EVENT_TRAINING_REVIEW_REQUIRED, source="pipeline", payload={"next_actions": gold.get("next_actions", [])}))

        checkpoint = {
            "ts": now_iso(),
            "scope": scope or ".",
            "bronze_notes": bronze["note_count"],
            "silver_db": silver["db_path"],
            "gold_top_folders": len(gold.get("top_folders", [])),
            "training_ready": (gold.get("training_readiness") or {}).get("ready", False),
        }
        write_json(state.checkpoints, checkpoint)

        existing_handoff = read_json(state.handoff_latest, default={}) or {}
        graph_review = load_graph_demotion_review(paths)
        controller_fields = graph_controller_handoff_fields(
            graph_review,
            handoff=existing_handoff,
            fallback_actions=list(gold.get("next_actions", []) or []),
        )
        handoff = {
            **existing_handoff,
            **controller_fields,
            "last_pipeline_scope": scope or ".",
            "status": "ready",
            "updated_at": now_iso(),
            "artifacts": _dedupe_text(
                list(existing_handoff.get("artifacts", []) or [])
                + [
                    "artifacts/reports/bronze_summary.json",
                    "artifacts/reports/silver_summary.json",
                    "artifacts/summaries/gold_summary.json",
                    "artifacts/reports/gold_summary.md",
                ]
                + ([str(graph_review.get("source_path"))] if graph_review else [])
            ),
        }
        write_json(state.handoff_latest, handoff)
        logger.info("[pipeline] complete")
        return {"bronze": bronze, "silver": silver, "gold": gold, "checkpoint": checkpoint}
    finally:
        _release_pipeline_lock()
