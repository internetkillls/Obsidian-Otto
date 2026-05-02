from __future__ import annotations

import sqlite3
from typing import Any

from ..config import load_paths, load_retrieval_config, load_wellbeing
from ..logging_utils import get_logger
from ..state import write_json
from .vector_store import build_vector_cache


def _folder_sample(conn: sqlite3.Connection, folder: str, limit: int = 3) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT path, title, has_frontmatter
        FROM notes
        WHERE path LIKE ?
        ORDER BY mtime DESC
        LIMIT ?
        """,
        (f"{folder}/%", limit),
    ).fetchall()
    return [{"path": row[0], "title": row[1], "has_frontmatter": bool(row[2])} for row in rows]


def _extract_wellbeing(conn: sqlite3.Connection) -> dict[str, Any]:
    cfg = load_wellbeing()
    if not cfg.get("enabled"):
        return {"enabled": False, "note": "wellbeing parsing disabled"}
    keys = cfg.get("frontmatter_keys", {})
    rows = conn.execute("SELECT frontmatter_text FROM notes WHERE has_frontmatter = 1").fetchall()
    signals = {"mood": [], "energy": [], "stress": [], "strength": [], "weakness": [], "opportunity": [], "threat": []}
    for (fm_text,) in rows:
        for raw_line in str(fm_text or "").splitlines():
            if ":" not in raw_line:
                continue
            key, value = raw_line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            for signal_name, signal_key in keys.items():
                if key == str(signal_key).strip().lower():
                    signals.setdefault(signal_name, []).append(value)
    return {"enabled": True, "signals": {k: v[-10:] for k, v in signals.items() if v}}


def build_gold() -> dict[str, Any]:
    logger = get_logger("otto.gold")
    paths = load_paths()
    conn = sqlite3.connect(paths.sqlite_path)

    folder_risk = [
        {
            "folder": row[0],
            "missing_frontmatter": row[1],
            "duplicate_titles": row[2],
            "outbound_links": row[3],
            "note_count": row[4],
            "risk_score": row[5],
            "examples": _folder_sample(conn, row[0]),
        }
        for row in conn.execute(
            """
            SELECT folder, missing_frontmatter, duplicate_titles, outbound_links, note_count, risk_score
            FROM folder_risk
            ORDER BY risk_score DESC, note_count DESC
            LIMIT 12
            """
        ).fetchall()
    ]

    retrieval_cfg = load_retrieval_config()
    vector_cfg = retrieval_cfg.get("vector", {})
    excluded_prefixes = [str(item) for item in (vector_cfg.get("exclude_prefixes") or [])]
    excluded_suffixes = [str(item).replace("\\", "/").lower() for item in (vector_cfg.get("exclude_suffixes") or [])]
    excluded_titles = {str(item).strip().lower() for item in (vector_cfg.get("exclude_titles") or [])}

    note_rows = conn.execute(
        """
        SELECT path, title, frontmatter_text, body_excerpt
        FROM notes
        WHERE has_frontmatter = 1
        ORDER BY mtime DESC
        """
    ).fetchall()
    vector_notes = [
        {
            "path": row[0],
            "title": row[1],
            "frontmatter_text": row[2],
            "render_text": "\n".join(
                part for part in [row[1] or "", row[2] or "", row[3] or ""] if part
            ),
        }
        for row in note_rows
        if not any(str(row[0] or "").replace("\\", "/").lower().startswith(prefix.replace("\\", "/").lower()) for prefix in excluded_prefixes)
        if not any(str(row[0] or "").replace("\\", "/").lower().endswith(suffix) for suffix in excluded_suffixes)
        if str(row[1] or "").strip().lower() not in excluded_titles
    ]
    vector_result = build_vector_cache(vector_notes)
    wellbeing = _extract_wellbeing(conn)
    conn.close()

    training_ready = (
        len(folder_risk) > 0
        and sum(item["missing_frontmatter"] for item in folder_risk[:5]) < 100
    )

    summary = {
        "top_folders": folder_risk[:8],
        "training_readiness": {
            "ready": training_ready,
            "reasons": [
                "Gold exists" if folder_risk else "No Gold summary built",
                "Frontmatter corruption not catastrophic" if training_ready else "Too many hygiene issues remain",
            ],
        },
        "vector_cache": vector_result.__dict__,
        "wellbeing": wellbeing,
        "next_actions": [
            "fix frontmatter in the top risky folder",
            "rerun scoped pipeline for any folder above risk score 10",
            "export training candidates only after Gold is reviewed",
        ],
    }

    write_json(paths.artifacts_root / "summaries" / "gold_summary.json", summary)

    report_lines = ["# Gold Summary", "", "## Top folders"]
    for item in summary["top_folders"]:
        report_lines.append(
            f"- **{item['folder']}** risk={item['risk_score']} missing_frontmatter={item['missing_frontmatter']} duplicates={item['duplicate_titles']} notes={item['note_count']}"
        )
    report_lines.extend(["", "## Training readiness", f"- ready: {summary['training_readiness']['ready']}", "", "## Next actions"])
    report_lines.extend([f"- {line}" for line in summary["next_actions"]])
    report_path = paths.artifacts_root / "reports" / "gold_summary.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    logger.info(f"[gold] top_folders={len(summary['top_folders'])} training_ready={training_ready}")
    return summary
