from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

    chunk_size = int(cfg.get("vector", {}).get("chunk_size", 900))
    chunk_overlap = int(cfg.get("vector", {}).get("chunk_overlap", 120))
    collection_name = str(cfg.get("vector", {}).get("collection_name", "otto_gold"))

    client = chromadb.PersistentClient(path=str(paths.chroma_path))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.get_or_create_collection(collection_name)

    splitter = None
    if RecursiveCharacterTextSplitter is not None:
        splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    docs, ids, metas = [], [], []
    count = 0
    for note in notes:
        text = note.get("render_text", "") or note.get("frontmatter_text", "") or note.get("title", "")
        text = text.strip()
        if not text:
            continue
        chunks = splitter.split_text(text) if splitter else [text[:chunk_size]]
        for idx, chunk in enumerate(chunks):
            docs.append(chunk)
            ids.append(f"{note['path']}::{idx}")
            metas.append({"path": note["path"], "title": note["title"]})
            count += 1

    if ids:
        try:
            collection.delete(where={})
        except Exception:
            pass
        collection.add(documents=docs, ids=ids, metadatas=metas)

    summary = {"enabled": True, "note": "vector cache built", "chunk_count": count, "collection": collection_name}
    write_json(paths.artifacts_root / "reports" / "vector_summary.json", summary)
    logger.info(f"[vector] chunks={count}")
    return VectorBuildResult(enabled=True, note="vector cache built", chunk_count=count)
