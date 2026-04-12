from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..config import load_paths
from ..logging_utils import get_logger
from ..state import read_json


def _sqlite_hits(conn: sqlite3.Connection, query: str, limit: int) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    rows = conn.execute(
        """
        SELECT path, title, frontmatter_text, body_excerpt
        FROM notes
        WHERE title LIKE ? OR frontmatter_text LIKE ? OR body_excerpt LIKE ? OR path LIKE ?
        ORDER BY mtime DESC
        LIMIT ?
        """,
        (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit),
    ).fetchall()
    return [{"path": row[0], "title": row[1], "frontmatter_text": row[2][:240], "body_excerpt": (row[3] or "")[:240]} for row in rows]


def _folder_hits(gold: dict[str, Any], query: str, limit: int) -> list[dict[str, Any]]:
    results = []
    q = query.lower().strip()
    for item in gold.get("top_folders", []):
        text = json.dumps(item, ensure_ascii=False).lower()
        if q in text:
            results.append(item)
    return results[:limit]


def retrieve(query: str, mode: str = "fast") -> dict[str, Any]:
    logger = get_logger("otto.retrieve")
    paths = load_paths()
    gold = read_json(paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
    handoff = read_json(paths.state_root / "handoff" / "latest.json", default={}) or {}

    note_hits: list[dict[str, Any]] = []
    if paths.sqlite_path.exists():
        conn = sqlite3.connect(paths.sqlite_path)
        note_hits = _sqlite_hits(conn, query, 8 if mode == "fast" else 20)
        conn.close()

    folder_hits = _folder_hits(gold, query, 4 if mode == "fast" else 8)
    state_hits = []
    handoff_text = json.dumps(handoff, ensure_ascii=False)
    if query.lower().strip() and query.lower().strip() in handoff_text.lower():
        state_hits.append({"source": "handoff", "snippet": handoff_text[:240]})

    enough_evidence = bool(note_hits or folder_hits or state_hits)
    needs_deepening = (mode == "fast") and not enough_evidence

    package = {
        "mode": mode,
        "query": query,
        "enough_evidence": enough_evidence,
        "needs_deepening": needs_deepening,
        "note_hits": note_hits,
        "folder_hits": folder_hits,
        "state_hits": state_hits,
        "training_readiness": (gold.get("training_readiness") or {}),
    }
    logger.info(f"[retrieve] mode={mode} note_hits={len(note_hits)} folder_hits={len(folder_hits)}")
    return package
