from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..logging_utils import get_logger
from ..state import now_iso, write_json


# ── scoring constants ──────────────────────────────────────────────────────────
@dataclass
class QualityWeights:
    # Uselessness factors (higher = more useless for training)
    no_frontmatter_penalty: float = 2.0
    no_tags_penalty: float = 1.5
    no_wikilinks_penalty: float = 1.2
    no_scarcity_penalty: float = 1.0
    no_necessity_penalty: float = 0.8
    orphan_penalty: float = 1.8  # no links, no tags, no fm = orphan
    duplicate_title_penalty: float = 1.5

    # Training worth factors (higher = more worth training on)
    has_frontmatter_bonus: float = 1.0
    has_scarcity_bonus: float = 1.5
    has_necessity_bonus: float = 1.5
    has_cluster_bonus: float = 1.2
    signal_density_bonus: float = 1.0  # per signal field filled
    depth_bonus: float = 0.8  # longer notes tend to be more substantive
    recency_bonus: float = 0.5  # recently modified notes are more relevant
    unique_title_bonus: float = 0.5  # non-duplicate titles


WEIGHTS = QualityWeights()


@dataclass
class AreaTelemetry:
    area: str
    note_count: int
    avg_size: float
    frontmatter_pct: float
    tag_density: float
    wikilink_density: float
    signal_density: float
    orphan_ratio: float
    duplicate_ratio: float
    recency_score: float
    content_uniqueness: float
    uselessness_score: float
    training_worth_score: float
    train_candidates: list[dict[str, Any]]
    dig_priority: str  # "critical" | "high" | "medium" | "low"
    recommendation: str
    mtime: str


@dataclass
class VaultTelemetryReport:
    overall_uselessness: float
    overall_training_worth: float
    high_value_areas: list[str]
    dead_zones: list[str]
    dig_targets: list[dict[str, Any]]
    train_targets: list[dict[str, Any]]
    areas: list[AreaTelemetry]


