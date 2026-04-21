from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None

from ..config import load_paths, load_retrieval_config
from ..db import pg_available, write_signals
from ..logging_utils import append_jsonl, get_logger
from ..state import now_iso


WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
NEGATION_RE = re.compile(r"\b(no|not|never|without|lack|lacks|missing|failed|failure|cannot|can't|won't)\b", re.I)
ACTION_RE = re.compile(r"\b(fix|repair|add|write|review|resolve|rerun|implement|create|update|remove|audit|check)\b", re.I)
TIMEBOUND_RE = re.compile(r"\b(today|tomorrow|yesterday|this week|breaking|urgent|latest|current|recently)\b", re.I)
EVERGREEN_RE = re.compile(r"\b(pattern|system|structure|habit|workflow|process|governance|architecture|trajectory|signal)\b", re.I)


@dataclass
class VaultMatch:
    path: str
    title: str
    source: str
    similarity: float
    excerpt: str


@dataclass
class VaultConsistencyResult:
    primary_claim: str
    matches: list[VaultMatch] = field(default_factory=list)
    consistent: bool = False
    contradiction: bool = False
    merge_recommended: bool = False
    best_similarity: float = 0.0
    reason: str = "no relevant match found"


@dataclass
class ScoreBreakdown:
    utility: float
    vault_alignment: float
    insight_density: float
    actionability: float
    temporal_durability: float


@dataclass
class GoldScore:
    note_path: str
    primary_claim: str
    signal_type: str
    weighted_score: float
    gold_threshold: float
    band: str
    breakdown: ScoreBreakdown
    consistency: VaultConsistencyResult
    recommended_action: str
    gold_promoted: bool


@dataclass
class ContradictionSignal:
    ts: str
    note_path: str
    conflicting_path: str
    primary_claim: str
    conflicting_excerpt: str
    similarity: float
    confidence_delta: float
    resolution_task: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "note_path": self.note_path,
            "conflicting_path": self.conflicting_path,
            "primary_claim": self.primary_claim,
            "conflicting_excerpt": self.conflicting_excerpt,
            "similarity": round(self.similarity, 3),
            "confidence_delta": round(self.confidence_delta, 3),
            "resolution_task": self.resolution_task,
        }


