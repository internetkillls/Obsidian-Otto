from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..schema_registry import schema_fingerprint
from ..logging_utils import get_logger
from ..state import write_json


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _atomic_schema_build(conn: sqlite3.Connection) -> None:
    """Atomically rebuild the Silver schema from scratch.

    Silver is derived data produced from Bronze on every pipeline run, so we do
    not need best-effort migration from older table layouts. Rebuilding cleanly
    is safer than attempting to copy from legacy schemas that may have missing
    columns.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
    DROP TABLE IF EXISTS notes;
    DROP TABLE IF EXISTS attachments;
    DROP TABLE IF EXISTS folder_risk;
    DROP TABLE IF EXISTS notes_fts;

    CREATE TABLE notes (
        path TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        size INTEGER NOT NULL,
        sha1 TEXT NOT NULL,
        mtime REAL NOT NULL,
        has_frontmatter INTEGER NOT NULL,
        frontmatter_text TEXT,
        aliases_json TEXT,
        body_excerpt TEXT,
        tags_json TEXT,
        wikilinks_json TEXT,
        scarcity TEXT,
        necessity TEXT,
        artificial TEXT,
        orientation TEXT,
        allocation TEXT,
        cluster_membership TEXT
    );
    CREATE TABLE attachments (
        path TEXT PRIMARY KEY,
        size INTEGER NOT NULL,
        mtime REAL NOT NULL,
        extension TEXT
    );
    CREATE TABLE folder_risk (
        folder TEXT PRIMARY KEY,
        missing_frontmatter INTEGER NOT NULL,
        duplicate_titles INTEGER NOT NULL,
        outbound_links INTEGER NOT NULL,
        note_count INTEGER NOT NULL,
        risk_score REAL NOT NULL
    );
    CREATE VIRTUAL TABLE notes_fts USING fts5(
        path, title, aliases_text, frontmatter_text, body_excerpt
    );
    """)


def build_silver(bronze_payload: dict[str, Any]) -> dict[str, Any]:
    logger = get_logger("otto.silver")
    paths = load_paths()
    db_path = paths.sqlite_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        _atomic_schema_build(conn)

        folder_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"missing_frontmatter": 0, "titles": [], "outbound_links": 0, "note_count": 0}
        )

        for note in bronze_payload.get("notes", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO notes
                (path, title, size, sha1, mtime, has_frontmatter, frontmatter_text, aliases_json, body_excerpt, tags_json, wikilinks_json, scarcity, necessity, artificial, orientation, allocation, cluster_membership)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note["path"],
                    note["title"],
                    note["size"],
                    note["sha1"],
                    note["mtime"],
                    1 if note["has_frontmatter"] else 0,
                    note["frontmatter_text"],
                    json.dumps(note.get("aliases", []), ensure_ascii=False),
                    note.get("body_excerpt", ""),
                    json.dumps(note.get("tags", []), ensure_ascii=False),
                    json.dumps(note.get("wikilinks", []), ensure_ascii=False),
                    json.dumps(note.get("scarcity", []), ensure_ascii=False),
                    note.get("necessity"),
                    note.get("artificial"),
                    note.get("orientation"),
                    note.get("allocation"),
                    json.dumps(note.get("cluster_membership", []), ensure_ascii=False),
                ),
            )
            conn.execute(
                "INSERT INTO notes_fts(path, title, aliases_text, frontmatter_text, body_excerpt) VALUES (?, ?, ?, ?, ?)",
                (
                    note["path"],
                    note["title"],
                    " ".join(note.get("aliases", [])),
                    note["frontmatter_text"],
                    note.get("body_excerpt", ""),
                ),
            )

            folder = str(Path(note["path"]).parent)
            stat = folder_stats[folder]
            stat["note_count"] += 1
            stat["outbound_links"] += len(note.get("wikilinks", []))
            stat["titles"].append(note["title"].strip().lower())
            if not note.get("has_frontmatter"):
                stat["missing_frontmatter"] += 1

        for attachment in bronze_payload.get("attachments", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO attachments(path, size, mtime, extension)
                VALUES (?, ?, ?, ?)
                """,
                (
                    attachment["path"],
                    attachment["size"],
                    attachment["mtime"],
                    attachment.get("extension"),
                ),
            )

        risk_rows = []
        for folder, stat in sorted(folder_stats.items()):
            duplicate_titles = sum(count - 1 for count in Counter(stat["titles"]).values() if count > 1)
            note_count = stat["note_count"]
            risk_score = round(
                (stat["missing_frontmatter"] * 2.0)
                + (duplicate_titles * 3.0)
                + ((stat["outbound_links"] / max(note_count, 1)) * 0.5),
                2,
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO folder_risk(folder, missing_frontmatter, duplicate_titles, outbound_links, note_count, risk_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (folder, stat["missing_frontmatter"], duplicate_titles, stat["outbound_links"], note_count, risk_score),
            )
            risk_rows.append(
                {
                    "folder": folder,
                    "missing_frontmatter": stat["missing_frontmatter"],
                    "duplicate_titles": duplicate_titles,
                    "outbound_links": stat["outbound_links"],
                    "note_count": note_count,
                    "risk_score": risk_score,
                }
            )

        conn.commit()
    finally:
        conn.close()

    summary = {
        "db_path": str(db_path),
        "note_count": len(bronze_payload.get("notes", [])),
        "attachment_count": len(bronze_payload.get("attachments", [])),
        "top_risky_folders": sorted(risk_rows, key=lambda x: x["risk_score"], reverse=True)[:10],
        "schema_fingerprint": schema_fingerprint(),
    }
    write_json(paths.artifacts_root / "reports" / "silver_summary.json", summary)
    logger.info(f"[silver] db={db_path} notes={summary['note_count']}")
    return summary
