from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import load_paths, load_retrieval_config
from ..logging_utils import append_jsonl, get_logger
from ..state import now_iso, read_json, write_json


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")
_STOPWORDS = {
    "this",
    "that",
    "with",
    "from",
    "into",
    "about",
    "there",
    "their",
    "where",
    "which",
    "what",
    "have",
    "been",
    "were",
    "will",
    "would",
    "could",
    "should",
    "might",
    "than",
    "when",
    "then",
    "because",
    "while",
    "also",
    "across",
    "between",
    "still",
}


@dataclass
class GoldSignalScore:
    note_path: str
    title: str
    folder: str
    category: str
    category_reason: str
    primary_claim: str
    utility: float
    vault_alignment: float
    insight_density: float
    actionability: float
    temporal_durability: float
    total_score: float
    threshold: float
    promoted: bool
    consistency_hits: int
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "note_path": self.note_path,
            "title": self.title,
            "folder": self.folder,
            "category": self.category,
            "category_reason": self.category_reason,
            "primary_claim": self.primary_claim,
            "utility": round(self.utility, 3),
            "vault_alignment": round(self.vault_alignment, 3),
            "insight_density": round(self.insight_density, 3),
            "actionability": round(self.actionability, 3),
            "temporal_durability": round(self.temporal_durability, 3),
            "total_score": round(self.total_score, 3),
            "threshold": round(self.threshold, 3),
            "promoted": self.promoted,
            "consistency_hits": self.consistency_hits,
            "notes": self.notes,
        }


@dataclass
class GoldContradiction:
    note_path: str
    conflicting_path: str
    primary_claim: str
    conflicting_excerpt: str
    confidence: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "note_path": self.note_path,
            "conflicting_path": self.conflicting_path,
            "primary_claim": self.primary_claim,
            "conflicting_excerpt": self.conflicting_excerpt,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
        }


@dataclass
class KairosGoldResult:
    ts: str
    kairos_score: float
    gold_promoted_count: int
    silver_count: int
    noise_count: int
    category_counts: dict[str, int]
    category_promoted_counts: dict[str, int]
    scored_signals: list[GoldSignalScore]
    contradictions: list[GoldContradiction]
    dynamic_thresholds: dict[str, float]
    promoted_paths: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "kairos_score": round(self.kairos_score, 3),
            "gold_promoted_count": self.gold_promoted_count,
            "silver_count": self.silver_count,
            "noise_count": self.noise_count,
            "category_counts": self.category_counts,
            "category_promoted_counts": self.category_promoted_counts,
            "scored_signals": [item.as_dict() for item in self.scored_signals],
            "contradictions": [item.as_dict() for item in self.contradictions],
            "dynamic_thresholds": {k: round(v, 3) for k, v in self.dynamic_thresholds.items()},
            "promoted_paths": self.promoted_paths,
        }


