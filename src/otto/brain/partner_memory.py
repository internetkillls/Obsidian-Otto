from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from ..config import load_paths, load_retrieval_config
from ..logging_utils import get_logger
from ..state import now_iso

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None


def _partner_collection_name() -> str:
    return str(load_retrieval_config().get("vector", {}).get("partner_collection_name", "otto_partner"))


def _iso_to_epoch(value: str) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _stable_id(prefix: str, text: str, ts: str) -> str:
    digest = hashlib.sha256(f"{prefix}\n{ts}\n{text}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}::{digest}"


def _add_partner_document(text: str, metadata: dict[str, Any], *, id_prefix: str) -> dict[str, Any]:
    logger = get_logger("otto.partner_memory")
    if chromadb is None:
        return {"embedded": False, "reason": "chromadb not installed"}
    body = text.strip()
    if not body:
        return {"embedded": False, "reason": "empty text"}

    ts = str(metadata.get("ts") or now_iso())
    clean_metadata = {
        "path": str(metadata.get("path") or f"live/{id_prefix}"),
        "title": str(metadata.get("title") or id_prefix.replace("_", " ").title()),
        "signal_type": str(metadata.get("signal_type") or id_prefix),
        "mood_phase": str(metadata.get("mood_phase") or "unknown"),
        "audhd_state": str(metadata.get("audhd_state") or "unknown"),
        "ts": ts,
        "ts_epoch": float(metadata.get("ts_epoch") or _iso_to_epoch(ts)),
        "source": str(metadata.get("source") or "live_partner_memory"),
    }
    doc_id = str(metadata.get("id") or _stable_id(id_prefix, body, ts))

    try:
        client = chromadb.PersistentClient(path=str(load_paths().chroma_path))
        collection = client.get_or_create_collection(_partner_collection_name(), metadata={"hnsw:space": "cosine"})
        collection.upsert(documents=[body], ids=[doc_id], metadatas=[clean_metadata])
    except Exception as exc:
        logger.warning(f"[partner-memory] embed skipped: {exc}")
        return {"embedded": False, "reason": str(exc)}
    return {"embedded": True, "id": doc_id, "metadata": clean_metadata}


def embed_care_moment(text: str, **metadata: Any) -> dict[str, Any]:
    metadata.setdefault("signal_type", "care_moment")
    return _add_partner_document(text, metadata, id_prefix="care_moment")


def embed_mood_note(text: str, **metadata: Any) -> dict[str, Any]:
    metadata.setdefault("signal_type", "mood_note")
    return _add_partner_document(text, metadata, id_prefix="mood_note")


def record_care_moment(text: str, **metadata: Any) -> dict[str, Any]:
    return embed_care_moment(text, **metadata)


def record_interaction(text: str, mood_phase: str = "unknown", **metadata: Any) -> dict[str, Any]:
    metadata.setdefault("mood_phase", mood_phase)
    return embed_mood_note(text, **metadata)