class GoldScoringEngine:
    GOLD_THRESHOLD = 6.5
    SILVER_THRESHOLD = 4.0
    # Phase 2: set use_full_body=True once inline LLM is wired for claim enrichment
    USE_FULL_BODY = False

    def __init__(self) -> None:
        self.paths = load_paths()
        self._logger = get_logger("otto.kairos.gold")
        try:
            from ..models import choose_model
            self._scoring_model = choose_model("gold_scoring")
        except Exception:
            self._scoring_model = None

    def _tokenize(self, text: str) -> set[str]:
        return {m.group(0).lower() for m in WORD_RE.finditer(text or "")}

    def _similarity(self, left: str, right: str) -> float:
        left_tokens = self._tokenize(left)
        right_tokens = self._tokenize(right)
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)

    def _fetch_note_full(self, note_path: str) -> tuple[str, str, str, str]:
        """Return (title, frontmatter_text, body_excerpt, tags_str) for scoring."""
        if not self.paths.sqlite_path.exists():
            return "", "", "", ""
        conn = sqlite3.connect(self.paths.sqlite_path)
        try:
            row = conn.execute(
                """
                SELECT
                    COALESCE(title, ''),
                    COALESCE(frontmatter_text, ''),
                    COALESCE(body_excerpt, ''),
                    COALESCE(tags, '')
                FROM notes
                WHERE REPLACE(path, '/', '\\') = REPLACE(?, '/', '\\')
                LIMIT 1
                """,
                (note_path,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return "", "", "", ""
        return str(row[0] or ""), str(row[1] or ""), str(row[2] or ""), str(row[3] or "")

    def _candidate_rows(self, primary_claim: str, note_path: str | None = None, limit: int = 12) -> list[tuple[str, str, str]]:
        if not self.paths.sqlite_path.exists():
            return []
        tokens = sorted(self._tokenize(primary_claim), key=len, reverse=True)[:5]
        like_terms = [f"%{token}%" for token in tokens] or ["%%"]

        clauses = ["(title LIKE ? OR frontmatter_text LIKE ? OR body_excerpt LIKE ?)"]
        params: list[Any] = [like_terms[0], like_terms[0], like_terms[0]]
        for term in like_terms[1:]:
            clauses.append("(title LIKE ? OR frontmatter_text LIKE ? OR body_excerpt LIKE ?)")
            params.extend([term, term, term])

        sql = f"""
            SELECT path, COALESCE(title, ''), COALESCE(body_excerpt, '')
            FROM notes
            WHERE ({' OR '.join(clauses)})
        """
        if note_path:
            sql += " AND REPLACE(path, '/', '\\') != REPLACE(?, '/', '\\')"
            params.append(note_path)
        sql += " ORDER BY mtime DESC LIMIT ?"
        params.append(limit)

        conn = sqlite3.connect(self.paths.sqlite_path)
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]

    def _chroma_matches(self, primary_claim: str, limit: int = 5) -> list[VaultMatch]:
        if chromadb is None:
            return []
        cfg = load_retrieval_config()
        collection_name = str(cfg.get("vector", {}).get("collection_name", "otto_gold"))
        try:
            client = chromadb.PersistentClient(path=str(self.paths.chroma_path))
            coll = client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
            result = coll.query(
                query_texts=[primary_claim],
                n_results=limit,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []

        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]
        matches: list[VaultMatch] = []
        for doc, meta, distance in zip(documents[0], metadatas[0], distances[0]):
            similarity = max(0.0, 1.0 - float(distance or 1.0))
            matches.append(
                VaultMatch(
                    path=str((meta or {}).get("path", "")),
                    title=str((meta or {}).get("title", "")),
                    source="chroma",
                    similarity=round(similarity, 3),
                    excerpt=str(doc or "")[:220],
                )
            )
        return matches

    def _detect_contradiction(self, left: str, right: str) -> bool:
        shared = self._tokenize(left) & self._tokenize(right)
        if len(shared) < 3:
            return False
        return bool(NEGATION_RE.search(left)) != bool(NEGATION_RE.search(right))

    def _is_core_path(self, note_path: str) -> bool:
        lowered = note_path.replace("/", "\\").lower()
        return (
            lowered.startswith("projects\\")
            or lowered.startswith("areas\\")
            or lowered.startswith("otto-realm\\brain\\")
        )

    def _path_importance(self, note_path: str) -> float:
        lowered = note_path.replace("/", "\\").lower()
        if lowered.startswith("otto-realm\\brain\\"):
            return 2.0
        if lowered.startswith("projects\\"):
            return 1.6
        if lowered.startswith("areas\\"):
            return 1.2
        if lowered.startswith("otto-realm\\predictions\\"):
            return 0.8
        return 0.0

    def vault_consistency_check(self, primary_claim: str, note_path: str | None = None) -> VaultConsistencyResult:
        matches: list[VaultMatch] = []
        for path, title, excerpt in self._candidate_rows(primary_claim, note_path=note_path):
            similarity = self._similarity(primary_claim, f"{title}\n{excerpt}")
            if similarity < 0.2:
                continue
            matches.append(VaultMatch(path=path, title=title, source="sqlite", similarity=round(similarity, 3), excerpt=excerpt[:220]))
        matches.extend(self._chroma_matches(primary_claim))

        deduped: dict[str, VaultMatch] = {}
        for match in matches:
            if not match.path:
                continue
            current = deduped.get(match.path)
            if current is None or match.similarity > current.similarity:
                deduped[match.path] = match
        ranked = sorted(deduped.values(), key=lambda item: item.similarity, reverse=True)[:5]

        result = VaultConsistencyResult(primary_claim=primary_claim, matches=ranked)
        if not ranked:
            return result

        best = ranked[0]
        result.best_similarity = best.similarity
        result.contradiction = best.similarity >= 0.35 and self._detect_contradiction(primary_claim, best.excerpt)
        result.consistent = best.similarity >= 0.8 and not result.contradiction
        result.merge_recommended = result.consistent
        if result.merge_recommended:
            result.reason = f"merge with {best.path} (semantic overlap {best.similarity:.2f})"
        elif result.contradiction:
            result.reason = f"contradiction with {best.path} requires reconciliation"
        else:
            result.reason = f"new signal distinct from closest match {best.path}"
        return result

    def _utility_score(
        self,
        text: str,
        signal_type: str,
        *,
        note_path: str,
        signal_score: float | None,
        factors: dict[str, Any] | None,
    ) -> float:
        text_lower = text.lower()
        score = 4.0
        keyword_groups = {
            "economic": ["economic", "revenue", "income", "market", "pricing", "asset", "fragility", "career"],
            "wellbeing": ["wellbeing", "sleep", "stress", "health", "friction", "clarity", "confusion"],
            "system": ["vault", "metadata", "retrieval", "training", "frontmatter", "signal", "governance"],
        }
        for words in keyword_groups.values():
            if any(word in text_lower for word in words):
                score += 1.2
        if signal_type in {"contradiction", "economic", "chaos"}:
            score += 1.1
        score += self._path_importance(note_path)
        if signal_score is not None:
            score += min(max(signal_score, 0.0) * 0.22, 1.4)
        if isinstance(factors, dict):
            factor_text = " ".join(f"{k}={v}" for k, v in factors.items()).lower()
            if any(term in factor_text for term in ["economic", "career", "wellbeing", "vault", "metadata", "contradiction"]):
                score += 0.6
        factor_count = len(factors or {})
        if factor_count >= 4:
            score += 0.7
        if isinstance(factors, dict) and {"no_frontmatter", "no_wikilinks"} <= set(factors.keys()):
            score += 0.4
        return min(score, 10.0)

    def _insight_score(self, text: str, *, signal_score: float | None, factors: dict[str, Any] | None) -> float:
        score = 3.5
        token_count = len(self._tokenize(text))
        if token_count >= 15:
            score += 1.5
        if token_count >= 30:
            score += 1.0
        structural_terms = ["pattern", "cause", "because", "therefore", "system", "trajectory", "signal", "risk"]
        score += min(sum(1 for term in structural_terms if term in text.lower()) * 0.5, 3.0)
        if signal_score is not None and signal_score >= 5.0:
            score += 0.8
        if isinstance(factors, dict):
            structural_factor_hits = sum(
                1 for key in factors.keys()
                if any(term in str(key).lower() for term in ["cause", "pattern", "signal", "risk", "contradiction", "staleness"])
            )
            score += min(structural_factor_hits * 0.35, 1.2)
        if len(factors or {}) >= 4:
            score += 0.7
        return min(score, 10.0)

    def _actionability_score(
        self,
        text: str,
        *,
        note_path: str,
        signal_score: float | None,
        factors: dict[str, Any] | None,
    ) -> float:
        score = 3.0
        if ACTION_RE.search(text):
            score += 3.5
        if any(marker in text for marker in ["TODO", "Next", "must", "needs", "should"]):
            score += 1.5
        if "[[" in text or "\\" in text or "/" in text:
            score += 1.0
        if self._is_core_path(note_path):
            score += 0.8
        if signal_score is not None and signal_score >= 4.0:
            score += 1.0
        if isinstance(factors, dict) and any(str(v).lower() in {"fix", "repair", "resolve", "review"} for v in factors.values()):
            score += 0.5
        if len(factors or {}) >= 3:
            score += 0.7
        return min(score, 10.0)

    def _durability_score(self, text: str, *, signal_type: str, signal_score: float | None) -> float:
        score = 5.0
        if EVERGREEN_RE.search(text):
            score += 2.0
        if TIMEBOUND_RE.search(text):
            score -= 1.5
        if re.search(r"\b20\d{2}\b", text):
            score -= 0.5
        if signal_type in {"chaos", "contradiction"}:
            score += 0.5
        if signal_score is not None and signal_score >= 5.0:
            score += 0.5
        return max(0.0, min(score, 10.0))

    def _vault_alignment_score(
        self,
        consistency: VaultConsistencyResult,
        *,
        note_path: str,
        signal_type: str,
        signal_score: float | None,
        factors: dict[str, Any] | None,
    ) -> float:
        if consistency.consistent:
            return 8.5
        if consistency.contradiction:
            return 7.0
        if consistency.matches:
            return 5.0
        score = 4.5
        if self._is_core_path(note_path):
            score += 1.0
        if signal_type in {"chaos", "contradiction"}:
            score += 0.3
        if signal_score is not None and signal_score >= 5.0:
            score += 0.4
        if len(factors or {}) >= 4:
            score += 0.3
        return min(score, 10.0)

    def _gold_threshold(
        self,
        *,
        note_path: str,
        signal_type: str,
        signal_score: float | None,
        factors: dict[str, Any] | None,
    ) -> float:
        threshold = self.GOLD_THRESHOLD
        if signal_type == "contradiction":
            return 6.0
        if self._is_core_path(note_path) and (signal_score or 0.0) >= 5.0 and len(factors or {}) >= 4:
            return 6.1
        if self._is_core_path(note_path) and (signal_score or 0.0) >= 4.0:
            return 6.25
        return threshold

    def _noise_filter(self, text: str, *, note_path: str, signal_type: str, factors: dict[str, Any] | None) -> bool:
        """Return True if this signal should be classified as noise (discard unless override)."""
        text_lower = text.lower()
        factors = factors or {}
        factors_lower = {str(k).lower(): str(v).lower() for k, v in factors.items()}

        # 1. Emotional venting without delta — frustration expressed but no new signal about Joshua's state
        venting_indicators = ["frustration", "angry", "annoyed", "ugh", "dammit", "hate this"]
        has_venting = any(v in text_lower for v in venting_indicators)
        has_structural = any(term in text_lower for term in ["pattern", "because", "system", "signal", "therefore"])
        if has_venting and not has_structural and not factors.get("override"):
            return True

        # 2. Dead-end rabbit holes — no utility vector to Joshua's actual life (no economic/wellbeing/system keyword within 2 hops)
        connected_domains = ["economic", "revenue", "career", "wellbeing", "vault", "metadata", "governance",
                             "project", "system", "execution", "health", "asset", "training", "signal"]
        has_connection = any(domain in text_lower for domain in connected_domains)
        if not has_connection and len(text.split()) < 20:
            return True

        # 3. Attention-capture content — high subjective interest markers
        bait_indicators = ["shocking", "you won't believe", "must watch", "viral", "breaking news"]
        has_bait = any(b in text_lower for b in bait_indicators)
        if has_bait:
            return True

        # 4. Premature synthesis — conclusions about Joshua's character/capabilities before evidence
        premature_personality = ["i am", "i'm a", "i always", "i never", "i can't", "destined", "born to"]
        premature_indicators = ["probably", "seems like", "might be", "appears to be"]
        has_premature = any(p in text_lower for p in premature_personality) and any(i in text_lower for i in premature_indicators)
        if has_premature:
            return True

        # 5. Gossip and social theater — interpersonal drama with no structural lesson
        drama_keywords = ["drama", "betrayal", "he said", "she said", "conflict between", "feud"]
        has_drama = any(d in text_lower for d in drama_keywords)
        structural_in_others = any(term in text_lower for term in ["pattern", "human behavior", "incentive", "causality"])
        if has_drama and not structural_in_others:
            return True

        return False

    def _wellbeing_inflection(
        self,
        text: str,
        signal_type: str,
        signal_score: float | None,
        factors: dict[str, Any] | None,
    ) -> float:
        """Detect wellbeing inflection point bonus for Gold taxonomy §1.4."""
        text_lower = text.lower()
        bonus = 0.0
        transitions = [
            ("flow", "friction"), ("clarity", "confusion"), ("energy", "drain"),
            ("focus", "scatter"), ("momentum", "stall"),
        ]
        for pos, neg in transitions:
            if pos in text_lower and neg in text_lower:
                bonus += 1.5
        if signal_type in {"contradiction", "economic", "chaos"}:
            bonus += 0.8
        if any(term in text_lower for term in ["inflection", "tipping point", "transition"]):
            bonus += 1.2
        return min(bonus, 3.0)

    def score_signal(
        self,
        *,
        note_path: str,
        primary_claim: str,
        signal_type: str = "general",
        signal_score: float | None = None,
        factors: dict[str, Any] | None = None,
        override: bool = False,
    ) -> GoldScore:
        # Noise filter: discard unless override flag is set
        if not override and self._noise_filter(primary_claim, note_path=note_path, signal_type=signal_type, factors=factors):
            return GoldScore(
                note_path=note_path,
                primary_claim=primary_claim,
                signal_type=signal_type,
                weighted_score=0.0,
                gold_threshold=self.GOLD_THRESHOLD,
                band="noise",
                breakdown=ScoreBreakdown(utility=0.0, vault_alignment=0.0, insight_density=0.0, actionability=0.0, temporal_durability=0.0),
                consistency=VaultConsistencyResult(primary_claim=primary_claim),
                recommended_action="Archived as noise — override required to promote",
                gold_promoted=False,
            )

        consistency = self.vault_consistency_check(primary_claim, note_path=note_path)
        utility = self._utility_score(primary_claim, signal_type, note_path=note_path, signal_score=signal_score, factors=factors)
        vault_alignment = self._vault_alignment_score(
            consistency,
            note_path=note_path,
            signal_type=signal_type,
            signal_score=signal_score,
            factors=factors,
        )
        insight_density = self._insight_score(primary_claim, signal_score=signal_score, factors=factors)
        actionability = self._actionability_score(primary_claim, note_path=note_path, signal_score=signal_score, factors=factors)
        temporal_durability = self._durability_score(primary_claim, signal_type=signal_type, signal_score=signal_score)
        # Wellbeing inflection point bonus (Gold taxonomy §1.4)
        temporal_durability = min(temporal_durability + self._wellbeing_inflection(primary_claim, signal_type, signal_score, factors), 10.0)
        gold_threshold = self._gold_threshold(
            note_path=note_path,
            signal_type=signal_type,
            signal_score=signal_score,
            factors=factors,
        )

        weighted = round(
            utility * 0.30
            + vault_alignment * 0.20
            + insight_density * 0.20
            + actionability * 0.15
            + temporal_durability * 0.15,
            3,
        )
        band = "gold" if weighted >= gold_threshold else "silver" if weighted >= self.SILVER_THRESHOLD else "noise"

        if consistency.merge_recommended:
            action = f"Merge with {consistency.matches[0].path}"
        elif consistency.contradiction and consistency.matches:
            action = f"Resolve contradiction with {consistency.matches[0].path}"
        elif band == "gold":
            action = "Promote to Gold"
        elif band == "silver":
            action = "Keep in Silver for review"
        else:
            action = "Archive as noise unless overridden"

        return GoldScore(
            note_path=note_path,
            primary_claim=primary_claim,
            signal_type=signal_type,
            weighted_score=weighted,
            gold_threshold=gold_threshold,
            band=band,
            breakdown=ScoreBreakdown(
                utility=round(utility, 2),
                vault_alignment=round(vault_alignment, 2),
                insight_density=round(insight_density, 2),
                actionability=round(actionability, 2),
                temporal_durability=round(temporal_durability, 2),
            ),
            consistency=consistency,
            recommended_action=action,
            gold_promoted=band == "gold" and not consistency.merge_recommended,
        )

    def build_claim_for_signal(self, signal: dict[str, Any], *, use_full_body: bool = False) -> tuple[str, str]:
        note_path = str(signal.get("note_path", ""))
        signal_type = str(signal.get("signal_type", "general"))
        factors = signal.get("factors") or {}
        title, frontmatter, body, tags = self._fetch_note_full(note_path)
        factor_str = ", ".join(f"{k}={v}" for k, v in factors.items()) if isinstance(factors, dict) else ""

        # Body length: use_full_body=True when inline LLM is wired (Phase 2).
        # Without LLM, longer excerpts improve U/I regex scoring precision.
        body_limit = 10000 if use_full_body else 2000

        content_parts: list[str] = []
        if title:
            content_parts.append(f"Title: {title}")
        if tags:
            content_parts.append(f"Tags: {tags[:120]}")
        if frontmatter:
            content_parts.append(f"Frontmatter: {frontmatter[:400]}")
        if body:
            content_parts.append(f"Body: {body[:body_limit]}")
        if factor_str:
            content_parts.append(f"Factors: {factor_str[:300]}")
        content = " | ".join(content_parts)

        claim = (
            f"{signal_type} signal in {note_path}. "
            f"Tags: {tags[:80]}. "
            f"{content}"
        ).strip()
        return note_path, claim[:800]

    def contradiction_from_score(self, score: GoldScore) -> ContradictionSignal | None:
        if not score.consistency.contradiction or not score.consistency.matches:
            return None
        match = score.consistency.matches[0]
        return ContradictionSignal(
            ts=now_iso(),
            note_path=score.note_path,
            conflicting_path=match.path,
            primary_claim=score.primary_claim,
            conflicting_excerpt=match.excerpt,
            similarity=match.similarity,
            confidence_delta=abs(score.weighted_score - (match.similarity * 10.0)),
            resolution_task=f"Review {score.note_path} against {match.path} and write reconciliation note",
        )

    def emit_contradiction_signal(self, contradiction: ContradictionSignal) -> None:
        append_jsonl(self.paths.state_root / "run_journal" / "contradiction_signals.jsonl", contradiction.as_dict())
        if pg_available():
            try:
                write_signals([
                    {
                        "path": contradiction.note_path,
                        "signal_type": "contradiction",
                        "score": contradiction.similarity,
                        "factors": {
                            "conflicting_path": contradiction.conflicting_path,
                            "resolution_task": contradiction.resolution_task,
                        },
                    }
                ])
            except Exception:
                self._logger.warning("[kairos.gold] could not mirror contradiction signal to Postgres")

    def score_unresolved_signals(self, unresolved_signals: list[dict[str, Any]]) -> tuple[list[GoldScore], list[ContradictionSignal]]:
        scores: list[GoldScore] = []
        contradictions: list[ContradictionSignal] = []
        for signal in unresolved_signals:
            note_path, claim = self.build_claim_for_signal(signal, use_full_body=self.USE_FULL_BODY)
            signal_score = signal.get("score")
            score = self.score_signal(
                note_path=note_path,
                primary_claim=claim,
                signal_type=str(signal.get("signal_type", "general")),
                signal_score=float(signal_score) if signal_score is not None else None,
                factors=signal.get("factors") if isinstance(signal.get("factors"), dict) else {},
            )
            scores.append(score)
            contradiction = self.contradiction_from_score(score)
            if contradiction is not None:
                self.emit_contradiction_signal(contradiction)
                contradictions.append(contradiction)
        return scores, contradictions