class VaultTelemetryEngine:
    """Scans the vault and produces actionable telemetry on data quality and training worth."""

    def __init__(self, sqlite_conn: sqlite3.Connection | None = None):
        self.paths = load_paths()
        self._conn = sqlite_conn
        self._logger = get_logger("otto.telemetry")

    def _conn(self) -> sqlite3.Connection:
        if self._conn:
            return self._conn
        return sqlite3.connect(self.paths.sqlite_path)

    def scan(self) -> VaultTelemetryReport:
        logger = self._logger
        conn = sqlite3.connect(self.paths.sqlite_path)
        conn.set_trace_callback(None)

        rows = conn.execute(
            """
            SELECT path, title, size, has_frontmatter, frontmatter_text,
                   body_excerpt, tags_json, wikilinks_json, mtime
            FROM notes
            ORDER BY mtime DESC
            """
        ).fetchall()
        conn.close()

        if not rows:
            return VaultTelemetryReport(
                overall_uselessness=0.0,
                overall_training_worth=0.0,
                high_value_areas=[],
                dead_zones=[],
                dig_targets=[],
                train_targets=[],
                areas=[],
            )

        by_area: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            path, title, size, has_fm, fm_text, body, tags_json, wlinks_json, mtime = row
            area = str(Path(path).parent)
            note = {
                "path": path, "title": title, "size": size or 0,
                "has_frontmatter": bool(has_fm),
                "frontmatter_text": fm_text or "",
                "body_excerpt": body or "",
                "tags": json.loads(tags_json) if tags_json else [],
                "wikilinks": json.loads(wlinks_json) if wlinks_json else [],
                "mtime": mtime or 0,
                "scarcity": [],
                "necessity": None,
                "cluster": [],
                "allocation": None,
                "orientation": None,
            }
            by_area.setdefault(area, []).append(note)

        areas: list[AreaTelemetry] = []
        all_uselessness, all_worth, note_count = [], [], 0

        for area_name, notes in sorted(by_area.items(), key=lambda x: len(x[1]), reverse=True):
            at = self._score_area(area_name, notes)
            areas.append(at)
            all_uselessness.append(at.uselessness_score * at.note_count)
            all_worth.append(at.training_worth_score * at.note_count)
            note_count += at.note_count

        total_notes = max(note_count, 1)
        overall_uselessness = round(sum(all_uselessness) / total_notes, 3)
        overall_training_worth = round(sum(all_worth) / total_notes, 3)

        high_value = [a.area for a in areas if a.training_worth_score > 1.5 and a.note_count >= 3]
        dead_zones = [a.area for a in areas if a.uselessness_score > 2.5 and a.note_count >= 3]

        dig_targets = [
            {
                "area": a.area,
                "priority": a.dig_priority,
                "reason": a.recommendation,
                "note_count": a.note_count,
                "uselessness": a.uselessness_score,
            }
            for a in areas
            if a.dig_priority in ("critical", "high")
            and a.note_count >= 2
        ]
        dig_targets.sort(key=lambda x: {"critical": 0, "high": 1}.get(x["priority"], 2))

        train_targets = [
            {
                "area": a.area,
                "note_count": a.note_count,
                "training_worth": a.training_worth_score,
                "signal_density": a.signal_density,
                "top_candidates": a.train_candidates[:5],
            }
            for a in areas
            if a.training_worth_score > 0.8 and a.note_count >= 2
        ]
        train_targets.sort(key=lambda x: -x["training_worth"])

        return VaultTelemetryReport(
            overall_uselessness=overall_uselessness,
            overall_training_worth=overall_training_worth,
            high_value_areas=high_value,
            dead_zones=dead_zones,
            dig_targets=dig_targets,
            train_targets=train_targets,
            areas=areas,
        )

    def _score_area(self, area: str, notes: list[dict[str, Any]]) -> AreaTelemetry:
        n = len(notes)
        if n == 0:
            return AreaTelemetry(
                area=area, note_count=0, avg_size=0.0, frontmatter_pct=0.0,
                tag_density=0.0, wikilink_density=0.0, signal_density=0.0,
                orphan_ratio=0.0, duplicate_ratio=0.0, recency_score=0.0,
                content_uniqueness=0.0, uselessness_score=0.0, training_worth_score=0.0,
                train_candidates=[], dig_priority="low", recommendation="no data",
            )

        now_ts = datetime.now(timezone.utc).timestamp()
        titles = [note["title"].strip().lower() for note in notes]
        dup_titles = len(titles) - len(set(titles))

        def avg_field(getter):
            vals = [getter(note) for note in notes if getter(note) is not None]
            return sum(vals) / len(vals) if vals else 0.0

        fm_pct = sum(1 for note in notes if note["has_frontmatter"]) / n
        tag_dens = avg_field(lambda note: len(note["tags"]))
        wl_dens = avg_field(lambda note: len(note["wikilinks"]))
        sig_dens = avg_field(lambda note: sum(1 for s in [note.get("scarcity"), note.get("necessity"), note.get("cluster")] if s))
        orphan_ratio = sum(1 for note in notes if not note["has_frontmatter"] and not note["tags"] and not note["wikilinks"]) / n
        dup_ratio = dup_titles / n

        recency_vals = []
        for note in notes:
            mtime = note.get("mtime") or 0
            if mtime > 0:
                age_days = max((now_ts - mtime) / 86400, 0)
                recency_vals.append(max(0, 1 - age_days / 90))
        recency_score = sum(recency_vals) / len(recency_vals) if recency_vals else 0.0

        avg_size = avg_field(lambda note: note.get("size") or 0)

        # Uniqueness: if titles vary widely = more unique content
        title_words = set(w for t in titles for w in t.split() if len(w) > 4)
        content_uniqueness = min(1.0, len(title_words) / max(n * 3, 1))

        # ── Uselessness score ─────────────────────────────────────────────
        uselessness = (
            (1 - fm_pct) * WEIGHTS.no_frontmatter_penalty
            + (1 - avg_field(lambda note: 1 if note["tags"] else 0)) * WEIGHTS.no_tags_penalty
            + (1 - avg_field(lambda note: 1 if note["wikilinks"] else 0)) * WEIGHTS.no_wikilinks_penalty
            + orphan_ratio * WEIGHTS.orphan_penalty
            + dup_ratio * WEIGHTS.duplicate_title_penalty
            + (1 - sig_dens / 4) * 0.5  # low signal density penalty
        )

        # ── Training worth score ───────────────────────────────────────────
        worth = (
            fm_pct * WEIGHTS.has_frontmatter_bonus
            + (sig_dens / 4) * WEIGHTS.signal_density_bonus
            + recency_score * WEIGHTS.recency_bonus
            + content_uniqueness * 0.5
            + avg_field(lambda note: min(1.0, (note.get("size") or 0) / 2000)) * WEIGHTS.depth_bonus
            + (1 - dup_ratio) * WEIGHTS.unique_title_bonus
        )

        # ── Dig priority ──────────────────────────────────────────────────
        if uselessness > 2.5 and fm_pct < 0.3:
            dig_priority = "critical"
            rec = f"Critical: {n} notes, {fm_pct:.0%} frontmatter, {orphan_ratio:.0%} orphan. Dig to repair + add scarcity fields."
        elif uselessness > 1.8:
            dig_priority = "high"
            rec = f"High: {n} notes with low metadata density. Add tags, wikilinks, scarcity."
        elif uselessness > 1.0:
            dig_priority = "medium"
            rec = f"Medium: {n} notes. Improve metadata completeness for training worth."
        else:
            dig_priority = "low"
            rec = f"Healthy: {n} notes. Good metadata coverage, worth training on."

        # ── Training candidates ───────────────────────────────────────────
        candidates = []
        for note in notes:
            n_worth = (
                (1 if note["has_frontmatter"] else 0) * 1.0
                + (len(note["tags"]) / 3) * 0.5
                + (len(note["wikilinks"]) / 3) * 0.5
                + len(note.get("scarcity") or []) * 0.3
                + min(1.0, (note.get("size") or 0) / 2000) * 0.8
            )
            candidates.append({"path": note["path"], "title": note["title"], "worth_score": round(n_worth, 3)})
        candidates.sort(key=lambda x: -x["worth_score"])

        mtime_str = max(
            (datetime.fromtimestamp(note["mtime"], tz=timezone.utc).isoformat()[:10]
             for note in notes if note.get("mtime", 0) > 0),
            default="unknown",
        )

        return AreaTelemetry(
            area=area, note_count=n,
            avg_size=round(avg_size, 1),
            frontmatter_pct=round(fm_pct, 3),
            tag_density=round(tag_dens, 2),
            wikilink_density=round(wl_dens, 2),
            signal_density=round(sig_dens, 3),
            orphan_ratio=round(orphan_ratio, 3),
            duplicate_ratio=round(dup_ratio, 3),
            recency_score=round(recency_score, 3),
            content_uniqueness=round(content_uniqueness, 3),
            uselessness_score=round(uselessness, 3),
            training_worth_score=round(worth, 3),
            train_candidates=candidates,
            dig_priority=dig_priority,
            recommendation=rec,
            mtime=mtime_str,
        )


