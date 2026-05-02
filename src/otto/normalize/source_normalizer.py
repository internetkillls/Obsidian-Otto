from __future__ import annotations

from pathlib import Path
from typing import Any

from ..corridor import ensure_jsonl_row
from ..governance_utils import make_id, public_result, state_root
from .event_model import SilverEvent
from .privacy_classifier import classify_privacy
from .temporal_normalizer import normalize_observed_at


def silver_events_path() -> Path:
    return state_root() / "normalize" / "silver_events.jsonl"


def normalize_event_payload(
    *,
    source: str,
    text: str,
    kind: str = "idea_fragment",
    source_id: str = "vault_note",
    observed_at: str | None = None,
    language: str = "en",
    modality: str = "note",
    actor: str = "self",
    entities: list[str] | None = None,
    relations: list[dict[str, str]] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    observed, confidence = normalize_observed_at(observed_at)
    event = SilverEvent(
        event_id=make_id("evt"),
        state="SILVER_EVENT",
        source_id=source_id,
        source_ref=source,
        kind=kind,
        time={"observed_at": observed, "event_time_confidence": confidence},
        actor=actor,
        content_unit={"text": text, "language": language, "modality": modality},
        entities=list(entities or []),
        relations=list(relations or []),
        evidence_refs=[f"raw:{source}"],
        privacy=classify_privacy(source_id=source_id, text=text),
        qmd_index_allowed=False,
        vault_writeback_allowed=False,
    )
    payload = event.to_dict()
    if not dry_run:
        ensure_jsonl_row(silver_events_path(), payload)
    return public_result(True, dry_run=dry_run, silver_event=payload)


def normalize_event(source: str, *, dry_run: bool = True) -> dict[str, Any]:
    path = Path(source)
    text = path.read_text(encoding="utf-8") if path.exists() else source
    source_ref = str(path) if path.exists() else f"inline:{source[:32]}"
    return normalize_event_payload(source=source_ref, text=text, dry_run=dry_run)
