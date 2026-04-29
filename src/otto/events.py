from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from .config import load_paths
from .logging_utils import append_jsonl
from .state import now_iso


def _pg_write(event_dict: dict[str, Any]) -> None:
    try:
        from .db import write_event as pg_write_event
        pg_write_event(event_dict)
    except Exception:
        pass  # Postgres is best-effort; JSONL is always authoritative


@dataclass
class Event:
    type: str
    source: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: uuid4().hex)
    ts: str = field(default_factory=now_iso)


class EventBus:
    def __init__(self, paths: Any | None = None) -> None:
        self._handlers: dict[str, list[Callable[[Event], None]]] = {}
        self._paths = paths

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: Event) -> None:
        if self._paths is None:
            self._paths = load_paths()
        # Always write JSONL (authoritative log)
        append_jsonl(self._paths.state_root / "run_journal" / "events.jsonl", event.__dict__)
        append_jsonl(self._paths.logs_root / "app" / "events.jsonl", event.__dict__)
        # Best-effort Postgres write (structured queries)
        _pg_write(event.__dict__)
        for handler in self._handlers.get(event.type, []):
            handler(event)


EVENT_PIPELINE_BRONZE = "pipeline.bronze.built"
EVENT_PIPELINE_SILVER = "pipeline.silver.built"
EVENT_PIPELINE_GOLD = "pipeline.gold.built"
EVENT_CACHE_RAW_READY = "cache.raw.ready"
EVENT_CACHE_SQL_READY = "cache.sql.ready"
EVENT_CACHE_VECTOR_READY = "cache.vector.ready"
EVENT_DATASET_GOLD_READY = "dataset.gold.ready"
EVENT_TRAINING_REVIEW_REQUIRED = "training.review.required"
EVENT_RETRIEVAL_FAST = "retrieval.fast"
EVENT_RETRIEVAL_DEEP = "retrieval.deep"
EVENT_RETRIEVAL_MISS = "retrieval.miss"
EVENT_KAIROS = "kairos.heartbeat"
EVENT_KAIROS_GOLD_SCORED = "kairos.gold.scored"
EVENT_KAIROS_CONTRADICTION = "kairos.contradiction"
EVENT_COUNCIL_DEBATE = "council.debate"
EVENT_DREAM = "dream.run"
EVENT_MORPHEUS_ENRICHED = "morpheus.enriched"
EVENT_MORPHEUS_MEMORY_CANDIDATES = "morpheus.memory_candidates.updated"
EVENT_BRAIN_SELF_MODEL_UPDATED = "brain.self_model.updated"
EVENT_BRAIN_PREDICTION_GENERATED = "brain.prediction.generated"
EVENT_BRAIN_RITUAL_COMPLETED = "brain.ritual.completed"
EVENT_METADATA_ENRICHMENT = "metadata.enrichment.completed"
EVENT_OPENCLAW_CONFIG_SYNCED = "openclaw.config.synced"
EVENT_OPENCLAW_RESEARCH = "openclaw.research.executed"
EVENT_OPENCLAW_FALLBACK_TRIGGERED = "openclaw.fallback.triggered"
EVENT_QMD_INDEX_REFRESHED = "openclaw.qmd.index.refreshed"
EVENT_META_GOV_ALERT = "meta_gov.alert"
