from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..db import pg_available, write_signals
from ..state import now_iso


@dataclass
class ChaosScore:
    path: str
    title: str
    score: float  # higher = more chaotic
    factors: dict[str, float]
    mtime: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "score": round(self.score, 3),
            "factors": {k: round(v, 3) for k, v in self.factors.items()},
            "mtime": self.mtime,
        }


@dataclass
class SignalHit:
    path: str
    title: str
    signal_type: str
    signal_value: str
    confidence: float
    excerpt: str
    mtime: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "signal_type": self.signal_type,
            "signal_value": self.signal_value,
            "confidence": round(self.confidence, 2),
            "excerpt": self.excerpt[:120],
            "mtime": self.mtime,
        }


@dataclass
class RankedResult:
    path: str
    title: str
    rank_score: float
    signal_matches: list[str]
    excerpt: str
    mtime: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "rank_score": round(self.rank_score, 3),
            "signal_matches": self.signal_matches,
            "excerpt": self.excerpt[:150],
            "mtime": self.mtime,
        }


class VaultSignalTools:
    CHAOS_WEIGHTS = {
        "no_frontmatter": 1.5,
        "no_wikilinks": 1.0,
        "no_scarcity": 0.8,
        "no_cluster": 0.7,
        "no_tags": 0.6,
        "no_necessity": 0.5,
        "stale_mtime_days": 0.02,  # per day stale
    }
    CHAOS_STALE_CUTOFF_DAYS = 30

    def __init__(self, bronze_path: Path | None = None):
        paths = load_paths()
        self.bronze_path = bronze_path or (paths.bronze_root / "bronze_manifest.json")
        self.vault_path = paths.vault_path
        self._manifest: dict[str, Any] | None = None

    def _load_manifest(self) -> dict[str, Any]:
        if self._manifest is not None:
            return self._manifest
        if not self.bronze_path.exists():
            return {}
        self._manifest = json.loads(self.bronze_path.read_text(encoding="utf-8"))
        return self._manifest

    def _note_mtime(self, note: dict[str, Any]) -> str:
        mtime_epoch = note.get("mtime", 0)
        if isinstance(mtime_epoch, (int, float)):
            from datetime import datetime, timezone

            return (
                datetime.fromtimestamp(mtime_epoch, tz=timezone.utc)
                .astimezone()
                .isoformat(timespec="seconds")
            )
        return ""

    def list_chaos_to_order(
        self,
        limit: int = 20,
        min_score: float = 0.5,
        focus: str = "all",
    ) -> list[ChaosScore]:
        manifest = self._load_manifest()
        notes: list[dict[str, Any]] = manifest.get("notes", [])
        results: list[ChaosScore] = []

        now_ts = now_iso()
        try:
            from datetime import datetime, timezone

            now_epoch = datetime.now(timezone.utc).timestamp()
        except Exception:
            now_epoch = 0

        for note in notes:
            factors: dict[str, float] = {}
            score = 0.0

            if focus in ("frontmatter", "all"):
                if not note.get("has_frontmatter", False):
                    factors["no_frontmatter"] = self.CHAOS_WEIGHTS["no_frontmatter"]
                    score += factors["no_frontmatter"]

            if focus in ("links", "all"):
                if not note.get("wikilinks"):
                    factors["no_wikilinks"] = self.CHAOS_WEIGHTS["no_wikilinks"]
                    score += factors["no_wikilinks"]

            if focus in ("scarcity", "all"):
                scarcity = note.get("scarcity", [])
                if not scarcity:
                    factors["no_scarcity"] = self.CHAOS_WEIGHTS["no_scarcity"]
                    score += factors["no_scarcity"]

            if focus in ("cluster", "all"):
                clusters = note.get("cluster_membership", [])
                if not clusters:
                    factors["no_cluster"] = self.CHAOS_WEIGHTS["no_cluster"]
                    score += factors["no_cluster"]

            if focus in ("tags", "all"):
                tags = note.get("tags", [])
                if not tags:
                    factors["no_tags"] = self.CHAOS_WEIGHTS["no_tags"]
                    score += factors["no_tags"]

            if focus in ("necessity", "all"):
                if note.get("necessity") is None:
                    factors["no_necessity"] = self.CHAOS_WEIGHTS["no_necessity"]
                    score += factors["no_necessity"]

            if focus in ("stale", "all"):
                mtime_ep = note.get("mtime", 0)
                if isinstance(mtime_ep, (int, float)) and mtime_ep > 0:
                    age_days = (now_epoch - mtime_ep) / 86400
                    if age_days > self.CHAOS_STALE_CUTOFF_DAYS:
                        stale_factor = min(age_days * self.CHAOS_WEIGHTS["stale_mtime_days"], 3.0)
                        factors["stale"] = stale_factor
                        score += stale_factor

            if score < min_score:
                continue

            results.append(
                ChaosScore(
                    path=note.get("path", ""),
                    title=note.get("title", ""),
                    score=score,
                    factors=factors,
                    mtime=self._note_mtime(note),
                )
            )

        results.sort(key=lambda x: -x.score)
        ranked = results[:limit]
        # Persist chaos scores to Postgres vault_signals table
        if pg_available():
            try:
                signal_records = [
                    {
                        "path": c.path,
                        "signal_type": "chaos",
                        "score": c.score,
                        "factors": c.factors,
                    }
                    for c in ranked
                ]
                write_signals(signal_records)
            except Exception:
                pass  # Postgres write is best-effort
        return ranked

    def search_signals(
        self,
        signal_type: str,
        value: str | None = None,
        limit: int = 20,
    ) -> list[SignalHit]:
        manifest = self._load_manifest()
        notes: list[dict[str, Any]] = manifest.get("notes", [])
        hits: list[SignalHit] = []

        valid_types = {
            "scarcity",
            "tag",
            "cluster",
            "orientation",
            "allocation",
            "necessity",
            "frontmatter_missing",
            "orphan",
        }
        if signal_type not in valid_types:
            return []

        for note in notes:
            match_val = ""
            confidence = 0.0

            if signal_type == "scarcity":
                scarcity_list: list[str] = note.get("scarcity", [])
                if value:
                    matched = [s for s in scarcity_list if value.lower() in s.lower()]
                    if matched:
                        match_val = matched[0]
                        confidence = 0.9
                else:
                    if scarcity_list:
                        match_val = ", ".join(scarcity_list[:3])
                        confidence = 0.8

            elif signal_type == "tag":
                tags: list[str] = note.get("tags", [])
                matched_tags = [t for t in tags if not value or value.lower() in t.lower()]
                if matched_tags:
                    match_val = matched_tags[0]
                    confidence = 0.85

            elif signal_type == "cluster":
                clusters: list[str] = note.get("cluster_membership", [])
                matched_c = [c for c in clusters if not value or value.lower() in c.lower()]
                if matched_c:
                    match_val = matched_c[0]
                    confidence = 0.9

            elif signal_type == "orientation":
                orient = note.get("orientation")
                if orient and (not value or value.lower() in str(orient).lower()):
                    match_val = str(orient)
                    confidence = 0.85

            elif signal_type == "allocation":
                alloc = note.get("allocation")
                if alloc and (not value or value.lower() in str(alloc).lower()):
                    match_val = str(alloc)
                    confidence = 0.85

            elif signal_type == "necessity":
                nec = note.get("necessity")
                if nec is not None and (value is None or str(nec) == value):
                    match_val = str(nec)
                    confidence = 0.8

            elif signal_type == "frontmatter_missing":
                if not note.get("has_frontmatter", False):
                    match_val = "missing"
                    confidence = 0.95

            elif signal_type == "orphan":
                if not note.get("wikilinks") and not note.get("tags"):
                    match_val = "orphan"
                    confidence = 0.9

            if match_val:
                excerpt = note.get("body_excerpt", "")[:200]
                hits.append(
                    SignalHit(
                        path=note.get("path", ""),
                        title=note.get("title", ""),
                        signal_type=signal_type,
                        signal_value=match_val,
                        confidence=confidence,
                        excerpt=excerpt,
                        mtime=self._note_mtime(note),
                    )
                )

        hits.sort(key=lambda x: -x.confidence)
        ranked = hits[:limit]
        # Persist signal hits to Postgres
        if pg_available():
            try:
                signal_records = [
                    {
                        "path": h.path,
                        "signal_type": h.signal_type,
                        "score": h.confidence,
                        "factors": {"signal_value": h.signal_value, "excerpt": h.excerpt[:100]},
                    }
                    for h in ranked
                ]
                write_signals(signal_records)
            except Exception:
                pass
        return ranked

    def rank_vault_search(
        self,
        query: str,
        limit: int = 15,
        signal_focus: list[str] | None = None,
    ) -> list[RankedResult]:
        manifest = self._load_manifest()
        notes: list[dict[str, Any]] = manifest.get("notes", [])
        results: list[RankedResult] = []

        if signal_focus is None:
            signal_focus = ["scarcity", "tag", "cluster", "necessity"]

        query_terms = query.lower().split()

        for note in notes:
            path = note.get("path", "")
            title = note.get("title", "")
            body = note.get("body_excerpt", "")
            all_text = f"{title} {body}".lower()

            term_matches = sum(1 for t in query_terms if t in all_text)
            if term_matches == 0:
                continue

            text_score = term_matches / max(len(query_terms), 1)

            signal_matches: list[str] = []
            signal_score = 0.0

            if "scarcity" in signal_focus:
                scarcity: list[str] = note.get("scarcity", [])
                for s in scarcity:
                    if any(t in s.lower() for t in query_terms):
                        signal_matches.append(f"scarcity:{s}")
                        signal_score += 0.5

            if "tag" in signal_focus:
                tags: list[str] = note.get("tags", [])
                for t in tags:
                    if any(term in t.lower() for term in query_terms):
                        signal_matches.append(f"tag:{t}")
                        signal_score += 0.4

            if "cluster" in signal_focus:
                clusters: list[str] = note.get("cluster_membership", [])
                for c in clusters:
                    if any(term in c.lower() for term in query_terms):
                        signal_matches.append(f"cluster:{c}")
                        signal_score += 0.6

            if "necessity" in signal_focus:
                nec = note.get("necessity")
                if nec is not None:
                    nec_str = str(nec).lower()
                    if any(term in nec_str for term in query_terms):
                        signal_matches.append(f"necessity:{nec}")
                        signal_score += 0.7

            rank_score = (text_score * 1.0) + (signal_score * 0.5)
            rank_score = min(rank_score, 5.0)

            results.append(
                RankedResult(
                    path=path,
                    title=title,
                    rank_score=rank_score,
                    signal_matches=signal_matches,
                    excerpt=body[:200],
                    mtime=self._note_mtime(note),
                )
            )

        results.sort(key=lambda x: -x.rank_score)
        return results[:limit]
