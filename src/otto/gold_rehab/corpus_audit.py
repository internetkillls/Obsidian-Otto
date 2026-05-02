from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..corridor import ensure_last, rewrite_jsonl
from ..governance_utils import public_result, state_root
from .frontmatter_patch_plan import build_frontmatter_patch_candidate
from .promotion_ladder import ladder_state
from .readiness_score import build_note_readiness
from .semantic_enrichment import build_semantic_enrichment_candidate


def corpus_audit_path() -> Path:
    return state_root() / "gold_rehab" / "corpus_audit.json"


def note_readiness_path() -> Path:
    return state_root() / "gold_rehab" / "note_readiness.jsonl"


def metadata_repair_plan_path() -> Path:
    return state_root() / "gold_rehab" / "metadata_repair_plan.jsonl"


def gold_readiness_scores_path() -> Path:
    return state_root() / "gold_rehab" / "gold_readiness_scores.jsonl"


def promotion_ladder_path() -> Path:
    return state_root() / "gold_rehab" / "promotion_ladder.jsonl"


def _load_notes(limit: int | None = None) -> list[dict[str, Any]]:
    paths = load_paths()
    if not paths.sqlite_path.exists():
        return []
    conn = sqlite3.connect(paths.sqlite_path)
    try:
        query = """
            SELECT path, title, sha1, has_frontmatter, frontmatter_text, body_excerpt, tags_json, wikilinks_json
            FROM notes
            ORDER BY mtime DESC
        """
        if limit:
            query += f" LIMIT {int(limit)}"
        rows = conn.execute(query).fetchall()
    finally:
        conn.close()
    return [
        {
            "path": row[0],
            "title": row[1],
            "sha1": row[2],
            "has_frontmatter": bool(row[3]),
            "frontmatter_text": row[4],
            "body_excerpt": row[5],
            "tags_json": row[6],
            "wikilinks_json": row[7],
        }
        for row in rows
    ]


def run_corpus_audit(*, dry_run: bool = True, limit: int | None = None) -> dict[str, Any]:
    notes = _load_notes(limit=limit)
    readiness_rows: list[dict[str, Any]] = []
    repair_rows: list[dict[str, Any]] = []
    score_rows: list[dict[str, Any]] = []
    ladder_rows: list[dict[str, Any]] = []
    semantic_rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for note in notes:
        readiness = build_note_readiness(note)
        readiness_rows.append(readiness)
        counts[readiness["class"]] = counts.get(readiness["class"], 0) + 1
        repair_rows.append({"path": note["path"], "recommended_actions": readiness["recommended_actions"]})
        score_rows.append({"path": note["path"], "gold_readiness": readiness["scores"]["gold_readiness"]})
        ladder_rows.append({"path": note["path"], "state": ladder_state(readiness)})
        semantic_rows.append(build_semantic_enrichment_candidate(note, readiness, persist=not dry_run))
        if not note["has_frontmatter"]:
            build_frontmatter_patch_candidate(note["path"], readiness, persist=not dry_run)
    summary = {
        "ok": True,
        "note_count": len(notes),
        "classes": counts,
        "global_state": "GOLD2_DATA_REHABILITATION_AND_ENRICHMENT_READY" if notes else "GOLD2_IDLE",
    }
    if not dry_run:
        rewrite_jsonl(note_readiness_path(), readiness_rows)
        rewrite_jsonl(metadata_repair_plan_path(), repair_rows)
        rewrite_jsonl(gold_readiness_scores_path(), score_rows)
        rewrite_jsonl(promotion_ladder_path(), ladder_rows)
        ensure_last(corpus_audit_path(), summary)
    return public_result(True, dry_run=dry_run, corpus_audit=summary, note_readiness=readiness_rows[:10])
