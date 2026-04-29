from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import yaml

from ..config import load_paths, load_retrieval_config
from ..logging_utils import get_logger
from ..state import write_json

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover
    RecursiveCharacterTextSplitter = None


@dataclass
class VectorBuildResult:
    enabled: bool
    note: str
    chunk_count: int = 0
    collections: list[str] | None = None


_PARTNER_HINTS = (
    "partner",
    "care",
    "wellness",
    "check-in",
    "checkin",
    "follow-up",
    "followup",
    "mood",
    "fatigue",
    "energy",
    "recovery",
    "shutdown",
    "audhd",
    "bd",
    "relationship",
    "relational",
    "emotion",
    "support",
)

_CARE_HINTS = ("care", "support", "check-in", "checkin", "follow-up", "followup", "relationship", "relational")
_MOOD_HINTS = ("mood", "fatigue", "energy", "recovery", "shutdown", "emotion", "wellness", "audhd", "bd")


def _is_partner_memory_note(note: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(note.get(field, "") or "")
        for field in ("path", "title", "frontmatter_text", "render_text")
    ).lower()
    return any(hint in haystack for hint in _PARTNER_HINTS)


def _frontmatter_map(note: dict[str, Any]) -> dict[str, Any]:
    raw = str(note.get("frontmatter_text", "") or "").strip()
    if not raw:
        return {}
    try:
        payload = yaml.safe_load(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_string(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (list, tuple, set)):
            for item in value:
                if isinstance(item, datetime):
                    return item.isoformat()
                text = str(item or "").strip()
                if text:
                    return text
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _iso_to_epoch(value: str) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _signal_type_for_note(note: dict[str, Any]) -> str:
    frontmatter = _frontmatter_map(note)
    explicit = _first_string(frontmatter.get("signal_type"), note.get("signal_type"))
    if explicit:
        return explicit
    haystack = " ".join(
        str(note.get(field, "") or "")
        for field in ("path", "title", "frontmatter_text", "render_text")
    ).lower()
    if any(hint in haystack for hint in _CARE_HINTS):
        return "care_moment"
    if any(hint in haystack for hint in _MOOD_HINTS):
        return "mood_note"
    return "partner_memory"


def _partner_metadata_for_note(note: dict[str, Any]) -> dict[str, Any]:
    frontmatter = _frontmatter_map(note)
    ts = _first_string(
        frontmatter.get("ts"),
        frontmatter.get("date"),
        frontmatter.get("created"),
        frontmatter.get("updated"),
        note.get("ts"),
    )
    return {
        "path": str(note.get("path", "")),
        "title": str(note.get("title", note.get("path", ""))),
        "signal_type": _signal_type_for_note(note),
        "mood_phase": _first_string(frontmatter.get("mood_phase"), note.get("mood_phase"), default="unknown"),
        "audhd_state": _first_string(frontmatter.get("audhd_state"), note.get("audhd_state"), default="unknown"),
        "ts": ts,
        "ts_epoch": _iso_to_epoch(ts),
        "source": _first_string(frontmatter.get("source"), note.get("source"), note.get("path"), default="vector_build"),
    }


def _collection_client():
    return chromadb.PersistentClient(path=str(load_paths().chroma_path))


def _build_collection(client, name: str, docs: list[str], ids: list[str], metas: list[dict[str, Any]]) -> None:
    try:
        client.delete_collection(name)
    except Exception:
        pass
    collection = client.get_or_create_collection(name)
    try:
        collection.delete(where={})
    except Exception:
        pass
    if ids:
        collection.add(documents=docs, ids=ids, metadatas=metas)


def build_vector_cache(notes: list[dict[str, Any]]) -> VectorBuildResult:
    logger = get_logger("otto.vector")
    paths = load_paths()
    cfg = load_retrieval_config()
    if chromadb is None:
        note = "chromadb not installed; vector cache skipped"
        write_json(paths.artifacts_root / "reports" / "vector_summary.json", {"enabled": False, "note": note})
        logger.info(f"[vector] {note}")
        return VectorBuildResult(enabled=False, note=note)

    if not notes:
        note = "no notes available for vector cache"
        write_json(paths.artifacts_root / "reports" / "vector_summary.json", {"enabled": False, "note": note})
        logger.info(f"[vector] {note}")
        return VectorBuildResult(enabled=False, note=note)

    vector_cfg = cfg.get("vector", {})
    chunk_size = int(vector_cfg.get("chunk_size", 900))
    chunk_overlap = int(vector_cfg.get("chunk_overlap", 120))
    collection_name = str(vector_cfg.get("collection_name", "otto_gold"))
    partner_collection_name = str(vector_cfg.get("partner_collection_name", "otto_partner"))

    client = chromadb.PersistentClient(path=str(paths.chroma_path))

    splitter = None
    if RecursiveCharacterTextSplitter is not None:
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    gold_docs: list[str] = []
    gold_ids: list[str] = []
    gold_metas: list[dict[str, Any]] = []
    partner_docs: list[str] = []
    partner_ids: list[str] = []
    partner_metas: list[dict[str, Any]] = []
    count = 0
    for note in notes:
        text = note.get("render_text", "") or note.get("frontmatter_text", "") or note.get("title", "")
        text = text.strip()
        if not text:
            continue
        chunks = splitter.split_text(text) if splitter else [text[:chunk_size]]
        for idx, chunk in enumerate(chunks):
            payload_meta = {"path": note["path"], "title": note["title"]}
            gold_docs.append(chunk)
            gold_ids.append(f"{note['path']}::{idx}")
            gold_metas.append(payload_meta)
            if _is_partner_memory_note(note):
                partner_docs.append(chunk)
                partner_ids.append(f"{note['path']}::{idx}")
                partner_metas.append(_partner_metadata_for_note(note))
            count += 1

    _build_collection(client, collection_name, gold_docs, gold_ids, gold_metas)
    _build_collection(client, partner_collection_name, partner_docs, partner_ids, partner_metas)

    summary = {
        "enabled": True,
        "note": "vector cache built",
        "chunk_count": count,
        "collections": {
            "gold": collection_name,
            "partner": partner_collection_name,
        },
    }
    write_json(paths.artifacts_root / "reports" / "vector_summary.json", summary)
    logger.info(f"[vector] chunks={count} collections={collection_name},{partner_collection_name}")
    return VectorBuildResult(enabled=True, note="vector cache built", chunk_count=count, collections=[collection_name, partner_collection_name])
