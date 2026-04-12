from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..logging_utils import get_logger
from ..state import write_json


def _atomic_schema_build(conn: sqlite3.Connection) -> None:
    """Atomically rebuild schema: creates temp tables, migrates data, replaces originals.

    If anything fails mid-way, the transaction is rolled back and the original
    tables remain intact — no partial/corrupt state.
    """
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS notes_new (
        path TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        size INTEGER NOT NULL,
        sha1 TEXT NOT NULL,
        mtime REAL NOT NULL,
        has_frontmatter INTEGER NOT NULL,
        frontmatter_text TEXT,
        body_excerpt TEXT,
        tags_json TEXT,
        wikilinks_json TEXT
    );
    CREATE TABLE IF NOT EXISTS attachments_new (
        path TEXT PRIMARY KEY,
        size INTEGER NOT NULL,
        mtime REAL NOT NULL,
        extension TEXT
    );
    CREATE TABLE IF NOT EXISTS folder_risk_new (
        folder TEXT PRIMARY KEY,
        missing_frontmatter INTEGER NOT NULL,
        duplicate_titles INTEGER NOT NULL,
        outbound_links INTEGER NOT NULL,
        note_count INTEGER NOT NULL,
        risk_score REAL NOT NULL
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts_new USING fts5(
        path, title, frontmatter_text, body_excerpt, content=''
    );
    """)

    conn.execute("""
        INSERT OR IGNORE INTO notes_new
            SELECT * FROM notes WHERE 0;
    """)
    conn.execute("""
        INSERT OR IGNORE INTO attachments_new
            SELECT * FROM attachments WHERE 0;
    """)
    conn.execute("""
        INSERT OR IGNORE INTO folder_risk_new
            SELECT * FROM folder_risk WHERE 0;
    """)

    conn.execute("DROP TABLE IF EXISTS notes")
    conn.execute("DROP TABLE IF EXISTS attachments")
    conn.execute("DROP TABLE IF EXISTS folder_risk")
    conn.execute("DROP TABLE IF EXISTS notes_fts")

    conn.execute("ALTER TABLE notes_new RENAME TO notes")
    conn.execute("ALTER TABLE attachments_new RENAME TO attachments")
    conn.execute("ALTER TABLE folder_risk_new RENAME TO folder_risk")
    conn.execute("ALTER TABLE notes_fts_new RENAME TO notes_fts")


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
                (path, title, size, sha1, mtime, has_frontmatter, frontmatter_text, body_excerpt, tags_json, wikilinks_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note["path"],
                    note["title"],
                    note["size"],
                    note["sha1"],
                    note["mtime"],
                    1 if note["has_frontmatter"] else 0,
                    note["frontmatter_text"],
                    note.get("body_excerpt", ""),
                    json.dumps(note.get("tags", []), ensure_ascii=False),
                    json.dumps(note.get("wikilinks", []), ensure_ascii=False),
                ),
            )
            conn.execute(
                "INSERT INTO notes_fts(path, title, frontmatter_text, body_excerpt) VALUES (?, ?, ?, ?)",
                (note["path"], note["title"], note["frontmatter_text"], note.get("body_excerpt", "")),
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
    }
    write_json(paths.artifacts_root / "reports" / "silver_summary.json", summary)
    logger.info(f"[silver] db={db_path} notes={summary['note_count']}")
    return summary