def run_vault_telemetry() -> VaultTelemetryReport:
    """Run full vault telemetry scan and save results."""
    engine = VaultTelemetryEngine()
    report = engine.scan()

    paths = load_paths()
    out = paths.state_root / "kairos" / "vault_telemetry.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    report_dict = {
        "ts": now_iso(),
        "overall_uselessness": report.overall_uselessness,
        "overall_training_worth": report.overall_training_worth,
        "high_value_areas": report.high_value_areas,
        "dead_zones": report.dead_zones,
        "dig_targets": report.dig_targets,
        "train_targets": report.train_targets,
        "areas": [
            {
                "area": a.area,
                "note_count": a.note_count,
                "avg_size": a.avg_size,
                "frontmatter_pct": a.frontmatter_pct,
                "tag_density": a.tag_density,
                "wikilink_density": a.wikilink_density,
                "signal_density": a.signal_density,
                "orphan_ratio": a.orphan_ratio,
                "duplicate_ratio": a.duplicate_ratio,
                "recency_score": a.recency_score,
                "content_uniqueness": a.content_uniqueness,
                "uselessness_score": a.uselessness_score,
                "training_worth_score": a.training_worth_score,
                "dig_priority": a.dig_priority,
                "recommendation": a.recommendation,
                "mtime": a.mtime,
            }
            for a in report.areas
        ],
    }
    write_json(out, report_dict)

    train_out = paths.state_root / "kairos" / "training_candidates.json"
    candidates_doc = {
        "ts": now_iso(),
        "total_areas": len(report.areas),
        "train_targets": report.train_targets,
        "dig_targets": report.dig_targets,
    }
    write_json(train_out, candidates_doc)

    return report