class KairosGoldEngine:
    CATEGORY_PROFILES = {
        "theory": {
            "weights": {
                "utility": 0.18,
                "vault_alignment": 0.22,
                "insight_density": 0.30,
                "actionability": 0.08,
                "temporal_durability": 0.22,
            },
            "threshold": 3.92,
        },
        "operational": {
            "weights": {
                "utility": 0.34,
                "vault_alignment": 0.18,
                "insight_density": 0.12,
                "actionability": 0.22,
                "temporal_durability": 0.14,
            },
            "threshold": 4.02,
        },
        "anchor": {
            "weights": {
                "utility": 0.18,
                "vault_alignment": 0.28,
                "insight_density": 0.14,
                "actionability": 0.06,
                "temporal_durability": 0.34,
            },
            "threshold": 3.88,
        },
        "bridge": {
            "weights": {
                "utility": 0.26,
                "vault_alignment": 0.21,
                "insight_density": 0.20,
                "actionability": 0.17,
                "temporal_durability": 0.16,
            },
            "threshold": 3.98,
        },
    }
    DEFAULT_PROFILE = {
        "weights": {
            "utility": 0.28,
            "vault_alignment": 0.22,
            "insight_density": 0.22,
            "actionability": 0.14,
            "temporal_durability": 0.14,
        },
        "threshold": 4.00,
    }
    CORE_THRESHOLD = 3.90
    HIGH_VALUE_THRESHOLD = 3.95
    DEFAULT_THRESHOLD = 4.06

    THEORY_MARKERS = (
        "theory",
        "proof",
        "lemma",
        "argument",
        "framework",
        "principle",
        "model",
        "method",
        "methodology",
        "epistemic",
        "philosophy",
        "ontology",
        "realism",
        "metakritik",
        "analysis",
        "concept",
        "logic",
        "syntax",
        "semantics",
        "thesis",
        "research",
        "corpus",
    )
    OPERATIONAL_MARKERS = (
        "repair",
        "fix",
        "implement",
        "ship",
        "task",
        "next step",
        "follow-up",
        "followup",
        "pipeline",
        "run ",
        "review",
        "audit",
        "cleanup",
        "automation",
        "deploy",
        "rebuild",
        "refactor",
        "calibration",
        "checklist",
    )
    ANCHOR_MARKERS = (
        "memory",
        "anchor",
        "profile",
        "handoff",
        "brain",
        "prediction",
        "continuity",
        "schedule",
        "state",
        "dream",
        "heartbeat",
        "mentor",
        "gold summary",
        "self-model",
    )

    def __init__(self) -> None:
        self.paths = load_paths()
        self.logger = get_logger("otto.kairos.gold")

    def _sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.paths.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _normalize_path(value: str) -> str:
        return str(value or "").replace("\\", "/").strip("/")

    @staticmethod
    def _json_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        text = str(value).strip()
        if not text:
            return []
        try:
            loaded = json.loads(text)
            if isinstance(loaded, list):
                return [str(item) for item in loaded]
        except json.JSONDecodeError:
            pass
        return [text]

    def _high_value_folders(self) -> set[str]:
        summary = read_json(self.paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
        folders: set[str] = set()
        for item in summary.get("top_folders", [])[:8]:
            folder = self._normalize_path(str(item.get("folder", "")))
            if folder:
                folders.add(folder.lower())
        return folders

    def _dynamic_threshold(self, note_path: str, high_value_folders: set[str]) -> float:
        normalized = self._normalize_path(note_path)
        root = normalized.split("/", 1)[0].lower() if normalized else ""
        core_roots = {"projects", "areas", "otto-realm", ".otto-realm"}
        if root in core_roots:
            return self.CORE_THRESHOLD
        lowered = normalized.lower()
        for folder in high_value_folders:
            if lowered == folder or lowered.startswith(f"{folder}/"):
                return self.HIGH_VALUE_THRESHOLD
        return self.DEFAULT_THRESHOLD

    def _candidate_notes(self, limit: int) -> list[dict[str, Any]]:
        if not self.paths.sqlite_path.exists():
            return []
        conn = self._sqlite()
        try:
            rows = conn.execute(
                """
                SELECT
                  n.path,
                  n.title,
                  n.frontmatter_text,
                  n.body_excerpt,
                  n.tags_json,
                  n.wikilinks_json,
                  n.scarcity,
                  n.necessity,
                  n.orientation,
                  n.allocation,
                  n.cluster_membership,
                  n.mtime,
                  COALESCE(MAX(r.risk_score), 0.0) AS risk_score
                FROM notes n
                LEFT JOIN folder_risk r
                  ON (
                    REPLACE(n.path, '\\', '/') LIKE REPLACE(r.folder, '\\', '/') || '/%'
                    OR REPLACE(n.path, '\\', '/') LIKE REPLACE(r.folder, '\\', '/')
                  )
                GROUP BY
                  n.path, n.title, n.frontmatter_text, n.body_excerpt, n.tags_json, n.wikilinks_json,
                  n.scarcity, n.necessity, n.orientation, n.allocation, n.cluster_membership, n.mtime
                ORDER BY risk_score DESC, n.mtime DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()

        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["path"] = str(item.get("path", ""))
            item["folder"] = self._normalize_path(item["path"]).split("/", 1)[0] if item.get("path") else ""
            results.append(item)
        return results

    def _full_body_text(self, note_path: str, fallback_excerpt: str) -> str:
        if self.paths.vault_path is None:
            return fallback_excerpt or ""
        target = self.paths.vault_path / Path(note_path)
        if not target.exists():
            target = self.paths.vault_path / Path(note_path.replace("\\", "/"))
        if not target.exists():
            return fallback_excerpt or ""
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return fallback_excerpt or ""
        fm = _FRONTMATTER_RE.match(text)
        return (text[fm.end():] if fm else text).strip()

    def build_claim_for_signal(self, note_row: dict[str, Any]) -> str:
        tags = self._json_list(note_row.get("tags_json"))
        links = self._json_list(note_row.get("wikilinks_json"))
        body = self._full_body_text(str(note_row.get("path", "")), str(note_row.get("body_excerpt", "")))
        body = body[:8000]
        segments = [
            f"title: {str(note_row.get('title', '')).strip()}",
            f"path: {str(note_row.get('path', '')).strip()}",
        ]
        fm_text = str(note_row.get("frontmatter_text", "") or "").strip()
        if fm_text:
            segments.append(f"frontmatter: {fm_text}")
        if tags:
            segments.append(f"tags: {', '.join(tags[:20])}")
        if links:
            segments.append(f"wikilinks: {', '.join(links[:20])}")
        scarcity = self._json_list(note_row.get("scarcity"))
        if scarcity:
            segments.append(f"scarcity: {', '.join(scarcity[:20])}")
        if note_row.get("orientation"):
            segments.append(f"orientation: {note_row.get('orientation')}")
        if note_row.get("allocation"):
            segments.append(f"allocation: {note_row.get('allocation')}")
        if note_row.get("necessity") not in (None, ""):
            segments.append(f"necessity: {note_row.get('necessity')}")
        if body:
            segments.append(f"body: {body}")
        return "\n".join(segments)

    def _category_text(self, note_row: dict[str, Any], claim: str) -> str:
        segments = [
            str(note_row.get("title", "")).strip(),
            str(note_row.get("path", "")).strip(),
            str(note_row.get("frontmatter_text", "") or "").strip(),
            str(note_row.get("orientation", "") or "").strip(),
            str(note_row.get("allocation", "") or "").strip(),
            str(note_row.get("necessity", "") or "").strip(),
            str(note_row.get("cluster_membership", "") or "").strip(),
            " ".join(self._json_list(note_row.get("tags_json"))),
            " ".join(self._json_list(note_row.get("wikilinks_json"))),
            " ".join(self._json_list(note_row.get("scarcity"))),
            claim,
        ]
        return " ".join(segment for segment in segments if segment).lower()

    def _category_matches(self, text: str, markers: tuple[str, ...]) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        for marker in markers:
            if marker in text:
                score += 1
                if len(reasons) < 4:
                    reasons.append(marker)
        return score, reasons

    def _infer_category(self, note_row: dict[str, Any], claim: str) -> tuple[str, str]:
        text = self._category_text(note_row, claim)
        theory_score, theory_hits = self._category_matches(text, self.THEORY_MARKERS)
        operational_score, operational_hits = self._category_matches(text, self.OPERATIONAL_MARKERS)
        anchor_score, anchor_hits = self._category_matches(text, self.ANCHOR_MARKERS)

        folder = self._normalize_path(str(note_row.get("path", ""))).lower()
        if folder.startswith("otto-realm/") or folder.startswith(".otto-realm/"):
            anchor_score += 3
            anchor_hits.insert(0, "otto-realm")
        if folder.startswith("state/") or folder.startswith("logs/"):
            anchor_score += 2
            anchor_hits.insert(0, "state/logs")
        if folder.startswith("projects/") or folder.startswith("areas/"):
            operational_score += 2
            operational_hits.insert(0, "projects/areas")
        if folder.startswith("10-inbox/") or folder.startswith("20-programs/") or folder.startswith("data/"):
            operational_score += 1
            operational_hits.insert(0, "workspace-ops")

        tag_text = " ".join(self._json_list(note_row.get("tags_json"))).lower()
        if any(token in tag_text for token in ("theory", "framework", "proof", "principle")):
            theory_score += 2
            theory_hits.insert(0, "tag")
        if any(token in tag_text for token in ("operational", "ops", "action", "repair")):
            operational_score += 2
            operational_hits.insert(0, "tag")
        if any(token in tag_text for token in ("anchor", "memory", "continuity")):
            anchor_score += 2
            anchor_hits.insert(0, "tag")

        ranked = sorted(
            [
                ("theory", theory_score, theory_hits),
                ("operational", operational_score, operational_hits),
                ("anchor", anchor_score, anchor_hits),
            ],
            key=lambda item: (-item[1], item[0]),
        )
        top_category, top_score, top_hits = ranked[0]
        runner_up = ranked[1]
        if top_score == 0:
            return "bridge", "fallback:no strong category signal"
        if top_category in {"theory", "operational"} and runner_up[1] > 0 and top_score - runner_up[1] <= 1:
            mixed_hits = ", ".join([top_category, runner_up[0]])
            return "bridge", f"mixed:{mixed_hits}"
        if top_category == "anchor" and top_score - runner_up[1] <= 1 and runner_up[1] > 0:
            return "bridge", "mixed:anchor-plus-other"
        reason = ", ".join(top_hits[:4]) if top_hits else "heuristic-match"
        return top_category, reason

    def _category_profile(self, category: str) -> dict[str, Any]:
        profile = self.CATEGORY_PROFILES.get(category)
        if profile is not None:
            return profile
        return self.DEFAULT_PROFILE

    @staticmethod
    def _keyword_terms(text: str, limit: int = 8) -> list[str]:
        freq: dict[str, int] = {}
        for token in _TOKEN_RE.findall(text.lower()):
            if token in _STOPWORDS:
                continue
            freq[token] = freq.get(token, 0) + 1
        ranked = sorted(freq.items(), key=lambda item: (-item[1], item[0]))
        return [term for term, _ in ranked[:limit]]

    @staticmethod
    def _wellness_signal_terms(text: str) -> bool:
        lowered = text.lower()
        patterns = (
            "wellbeing",
            "stress",
            "focus",
            "fatigue",
            "health",
            "gak sanggup",
            "ga sanggup",
            "gak kuat",
            "ga kuat",
            "berat banget",
            "moodku",
            "lelah",
            "capek",
            "burnout",
            "overwhelm",
            "overwhelmed",
            "shutdown",
            "cemas",
            "bingung banget",
            "not okay",
            "nothing helps",
            "nggak kuat",
        )
        if len(lowered.strip()) <= 5:
            return True
        return any(pattern in lowered for pattern in patterns)

    def _sqlite_consistency_hits(self, note_path: str, claim: str) -> list[dict[str, str]]:
        if not self.paths.sqlite_path.exists():
            return []
        terms = self._keyword_terms(claim)
        if not terms:
            return []
        conn = self._sqlite()
        hits: list[dict[str, str]] = []
        current = self._normalize_path(note_path)
        try:
            query = " OR ".join(terms[:6])
            rows = conn.execute(
                """
                SELECT path, title, body_excerpt
                FROM notes_fts
                WHERE notes_fts MATCH ?
                LIMIT 8
                """,
                (query,),
            ).fetchall()
            for row in rows:
                other_path = self._normalize_path(str(row["path"]))
                if other_path == current:
                    continue
                hits.append(
                    {
                        "path": str(row["path"]),
                        "title": str(row["title"]),
                        "excerpt": str(row["body_excerpt"] or "")[:500],
                    }
                )
        except sqlite3.Error:
            like_term = f"%{terms[0]}%"
            rows = conn.execute(
                """
                SELECT path, title, body_excerpt
                FROM notes
                WHERE (title LIKE ? OR body_excerpt LIKE ?)
                LIMIT 8
                """,
                (like_term, like_term),
            ).fetchall()
            for row in rows:
                other_path = self._normalize_path(str(row["path"]))
                if other_path == current:
                    continue
                hits.append(
                    {
                        "path": str(row["path"]),
                        "title": str(row["title"]),
                        "excerpt": str(row["body_excerpt"] or "")[:500],
                    }
                )
        finally:
            conn.close()
        return hits

    def _chroma_consistency_hits(self, note_path: str, claim: str) -> list[dict[str, str]]:
        retrieval_cfg = load_retrieval_config()
        collection_name = (
            retrieval_cfg.get("vector", {}).get("collection_name")
            or "otto_gold"
        )
        hits: list[dict[str, str]] = []
        current = self._normalize_path(note_path)
        try:
            import chromadb  # type: ignore
        except Exception:
            return hits
        try:
            client = chromadb.PersistentClient(path=str(self.paths.chroma_path))
            collection = client.get_collection(name=str(collection_name))
            result = collection.query(
                query_texts=[claim[:2000]],
                n_results=4,
                include=["documents", "metadatas"],
            )
        except Exception:
            return hits
        metadatas = (result or {}).get("metadatas") or []
        documents = (result or {}).get("documents") or []
        first_meta = metadatas[0] if metadatas else []
        first_docs = documents[0] if documents else []
        for idx, meta in enumerate(first_meta):
            meta_dict = meta if isinstance(meta, dict) else {}
            path_value = str(meta_dict.get("path") or meta_dict.get("note_path") or "").strip()
            if not path_value:
                continue
            if self._normalize_path(path_value) == current:
                continue
            excerpt = str(first_docs[idx] if idx < len(first_docs) else "")[:500]
            hits.append(
                {
                    "path": path_value,
                    "title": str(meta_dict.get("title") or Path(path_value).stem),
                    "excerpt": excerpt,
                }
            )
        return hits

    @staticmethod
    def _contradiction_score(claim: str, other_text: str) -> tuple[float, str]:
        lower_claim = claim.lower()
        lower_other = other_text.lower()
        pairs = [
            ("increase", "decrease"),
            ("high", "low"),
            ("always", "never"),
            ("must", "optional"),
            ("enabled", "disabled"),
            ("stable", "fragile"),
            ("growth", "decline"),
            ("centralized", "decentralized"),
        ]
        score = 0.0
        reasons: list[str] = []
        for left, right in pairs:
            if left in lower_claim and right in lower_other:
                score += 0.25
                reasons.append(f"{left}↔{right}")
            elif right in lower_claim and left in lower_other:
                score += 0.25
                reasons.append(f"{right}↔{left}")

        for token in ("ready", "safe", "profitable", "resolved"):
            if f"not {token}" in lower_claim and token in lower_other:
                score += 0.25
                reasons.append(f"not {token}↔{token}")
            elif token in lower_claim and f"not {token}" in lower_other:
                score += 0.25
                reasons.append(f"{token}↔not {token}")
        return min(score, 1.0), ", ".join(reasons)

    def _score_dimensions(
        self,
        note_row: dict[str, Any],
        claim: str,
        consistency_hits: int,
    ) -> tuple[float, float, float, float, float]:
        folder = str(note_row.get("folder", "")).lower()
        tags = self._json_list(note_row.get("tags_json"))
        links = self._json_list(note_row.get("wikilinks_json"))
        scarcity = self._json_list(note_row.get("scarcity"))
        lower = claim.lower()

        utility = 2.5
        if folder in {"projects", "areas", "otto-realm", ".otto-realm"}:
            utility += 2.0
        if any(word in lower for word in ("economic", "revenue", "income", "career", "market", "pricing", "risk")):
            utility += 2.0
        if self._wellness_signal_terms(claim):
            utility += 1.0
        if any(word in lower for word in ("repair", "strategy", "action", "plan", "next step", "task")):
            utility += 1.0

        vault_alignment = 2.0
        if str(note_row.get("frontmatter_text", "")).strip():
            vault_alignment += 2.0
        if tags:
            vault_alignment += 1.0
        if links:
            vault_alignment += 1.0
        vault_alignment += min(consistency_hits, 3) * 1.2

        insight_density = 2.0
        token_count = len(_TOKEN_RE.findall(claim))
        if token_count >= 150:
            insight_density += 2.5
        elif token_count >= 80:
            insight_density += 1.5
        if scarcity:
            insight_density += 1.0
        if note_row.get("orientation"):
            insight_density += 1.0
        if note_row.get("allocation"):
            insight_density += 0.8
        clusters = self._json_list(note_row.get("cluster_membership"))
        if clusters:
            insight_density += 0.7

        actionability = 2.0
        if note_row.get("necessity") not in (None, ""):
            actionability += 1.5
        if any(word in lower for word in ("should", "must", "need to", "next", "repair", "implement", "ship")):
            actionability += 2.0
        if any(word in lower for word in ("owner", "deadline", "today", "tomorrow", "week")):
            actionability += 1.0
        if links:
            actionability += 0.5

        temporal_durability = 3.0
        if any(word in lower for word in ("principle", "system", "architecture", "strategy", "pattern")):
            temporal_durability += 2.0
        if any(word in lower for word in ("incident", "today only", "temporary", "quick fix")):
            temporal_durability -= 1.0
        if len(_DATE_RE.findall(claim)) > 2:
            temporal_durability -= 0.8

        return (
            max(0.0, min(10.0, utility)),
            max(0.0, min(10.0, vault_alignment)),
            max(0.0, min(10.0, insight_density)),
            max(0.0, min(10.0, actionability)),
            max(0.0, min(10.0, temporal_durability)),
        )

    def score_signals(self, limit: int = 24) -> KairosGoldResult:
        rows = self._candidate_notes(limit=limit)
        high_value_folders = self._high_value_folders()
        scored: list[GoldSignalScore] = []
        contradictions: list[GoldContradiction] = []
        contradiction_keys: set[tuple[str, str]] = set()
        dynamic_thresholds: dict[str, float] = {}
        category_counts: dict[str, int] = {}
        category_promoted_counts: dict[str, int] = {}

        for row in rows:
            note_path = str(row.get("path", ""))
            claim = self.build_claim_for_signal(row)
            category, category_reason = self._infer_category(row, claim)
            category_counts[category] = category_counts.get(category, 0) + 1
            sqlite_hits = self._sqlite_consistency_hits(note_path, claim)
            chroma_hits = self._chroma_consistency_hits(note_path, claim)
            all_hits = sqlite_hits + chroma_hits

            for hit in all_hits:
                confidence, reason = self._contradiction_score(claim, hit.get("excerpt", ""))
                if confidence < 0.6:
                    continue
                key = (self._normalize_path(note_path), self._normalize_path(hit.get("path", "")))
                if key in contradiction_keys:
                    continue
                contradiction_keys.add(key)
                contradictions.append(
                    GoldContradiction(
                        note_path=note_path,
                        conflicting_path=str(hit.get("path", "")),
                        primary_claim=claim[:420],
                        conflicting_excerpt=str(hit.get("excerpt", ""))[:420],
                        confidence=confidence,
                        reason=reason or "semantic polarity clash",
                    )
                )

            profile = self._category_profile(category)
            threshold = profile.get("threshold", self.DEFAULT_PROFILE["threshold"])
            file_threshold = self._dynamic_threshold(note_path, high_value_folders)
            threshold = min(threshold, file_threshold) if file_threshold else threshold
            dynamic_thresholds[note_path] = threshold
            utility, vault_alignment, insight_density, actionability, temporal_durability = self._score_dimensions(
                row,
                claim,
                consistency_hits=len(all_hits),
            )
            weights = profile.get("weights", self.DEFAULT_PROFILE["weights"])
            total = (
                utility * weights["utility"]
                + vault_alignment * weights["vault_alignment"]
                + insight_density * weights["insight_density"]
                + actionability * weights["actionability"]
                + temporal_durability * weights["temporal_durability"]
            )
            promoted = total >= threshold
            note_flags: list[str] = []
            if len(all_hits) == 0:
                note_flags.append("weak-consistency-context")
            if promoted and row.get("folder", "").lower() in {"projects", "areas"}:
                note_flags.append("core-path-tight-threshold")
            note_flags.append(f"category:{category}")
            scored.append(
                GoldSignalScore(
                    note_path=note_path,
                    title=str(row.get("title", "")),
                    folder=str(row.get("folder", "")),
                    category=category,
                    category_reason=category_reason,
                    primary_claim=claim[:900],
                    utility=utility,
                    vault_alignment=vault_alignment,
                    insight_density=insight_density,
                    actionability=actionability,
                    temporal_durability=temporal_durability,
                    total_score=total,
                    threshold=threshold,
                    promoted=promoted,
                    consistency_hits=len(all_hits),
                    notes=note_flags,
                )
            )
            if promoted:
                category_promoted_counts[category] = category_promoted_counts.get(category, 0) + 1

        scored.sort(key=lambda item: item.total_score, reverse=True)
        promoted_paths = [item.note_path for item in scored if item.promoted]
        silver_count = 0
        noise_count = 0
        for item in scored:
            silver_floor = max(3.45, item.threshold - 0.30)
            if item.total_score >= item.threshold:
                continue
            if item.total_score >= silver_floor:
                silver_count += 1
            else:
                noise_count += 1
        kairos_score = sum(item.total_score for item in scored) / max(len(scored), 1)
        result = KairosGoldResult(
            ts=now_iso(),
            kairos_score=kairos_score,
            gold_promoted_count=len(promoted_paths),
            silver_count=silver_count,
            noise_count=noise_count,
            category_counts=category_counts,
            category_promoted_counts=category_promoted_counts,
            scored_signals=scored,
            contradictions=contradictions,
            dynamic_thresholds=dynamic_thresholds,
            promoted_paths=promoted_paths,
        )
        self._persist(result)
        self.logger.info(
            "[kairos.gold] scored=%s promoted=%s contradictions=%s",
            len(scored),
            result.gold_promoted_count,
            len(contradictions),
        )
        return result

    def _persist(self, result: KairosGoldResult) -> None:
        write_json(self.paths.state_root / "kairos" / "gold_scored_latest.json", result.as_dict())
        write_json(
            self.paths.state_root / "kairos" / "training_candidates.json",
            {
                "ts": result.ts,
                "count": result.gold_promoted_count,
                "paths": result.promoted_paths,
                "candidates": [item.as_dict() for item in result.scored_signals if item.promoted],
            },
        )
        append_jsonl(
            self.paths.state_root / "run_journal" / "kairos_gold_scores.jsonl",
            {
                "ts": result.ts,
                "kairos_score": result.kairos_score,
                "gold_promoted_count": result.gold_promoted_count,
                "silver_count": result.silver_count,
                "noise_count": result.noise_count,
                "promoted_paths": result.promoted_paths,
            },
        )
        for item in result.contradictions:
            append_jsonl(
                self.paths.state_root / "run_journal" / "contradiction_signals.jsonl",
                {
                    "ts": result.ts,
                    "note_path": item.note_path,
                    "conflicting_path": item.conflicting_path,
                    "primary_claim": item.primary_claim,
                    "conflicting_excerpt": item.conflicting_excerpt,
                    "confidence": item.confidence,
                    "reason": item.reason,
                    "resolved": False,
                },
            )
