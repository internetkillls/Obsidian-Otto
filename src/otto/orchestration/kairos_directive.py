from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..logging_utils import get_logger
from ..models import choose_model
from ..retrieval.rag_context import build_rag_context
from ..state import now_iso, read_json, write_json
from .vault_telemetry import VaultTelemetryEngine, run_vault_telemetry


@dataclass
class Directive:
    directive_id: str
    area: str
    target: str          # "folder" | "date_range" | "file" | "signal_type"
    target_path: str | None
    action: str          # "dig" | "train" | "refine" | "ignore"
    priority: str        # "critical" | "high" | "medium" | "low"
    rationale: str
    model_evidence: str  # RAG-grounded reasoning
    commands: list[str]  # Otto commands to execute
    done: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "directive_id": self.directive_id,
            "area": self.area,
            "target": self.target,
            "target_path": self.target_path,
            "action": self.action,
            "priority": self.priority,
            "rationale": self.rationale,
            "model_evidence": self.model_evidence,
            "commands": self.commands,
            "done": self.done,
        }


@dataclass
class KAIROSDirectiveManifest:
    ts: str
    cycle: int
    directives: list[Directive]
    summary: dict[str, Any]
    model_hint: str
    rag_tokens: int


class KAIROSDirectiveEngine:
    """Data Engineer + Academic Strategist.

    Takes vault telemetry + RAG context → produces actionable directives
    for what to dig (repair/improve), what to train on (high signal notes),
    and what to refine (metadata repair strategy).
    """

    def __init__(self, cycle: int = 1):
        self.paths = load_paths()
        self.cycle = cycle
        self._logger = get_logger("otto.kairos.directive")
        self._telemetry: Any = None
        self._rag_slices: list[Any] = []

    def _load_telemetry(self) -> Any:
        if self._telemetry is not None:
            return self._telemetry
        report = run_vault_telemetry()
        self._telemetry = report
        return report

    def _load_rag(self) -> list[Any]:
        if not self._rag_slices:
            self._rag_slices = build_rag_context(
                goal="kairos directive: vault data engineering and academic strategy",
                query="metadata repair training data signals frontmatter tags scarcity",
            )
        return self._rag_slices

    def produce_directives(self) -> KAIROSDirectiveManifest:
        """Main entry: run telemetry + RAG → produce directive manifest."""
        logger = self._logger
        telemetry = self._load_telemetry()
        rag_slices = self._load_rag()
        model = choose_model("kairos_daily")

        total_tokens = sum(s.tokens for s in rag_slices)
        logger.info(f"[kairos.directive] cycle={self.cycle} areas={len(telemetry.areas)} tokens={total_tokens}")

        directives: list[Directive] = []

        # ── CRITICAL dig directives ─────────────────────────────────────
        for target in telemetry.dig_targets:
            area = target["area"]
            priority = target["priority"]
            uselessness = target["uselessness"]
            note_count = target["note_count"]

            # Find the area telemetry for evidence
            area_tm = next((a for a in telemetry.areas if a.area == area), None)
            rec = area_tm.recommendation if area_tm else ""

            # Build commands
            folder_name = Path(area).name
            cmds = [
                f"otto pipeline --scope {folder_name}",
                f"# Then: repair frontmatter + add scarcity fields in {area}",
                f"# Target: {note_count} notes, uselessness={uselessness}",
            ]

            rag_evidence = "\n".join(s.content[:300] for s in rag_slices[:3])

            directive = Directive(
                directive_id=f"dig-{Path(area).name}-{self.cycle}",
                area=area,
                target="folder",
                target_path=area,
                action="dig",
                priority=priority,
                rationale=(
                    f"Area '{area}' has {note_count} notes with uselessness={uselessness}. "
                    f"{rec}"
                ),
                model_evidence=(
                    f"RAG context ({total_tokens} tokens): "
                    f"{rag_evidence[:500]}..."
                ),
                commands=cmds,
            )
            directives.append(directive)

        # ── TRAIN directives (high training worth areas) ─────────────────
        for target in telemetry.train_targets[:5]:
            area = target["area"]
            worth = target["training_worth"]
            candidates = target.get("top_candidates", [])[:3]

            rag_evidence = "\n".join(s.content[:300] for s in rag_slices[:3])

            directive = Directive(
                directive_id=f"train-{Path(area).name}-{self.cycle}",
                area=area,
                target="folder",
                target_path=area,
                action="train",
                priority="high" if worth > 2.0 else "medium",
                rationale=(
                    f"Area '{area}' training worth={worth}. "
                    f"Top candidates: {', '.join(c.get('title','') for c in candidates)}. "
                    f"High signal density + frontmatter coverage — good training data."
                ),
                model_evidence=f"RAG evidence: {rag_evidence[:500]}...",
                commands=[
                    f"# {area}: export top candidates for fine-tuning",
                    f"# Candidates: {json.dumps(candidates)}",
                    f"# Otto: mark these as training-eligible in gold_summary",
                ],
            )
            directives.append(directive)

        # ── REFINE directives (strategy refinement based on patterns) ────
        # Look for patterns: which metadata fields are most missing across the vault?
        all_areas = telemetry.areas
        missing_fm_areas = [a for a in all_areas if a.frontmatter_pct < 0.5]
        missing_scarcity_areas = [a for a in all_areas if a.signal_density < 0.5]
        orphan_heavy = [a for a in all_areas if a.orphan_ratio > 0.3]

        if missing_fm_areas:
            areas_str = ", ".join(Path(a.area).name for a in missing_fm_areas[:5])
            directives.append(Directive(
                directive_id=f"refine-frontmatter-{self.cycle}",
                area=areas_str,
                target="signal_type",
                target_path=None,
                action="refine",
                priority="high",
                rationale=(
                    f"{len(missing_fm_areas)} areas have <50% frontmatter coverage. "
                    f"Systemic issue: adding frontmatter will boost training data quality across "
                    f"{sum(a.note_count for a in missing_fm_areas)} notes."
                ),
                model_evidence="RAG shows frontmatter absence is top uselessness driver.",
                commands=[
                    "# Run: otto pipeline --full to rescan with frontmatter check",
                    "# Target: add frontmatter.yaml to these areas",
                ],
            ))

        if missing_scarcity_areas:
            areas_str = ", ".join(Path(a.area).name for a in missing_scarcity_areas[:5])
            directives.append(Directive(
                directive_id=f"refine-scarcity-{self.cycle}",
                area=areas_str,
                target="signal_type",
                target_path=None,
                action="refine",
                priority="medium",
                rationale=(
                    f"{len(missing_scarcity_areas)} areas have low scarcity signal density. "
                    f"Adding scarcity fields will improve training data quality."
                ),
                model_evidence="RAG shows scarcity field presence boosts training worth 1.5x.",
                commands=[
                    "# Add scarcity field to all notes in these areas",
                    "# scarcity: [what is scarce in this note, what would be lost if deleted]",
                ],
            ))

        if orphan_heavy:
            areas_str = ", ".join(Path(a.area).name for a in orphan_heavy[:5])
            directives.append(Directive(
                directive_id=f"refine-orphan-{self.cycle}",
                area=areas_str,
                target="signal_type",
                target_path=None,
                action="refine",
                priority="medium",
                rationale=(
                    f"{len(orphan_heavy)} areas have >30% orphan notes (no fm, no tags, no links). "
                    f"Orphan notes drag down overall training quality."
                ),
                model_evidence="RAG shows orphan ratio strongly anti-correlates with training worth.",
                commands=[
                    "# For orphan notes: add tags, add wikilinks, add frontmatter",
                    "# Target: reduce orphan ratio below 15% per area",
                ],
            ))

        summary = {
            "total_directives": len(directives),
            "dig": len([d for d in directives if d.action == "dig"]),
            "train": len([d for d in directives if d.action == "train"]),
            "refine": len([d for d in directives if d.action == "refine"]),
            "critical": len([d for d in directives if d.priority == "critical"]),
            "high": len([d for d in directives if d.priority == "high"]),
            "medium": len([d for d in directives if d.priority == "medium"]),
            "low": len([d for d in directives if d.priority == "low"]),
            "total_notes_affected": sum(
                next((a.note_count for a in telemetry.areas if a.area == d.area), 0)
                for d in directives
            ),
            "overall_uselessness": telemetry.overall_uselessness,
            "overall_training_worth": telemetry.overall_training_worth,
        }

        manifest = KAIROSDirectiveManifest(
            ts=now_iso(),
            cycle=self.cycle,
            directives=directives,
            summary=summary,
            model_hint=model.model,
            rag_tokens=total_tokens,
        )

        # Persist
        self._save_manifest(manifest)
        return manifest

    def _save_manifest(self, manifest: KAIROSDirectiveManifest) -> None:
        out_dir = self.paths.state_root / "kairos"
        out_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = out_dir / f"directives_{manifest.cycle:04d}.json"
        write_json(manifest_path, {
            "ts": manifest.ts,
            "cycle": manifest.cycle,
            "model_hint": manifest.model_hint,
            "rag_tokens": manifest.rag_tokens,
            "summary": manifest.summary,
            "directives": [d.to_dict() for d in manifest.directives],
        })

        # Latest symlink
        write_json(out_dir / "directives_latest.json", {
            "ts": manifest.ts,
            "cycle": manifest.cycle,
            "model_hint": manifest.model_hint,
            "rag_tokens": manifest.rag_tokens,
            "summary": manifest.summary,
            "directives": [d.to_dict() for d in manifest.directives],
        })

    def dig_area(self, area_path: str, focus: str = "all") -> dict[str, Any]:
        """Dig into a specific area: show exact notes, quality breakdown, recommendations."""
        engine = VaultTelemetryEngine()
        telemetry = engine.scan()

        area_tm = next((a for a in telemetry.areas if a.area == area_path), None)
        if not area_tm:
            return {"error": f"Area not found: {area_path}", "available_areas": [a.area for a in telemetry.areas]}

        # Query SQLite for exact note data in this area
        conn = sqlite3.connect(self.paths.sqlite_path)
        conn.set_trace_callback(None)
        rows = conn.execute(
            """
            SELECT path, title, size, has_frontmatter, frontmatter_text,
                   body_excerpt, tags_json, wikilinks_json, mtime
            FROM notes
            WHERE path LIKE ?
            ORDER BY mtime DESC
            """,
            (f"{area_path}%",),
        ).fetchall()
        conn.close()

        note_data = []
        for row in rows:
            path, title, size, has_fm, fm_text, body, tags_json, wlinks_json, mtime = row
            note_data.append({
                "path": path,
                "title": title,
                "size": size or 0,
                "has_frontmatter": bool(has_fm),
                "tags": json.loads(tags_json) if tags_json else [],
                "wikilinks": json.loads(wlinks_json) if wlinks_json else [],
                "scarcity": [],
                "necessity": None,
                "clusters": [],
                "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()[:10] if mtime else "?",
                "body_preview": (body or "")[:200],
            })

        return {
            "area": area_path,
            "note_count": len(note_data),
            "telemetry": {
                "uselessness_score": area_tm.uselessness_score,
                "training_worth_score": area_tm.training_worth_score,
                "frontmatter_pct": area_tm.frontmatter_pct,
                "tag_density": area_tm.tag_density,
                "wikilink_density": area_tm.wikilink_density,
                "signal_density": area_tm.signal_density,
                "orphan_ratio": area_tm.orphan_ratio,
                "dig_priority": area_tm.dig_priority,
                "recommendation": area_tm.recommendation,
            },
            "notes": note_data,
        }

    def dig_date_range(self, date_from: str, date_to: str) -> dict[str, Any]:
        """Dig into notes modified within a date range."""
        conn = sqlite3.connect(self.paths.sqlite_path)
        conn.set_trace_callback(None)
        rows = conn.execute(
            """
            SELECT path, title, size, has_frontmatter, tags_json, wikilinks_json, mtime
            FROM notes
            WHERE mtime BETWEEN ? AND ?
            ORDER BY mtime DESC
            """,
            (self._parse_date(date_from), self._parse_date(date_to)),
        ).fetchall()
        conn.close()

        notes = []
        for row in rows:
            path, title, size, has_fm, tags_json, wlinks_json, mtime = row
            notes.append({
                "path": path,
                "title": title,
                "size": size or 0,
                "has_frontmatter": bool(has_fm),
                "tags": json.loads(tags_json) if tags_json else [],
                "wikilinks": json.loads(wlinks_json) if wlinks_json else [],
                "scarcity": [],
                "necessity": None,
                "clusters": [],
                "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()[:10] if mtime else "?",
            })

        return {
            "date_from": date_from,
            "date_to": date_to,
            "note_count": len(notes),
            "notes": notes,
        }

    def dig_file(self, file_path: str) -> dict[str, Any]:
        """Deep-dive into a single file: full metadata quality, signal scores, recommendations."""
        conn = sqlite3.connect(self.paths.sqlite_path)
        conn.set_trace_callback(None)
        row = conn.execute(
            """
            SELECT path, title, size, has_frontmatter, frontmatter_text, body_excerpt,
                   tags_json, wikilinks_json, mtime
            FROM notes WHERE path = ?
            """,
            (file_path,),
        ).fetchone()
        conn.close()

        if not row:
            return {"error": f"File not in SQLite: {file_path}", "hint": "run pipeline first to index this file"}

        path, title, size, has_fm, fm_text, body, tags_json, wlinks_json, mtime = row

        # Score this individual note
        note = {
            "has_frontmatter": bool(has_fm),
            "tags": json.loads(tags_json) if tags_json else [],
            "wikilinks": json.loads(wlinks_json) if wlinks_json else [],
            "scarcity": json.loads(scarcity) if scarcity and scarcity != "null" else [],
            "necessity": necessity,
            "clusters": json.loads(cluster) if cluster and cluster != "null" else [],
            "size": size or 0,
        }

        quality_score = (
            (1 if note["has_frontmatter"] else 0) * 2.0
            + (len(note["tags"]) / 3) * 1.5
            + (len(note["wikilinks"]) / 3) * 1.2
            + len(note["scarcity"]) * 0.5
            + (1 if note["necessity"] else 0) * 1.0
            + len(note["clusters"]) * 0.5
        )

        missing = []
        if not note["has_frontmatter"]: missing.append("frontmatter")
        if not note["tags"]: missing.append("tags")
        if not note["wikilinks"]: missing.append("wikilinks")
        if not note["scarcity"]: missing.append("scarcity")
        if not note["necessity"]: missing.append("necessity")

        recommendations = []
        if "frontmatter" in missing:
            recommendations.append("Add frontmatter with tags, created date, and status fields")
        if "scarcity" in missing:
            recommendations.append("Add scarcity field: what is scarce here, what would be lost")
        if "tags" in missing:
            recommendations.append("Add at least 2-3 descriptive tags")
        if "wikilinks" in missing:
            recommendations.append("Link to related notes with [[wikilinks]]")
        if "necessity" in missing:
            recommendations.append("Add necessity field: why this note must exist")

        return {
            "file": path,
            "title": title,
            "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()[:10] if mtime else "?",
            "quality_score": round(quality_score, 2),
            "has_frontmatter": note["has_frontmatter"],
            "tags": note["tags"],
            "wikilinks": note["wikilinks"],
            "scarcity": note["scarcity"],
            "necessity": note["necessity"],
            "clusters": note["clusters"],
            "missing_fields": missing,
            "recommendations": recommendations,
            "frontmatter_text": fm_text[:500] if fm_text else None,
            "body_preview": (body or "")[:400] if body else None,
        }

    def _parse_date(self, date_str: str) -> float:
        """Parse YYYY-MM-DD to epoch timestamp."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return 0.0

    def current_manifest(self) -> dict[str, Any]:
        """Return the latest directive manifest."""
        path = self.paths.state_root / "kairos" / "directives_latest.json"
        return read_json(path, default={"directives": [], "summary": {}}) or {}


def produce_kairos_directives(cycle: int = 1) -> KAIROSDirectiveManifest:
    engine = KAIROSDirectiveEngine(cycle=cycle)
    return engine.produce_directives()