from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

import yaml

from ..config import load_paths, load_retrieval_config
from ..logging_utils import append_jsonl, get_logger
from ..state import now_iso, read_json
from .hybrid import reciprocal_rank_fusion

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None


_RELATION_HINT_FIELDS = (
    "allocation",
    "orientation",
    "scarcity",
    "family",
    "domain",
    "cluster",
    "pillar",
    "program",
    "topic",
    "topics",
    "concern",
    "concerns",
    "problem",
    "problems",
    "mode",
    "type",
)


def _fts_query(query: str) -> str:
    tokens = [token for token in query.replace("-", " ").split() if token.strip()]
    return " ".join(tokens) if tokens else query.strip()


def _dedupe_variants(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
    return deduped


def _query_tokens(query: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", query)]


def _pluralize_token(token: str) -> str:
    lowered = token.lower()
    if lowered.endswith("s"):
        return lowered
    if lowered.endswith("y") and len(lowered) > 1 and lowered[-2] not in "aeiou":
        return lowered[:-1] + "ies"
    return lowered + "s"


def _is_phrase_like_technical_query(query: str) -> bool:
    tokens = _query_tokens(query)
    if " " not in query.strip():
        return False
    if len(tokens) < 2 or len(tokens) > 3:
        return False
    return all(len(token) >= 4 for token in tokens)


def _query_variants(query: str) -> list[str]:
    raw = query.strip()
    if not raw:
        return []

    variants: list[str] = [raw]
    hyphen_normalized = " ".join(token for token in raw.replace("-", " ").split() if token.strip())
    if hyphen_normalized:
        variants.append(hyphen_normalized)

    token_clean = " ".join(re.findall(r"[A-Za-z0-9]+", raw))
    if token_clean:
        variants.append(token_clean)

    return _dedupe_variants(variants)


def _dense_query_variants(query: str) -> list[str]:
    base = _query_variants(query)
    raw = query.strip()
    tokens = _query_tokens(raw)
    if not raw or not _is_phrase_like_technical_query(raw):
        return base

    variants = list(base)
    if len(tokens) >= 2:
        left, right = tokens[0], tokens[1]
        variants.extend(
            [
                f"{left}-{right}",
                f"{left} {_pluralize_token(right)}",
                f"{right} {left}",
            ]
        )
        if {left, right} & {"semantic", "embedding", "embeddings", "vector"}:
            variants.extend(
                [
                    f"{left} vector",
                    f"vector {right}",
                    f"{right} vector",
                ]
            )

    if tokens[:2] == ["semantic", "vector"]:
        variants.extend(
            [
                "semantic embedding",
                "semantic embeddings",
                "vector embedding",
                "embedding vector",
            ]
        )
    if tokens[:2] == ["semantic", "embedding"] or tokens[:2] == ["semantic", "embeddings"]:
        variants.extend(
            [
                "semantic vector",
                "vector embedding",
                "embedding vector",
            ]
        )

    return _dedupe_variants(variants)


def _sparse_query_variants(query: str) -> list[str]:
    base = _query_variants(query)
    tokens = _query_tokens(query)
    if not _is_phrase_like_technical_query(query):
        return base

    variants = list(base)
    if tokens[:2] == ["semantic", "vector"]:
        variants.extend(["semantic embedding", "semantic embeddings"])
    if tokens[:2] == ["semantic", "embedding"] or tokens[:2] == ["semantic", "embeddings"]:
        variants.append("semantic vector")
    return _dedupe_variants(variants)


def _normalize_path(value: str | None) -> str:
    return str(value or "").replace("\\", "/").strip().lower()


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip().lower()


def _is_meta_schema_path(path: str | None) -> bool:
    normalized = _normalize_path(path)
    return normalized.startswith("00-meta/")


def _is_otto_runtime_path(path: str | None) -> bool:
    normalized = _normalize_path(path)
    return normalized.startswith(".otto-realm/") or normalized.startswith("otto-realm/")


def _ranking_cfg() -> dict[str, Any]:
    cfg = load_retrieval_config()
    return cfg.get("retrieval", {}).get("ranking", {})


def _vector_cfg() -> dict[str, Any]:
    cfg = load_retrieval_config()
    return cfg.get("vector", {})


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}
    except sqlite3.Error:
        return set()


def _matches_any_prefix(path: str, prefixes: list[str]) -> bool:
    normalized = _normalize_path(path)
    return any(normalized.startswith(_normalize_path(prefix)) for prefix in prefixes)


def _matches_any_suffix(path: str, suffixes: list[str]) -> bool:
    normalized = _normalize_path(path)
    return any(normalized.endswith(_normalize_path(suffix)) for suffix in suffixes)


def _noise_flags(hit: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    path = str(hit.get("path") or "")
    title = _normalize_text(hit.get("title"))
    flags: list[str] = []
    if _matches_any_prefix(path, list(cfg.get("penalize_prefixes", []) or [])):
        flags.append("penalized_prefix")
    if _matches_any_suffix(path, list(cfg.get("penalize_suffixes", []) or [])):
        flags.append("penalized_suffix")
    if title in {_normalize_text(item) for item in list(cfg.get("penalize_titles", []) or [])}:
        flags.append("penalized_title")
    return flags


def _exclude_hit(hit: dict[str, Any], cfg: dict[str, Any]) -> bool:
    path = str(hit.get("path") or "")
    return _matches_any_prefix(path, list(cfg.get("exclude_prefixes", []) or []))


def _quality_bonus(hit: dict[str, Any], cfg: dict[str, Any]) -> float:
    bonus = 0.0
    if str(hit.get("frontmatter_text") or "").strip():
        bonus += float(cfg.get("frontmatter_bonus", 0.15) or 0.0)
    title = _normalize_text(hit.get("title"))
    if title and title not in {_normalize_text(item) for item in list(cfg.get("penalize_titles", []) or [])}:
        bonus += float(cfg.get("title_bonus", 0.05) or 0.0)
    return bonus


def _source_support_boost(hit: dict[str, Any]) -> float:
    sources = list(hit.get("sources", []) or [])
    support_count = len({str(source).strip().lower() for source in sources if str(source).strip()})
    if support_count <= 1:
        return 0.0
    return 0.1 * float(support_count - 1)


def _frontmatter_map(frontmatter_text: str | None) -> dict[str, Any]:
    text = str(frontmatter_text or "").strip()
    if not text:
        return {}
    try:
        payload = yaml.safe_load(text)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_relation_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = re.sub(r"\s+", " ", value).strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_coerce_relation_values(item))
        return _dedupe_variants(values)
    return _coerce_relation_values(str(value))


def _extract_relation_hints(hit: dict[str, Any]) -> dict[str, list[str]]:
    path = hit.get("path")
    if _is_meta_schema_path(path) or _is_otto_runtime_path(path):
        return {}
    hints: dict[str, list[str]] = {}
    frontmatter = _frontmatter_map(hit.get("frontmatter_text"))
    for field in _RELATION_HINT_FIELDS:
        values = _coerce_relation_values(frontmatter.get(field))
        if values:
            hints[field] = values
    return hints


def _relation_hint_support(query: str, hit: dict[str, Any]) -> dict[str, Any]:
    hints = _extract_relation_hints(hit)
    query_terms = {token for token in _query_tokens(query) if len(token) >= 3}
    matched_terms: set[str] = set()
    matched_fields: set[str] = set()
    matched_values: list[str] = []
    for field, values in hints.items():
        for value in values:
            overlap = query_terms.intersection(_query_tokens(value))
            if not overlap:
                continue
            matched_terms.update(overlap)
            matched_fields.add(field)
            matched_values.append(value)
    score = min(0.03, (0.006 * len(matched_terms)) + (0.004 * len(matched_fields)))
    return {
        "relation_hints": hints,
        "matched_terms": sorted(matched_terms),
        "matched_fields": sorted(matched_fields),
        "matched_values": _dedupe_variants(matched_values),
        "score": round(score, 4),
    }


def _graph_prep_hints(hits: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for hit in hits:
        relation_hints = hit.get("relation_hints", {}) or {}
        if not relation_hints:
            continue
        hints.append(
            {
                "path": str(hit.get("path", "")),
                "title": str(hit.get("title", "")),
                "relation_hints": relation_hints,
            }
        )
        if len(hints) >= limit:
            break
    return hints


def _distance_caps(mode: str) -> tuple[float, float]:
    vector_cfg = _vector_cfg()
    default_cap = float(vector_cfg.get("max_distance_deep", 1.25) if mode == "deep" else vector_cfg.get("max_distance_fast", 1.1))
    corroborated_margin = float(
        vector_cfg.get("corroborated_margin_deep", 0.2) if mode == "deep" else vector_cfg.get("corroborated_margin_fast", 0.3)
    )
    return default_cap, default_cap + corroborated_margin


def _technical_rewrite_cap(mode: str) -> float:
    vector_cfg = _vector_cfg()
    base_cap, corroborated_cap = _distance_caps(mode)
    extra_margin = float(
        vector_cfg.get("technical_rewrite_margin_deep", 0.45)
        if mode == "deep"
        else vector_cfg.get("technical_rewrite_margin_fast", 0.55)
    )
    return max(base_cap, corroborated_cap + extra_margin)


def _fused_score_breakdown(
    hit: dict[str, Any],
    *,
    bonus: float,
    support_boost: float,
    relation_hint_support: float,
    penalty: float,
) -> dict[str, float]:
    source_rrf = {
        str(source).strip().lower(): float(score or 0.0)
        for source, score in dict(hit.get("source_rrf", {}) or {}).items()
        if str(source).strip()
    }
    semantic_similarity = sum(score for source, score in source_rrf.items() if source == "chroma")
    evidence_support = sum(score for source, score in source_rrf.items() if source != "chroma") + bonus + support_boost
    return {
        "semantic_similarity": round(semantic_similarity, 4),
        "evidence_support": round(evidence_support, 4),
        "relation_hint_support": round(float(relation_hint_support or 0.0), 4),
        "noise_penalty": round(float(penalty or 0.0), 4),
    }


def _rerank_hits(
    hits: list[dict[str, Any]],
    *,
    source_kind: str,
    cfg: dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    penalty_per_flag = float(cfg.get("penalty_per_flag", 0.35) or 0.0)
    max_distance, _ = _distance_caps(mode)
    for hit in hits:
        if _exclude_hit(hit, cfg):
            continue
        flags = _noise_flags(hit, cfg)
        bonus = _quality_bonus(hit, cfg)
        penalty = penalty_per_flag * len(flags)
        enriched = dict(hit)
        enriched["noise_flags"] = flags
        enriched["quality_bonus"] = bonus
        enriched["quality_penalty"] = penalty
        if source_kind == "sqlite":
            base = float(hit.get("rank", 1000.0) or 1000.0)
            enriched["_sort_value"] = base + penalty - bonus
        else:
            distance = hit.get("distance")
            base = float(distance) if distance is not None else 999.0
            if distance is not None and base > max_distance:
                continue
            enriched["_sort_value"] = base + penalty - bonus
        ranked.append(enriched)
    return sorted(ranked, key=lambda item: (float(item.get("_sort_value", 9999.0)), str(item.get("path", ""))))


def _rerank_fused_hits(hits: list[dict[str, Any]], cfg: dict[str, Any], query: str) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    penalty_per_flag = float(cfg.get("penalty_per_flag", 0.35) or 0.0)
    for hit in hits:
        flags = _noise_flags(hit, cfg)
        bonus = _quality_bonus(hit, cfg)
        penalty = penalty_per_flag * len(flags)
        support_boost = _source_support_boost(hit)
        relation_support = _relation_hint_support(query, hit)
        relation_hint_score = float(relation_support.get("score", 0.0) or 0.0)
        enriched = dict(hit)
        enriched["noise_flags"] = flags
        enriched["quality_bonus"] = bonus
        enriched["quality_penalty"] = penalty
        enriched["source_support_boost"] = support_boost
        enriched["relation_hints"] = relation_support.get("relation_hints", {})
        enriched["relation_hint_support"] = relation_hint_score
        enriched["relation_hint_matches"] = {
            "matched_terms": relation_support.get("matched_terms", []),
            "matched_fields": relation_support.get("matched_fields", []),
            "matched_values": relation_support.get("matched_values", []),
        }
        score_breakdown = _fused_score_breakdown(
            hit,
            bonus=bonus,
            support_boost=support_boost,
            relation_hint_support=relation_hint_score,
            penalty=penalty,
        )
        enriched["score_breakdown"] = score_breakdown
        enriched["rank_score"] = (
            float(score_breakdown.get("semantic_similarity", 0.0) or 0.0)
            + float(score_breakdown.get("evidence_support", 0.0) or 0.0)
            + float(score_breakdown.get("relation_hint_support", 0.0) or 0.0)
            - float(score_breakdown.get("noise_penalty", 0.0) or 0.0)
        )
        ranked.append(enriched)
    return sorted(ranked, key=lambda item: (-float(item.get("rank_score", 0.0)), str(item.get("path", ""))))


def _dense_gate_diagnostics(
    hits: list[dict[str, Any]],
    *,
    suppressed_reason_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    gate_counts: dict[str, int] = {}
    technical_rewrite_relaxed_hits: list[dict[str, Any]] = []
    for hit in hits:
        gate = str(hit.get("distance_gate", "unknown") or "unknown")
        gate_counts[gate] = gate_counts.get(gate, 0) + 1
        if gate == "technical_rewrite_relaxed":
            technical_rewrite_relaxed_hits.append(
                {
                    "path": str(hit.get("path", "")),
                    "best_variant": str(hit.get("best_variant", "")),
                    "distance": hit.get("distance"),
                }
            )
    return {
        "layer": "debug",
        "gate_counts": gate_counts,
        "technical_rewrite_relaxed_hits": technical_rewrite_relaxed_hits,
        "suppressed_reason_counts": dict(suppressed_reason_counts or {}),
    }


def _pick_better_suppressed_hit(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    if current is None:
        return candidate
    current_score = (
        -int(current.get("token_support_count", 0) or 0),
        0 if current.get("corroborated_path") else 1,
        float(current.get("distance", 999.0) or 999.0),
        str(current.get("path", "")),
    )
    candidate_score = (
        -int(candidate.get("token_support_count", 0) or 0),
        0 if candidate.get("corroborated_path") else 1,
        float(candidate.get("distance", 999.0) or 999.0),
        str(candidate.get("path", "")),
    )
    if candidate_score < current_score:
        return candidate
    return current


def _dense_anchor_tokens(query: str) -> list[str]:
    if not _is_phrase_like_technical_query(query):
        return []
    return _dedupe_variants([token.lower() for token in _query_tokens(query) if len(token) >= 4])


def _anchor_token_variants(token: str) -> list[str]:
    lowered = token.lower()
    if lowered == "vector":
        return ["vector", "vectors", "embedding", "embeddings"]
    if lowered in {"embedding", "embeddings"}:
        return ["embedding", "embeddings", "vector", "vectors"]
    if lowered == "semantic":
        return ["semantic", "semantics"]
    return [lowered]


def _dense_token_support(query: str, hit: dict[str, Any]) -> dict[str, Any]:
    anchor_tokens = _dense_anchor_tokens(query)
    support_text = " ".join(
        [
            str(hit.get("title") or ""),
            str(hit.get("path") or ""),
            str(hit.get("frontmatter_text") or ""),
            str(hit.get("body_excerpt") or ""),
        ]
    ).lower()
    matched_tokens = [
        token
        for token in anchor_tokens
        if any(variant in support_text for variant in _anchor_token_variants(token))
    ]
    nonsemantic_tokens = [token for token in anchor_tokens if token != "semantic"]
    matched_nonsemantic_tokens = [token for token in matched_tokens if token != "semantic"]
    return {
        "anchor_tokens": anchor_tokens,
        "matched_tokens": matched_tokens,
        "matched_count": len(matched_tokens),
        "missing_tokens": [token for token in anchor_tokens if token not in matched_tokens],
        "nonsemantic_tokens": nonsemantic_tokens,
        "matched_nonsemantic_tokens": matched_nonsemantic_tokens,
        "matched_nonsemantic_count": len(matched_nonsemantic_tokens),
    }


def _call_chroma_hits(
    query: str,
    limit: int,
    *,
    query_variants: list[str],
    candidate_limit: int,
    priority_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    try:
        return _chroma_hits(
            query,
            limit,
            query_variants=query_variants,
            candidate_limit=candidate_limit,
            priority_paths=priority_paths,
        )
    except TypeError:
        return _chroma_hits(query, limit)


def _like_hits(conn: sqlite3.Connection, query: str, limit: int) -> list[dict[str, Any]]:
    note_columns = _table_columns(conn, "notes")
    has_aliases_json = "aliases_json" in note_columns
    select_aliases = ", aliases_json" if has_aliases_json else ", ''"
    alias_clause = " OR aliases_json LIKE ?" if has_aliases_json else ""
    params: list[Any] = [f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"]
    if has_aliases_json:
        params.append(f"%{query}%")
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT path, title, frontmatter_text, body_excerpt{select_aliases}
        FROM notes
        WHERE title LIKE ? OR frontmatter_text LIKE ? OR body_excerpt LIKE ? OR path LIKE ?{alias_clause}
        ORDER BY mtime DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [
        {
            "path": row[0],
            "title": row[1],
            "frontmatter_text": row[2][:240] if row[2] else "",
            "body_excerpt": (row[3] or "")[:240],
            "aliases_json": row[4] or "",
            "source": "sqlite_like",
        }
        for row in rows
    ]


def _sqlite_hits(conn: sqlite3.Connection, query: str, limit: int) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    note_columns = _table_columns(conn, "notes")
    has_aliases_json = "aliases_json" in note_columns
    select_aliases = ", notes.aliases_json" if has_aliases_json else ", ''"
    try:
        rows = conn.execute(
            f"""
            SELECT notes.path, notes.title, notes.frontmatter_text, notes.body_excerpt, bm25(notes_fts) AS rank{select_aliases}
            FROM notes_fts
            JOIN notes ON notes.path = notes_fts.path
            WHERE notes_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (_fts_query(query), limit),
        ).fetchall()
        if rows and rows[0][0]:
            return [
                {
                    "path": row[0],
                    "title": row[1],
                    "frontmatter_text": row[2][:240] if row[2] else "",
                    "body_excerpt": (row[3] or "")[:240],
                    "rank": row[4],
                    "aliases_json": row[5] or "",
                    "source": "sqlite_fts",
                }
                for row in rows
            ]
    except sqlite3.Error:
        pass
    return _like_hits(conn, query, limit)


def _sqlite_variant_hits(conn: sqlite3.Connection, query: str, limit: int) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, Any]] = {}
    for variant in _sparse_query_variants(query):
        for hit in _sqlite_hits(conn, variant, limit):
            key = _normalize_path(hit.get("path"))
            current = by_path.get(key)
            candidate_rank = float(hit.get("rank", 1000.0) or 1000.0)
            if current is None or candidate_rank < float(current.get("rank", 1000.0) or 1000.0):
                enriched = dict(hit)
                enriched["matched_queries"] = [variant]
                enriched["best_variant"] = variant
                by_path[key] = enriched
            else:
                matched_queries = list(current.get("matched_queries", []) or [])
                if variant not in matched_queries:
                    current["matched_queries"] = [*matched_queries, variant]

    hits = sorted(
        by_path.values(),
        key=lambda item: (float(item.get("rank", 1000.0) or 1000.0), str(item.get("path", ""))),
    )
    return hits[:limit]


def _chroma_hits(
    query: str,
    limit: int,
    *,
    query_variants: list[str] | None = None,
    candidate_limit: int | None = None,
    priority_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    if chromadb is None or not query.strip():
        return []
    paths = load_paths()
    cfg = load_retrieval_config()
    collection_name = str(cfg.get("vector", {}).get("collection_name", "otto_gold"))
    effective_candidate_limit = max(int(candidate_limit or limit or 0), int(limit or 0), 1)
    try:
        client = chromadb.PersistentClient(path=str(paths.chroma_path))
        collection = client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
    except Exception:
        return []

    by_path: dict[str, dict[str, Any]] = {}
    for variant in query_variants or _query_variants(query):
        try:
            results = collection.query(
                query_texts=[variant],
                n_results=effective_candidate_limit,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            continue

        docs = results.get("documents") or [[]]
        metas = results.get("metadatas") or [[]]
        distances = results.get("distances") or [[]]
        if not docs or not docs[0]:
            continue

        for doc, meta, distance in zip(docs[0], metas[0], distances[0] if distances else [None] * len(docs[0])):
            meta = meta or {}
            path = str(meta.get("path", "") or "")
            if not path:
                continue
            key = _normalize_path(path)
            current = by_path.get(key)
            candidate_distance = float(distance) if distance is not None else 999.0
            if current is None or candidate_distance < float(current.get("distance", 999.0) or 999.0):
                by_path[key] = {
                    "path": path,
                    "title": meta.get("title", path or "vector_hit"),
                    "frontmatter_text": "",
                    "body_excerpt": (doc or "")[:240],
                    "distance": distance,
                    "source": "chroma",
                    "matched_queries": [variant],
                    "best_variant": variant,
                }
            elif variant not in list(current.get("matched_queries", []) or []):
                current["matched_queries"] = [*list(current.get("matched_queries", []) or []), variant]

    hits = sorted(
        by_path.values(),
        key=lambda item: (float(item.get("distance", 999.0) or 999.0), str(item.get("path", ""))),
    )
    selected = hits[:effective_candidate_limit]
    if priority_paths:
        selected_by_key = {_normalize_path(hit.get("path")): hit for hit in selected}
        for hit in hits[effective_candidate_limit:]:
            key = _normalize_path(hit.get("path"))
            if key in priority_paths and key not in selected_by_key:
                selected.append(hit)
                selected_by_key[key] = hit
    return selected


def _rerank_chroma_hits(
    hits: list[dict[str, Any]],
    *,
    query: str,
    cfg: dict[str, Any],
    mode: str,
    corroborated_paths: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, int]]:
    ranked: list[dict[str, Any]] = []
    best_suppressed: dict[str, Any] | None = None
    suppressed_reason_counts: dict[str, int] = {}
    penalty_per_flag = float(cfg.get("penalty_per_flag", 0.35) or 0.0)
    max_distance, corroborated_distance = _distance_caps(mode)
    technical_rewrite_distance = _technical_rewrite_cap(mode)
    base_variants = {variant.lower() for variant in _query_variants(query)}
    for hit in hits:
        if _exclude_hit(hit, cfg):
            continue
        flags = _noise_flags(hit, cfg)
        bonus = _quality_bonus(hit, cfg)
        penalty = penalty_per_flag * len(flags)
        enriched = dict(hit)
        enriched["noise_flags"] = flags
        enriched["quality_bonus"] = bonus
        enriched["quality_penalty"] = penalty
        token_support = _dense_token_support(query, hit)
        enriched["token_support"] = token_support

        distance = hit.get("distance")
        base = float(distance) if distance is not None else 999.0
        normalized_path = _normalize_path(hit.get("path"))
        is_corroborated = normalized_path in corroborated_paths
        matched_count = int(token_support.get("matched_count", 0) or 0)
        anchor_tokens = list(token_support.get("anchor_tokens", []) or [])
        matched_nonsemantic_count = int(token_support.get("matched_nonsemantic_count", 0) or 0)
        best_variant = str(hit.get("best_variant") or "").strip().lower()
        is_expanded_technical_variant = bool(anchor_tokens) and best_variant and best_variant not in base_variants
        token_penalty = 0.12 * float(max(0, len(anchor_tokens) - matched_count))
        if anchor_tokens and matched_count == 0:
            suppressed_reason_counts["weak_token_support"] = suppressed_reason_counts.get("weak_token_support", 0) + 1
            best_suppressed = _pick_better_suppressed_hit(
                best_suppressed,
                {
                    "path": hit.get("path", ""),
                    "title": hit.get("title", hit.get("path", "vector_hit")),
                    "distance": distance,
                    "matched_queries": list(hit.get("matched_queries", []) or []),
                    "best_variant": hit.get("best_variant"),
                    "reason": "weak_token_support",
                    "distance_threshold": max_distance,
                    "corroborated_distance_threshold": corroborated_distance,
                    "corroborated_path": is_corroborated,
                    "token_support_count": matched_count,
                    "token_support": token_support,
                },
            )
            continue
        if "semantic" in anchor_tokens and list(token_support.get("nonsemantic_tokens", []) or []) and matched_nonsemantic_count == 0:
            suppressed_reason_counts["weak_technical_context"] = suppressed_reason_counts.get("weak_technical_context", 0) + 1
            continue
        if distance is not None and base > max_distance:
            if is_corroborated and base <= corroborated_distance:
                enriched["distance_gate"] = "corroborated_relaxed"
                enriched["distance_threshold"] = corroborated_distance
            elif is_corroborated and is_expanded_technical_variant and matched_count > 0 and base <= technical_rewrite_distance:
                enriched["distance_gate"] = "technical_rewrite_relaxed"
                enriched["distance_threshold"] = technical_rewrite_distance
            else:
                suppressed_reason_counts["distance_above_cap"] = suppressed_reason_counts.get("distance_above_cap", 0) + 1
                best_suppressed = _pick_better_suppressed_hit(
                    best_suppressed,
                    {
                        "path": hit.get("path", ""),
                        "title": hit.get("title", hit.get("path", "vector_hit")),
                        "distance": distance,
                        "matched_queries": list(hit.get("matched_queries", []) or []),
                        "best_variant": hit.get("best_variant"),
                        "reason": "distance_above_cap",
                        "distance_threshold": max_distance,
                        "corroborated_distance_threshold": corroborated_distance,
                        "technical_rewrite_distance_threshold": technical_rewrite_distance,
                        "corroborated_path": is_corroborated,
                        "token_support_count": matched_count,
                        "token_support": token_support,
                    },
                )
                continue
        else:
            enriched["distance_gate"] = "default"
            enriched["distance_threshold"] = max_distance
        enriched["_sort_value"] = base + penalty + token_penalty - bonus
        ranked.append(enriched)
    return (
        sorted(ranked, key=lambda item: (float(item.get("_sort_value", 9999.0)), str(item.get("path", "")))),
        best_suppressed,
        suppressed_reason_counts,
    )


def _folder_hits(gold: dict[str, Any], query: str, limit: int) -> list[dict[str, Any]]:
    results = []
    q = query.lower().strip()
    for item in gold.get("top_folders", []):
        text = json.dumps(item, ensure_ascii=False).lower()
        if q in text:
            results.append(item)
    return results[:limit]


def retrieve_breakdown(query: str, mode: str = "fast") -> dict[str, Any]:
    logger = get_logger("otto.retrieve")
    paths = load_paths()
    gold = read_json(paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
    handoff = read_json(paths.state_root / "handoff" / "latest.json", default={}) or {}

    sqlite_limit = 8 if mode == "fast" else 20
    chroma_limit = 4 if mode == "fast" else 10
    folder_limit = 4 if mode == "fast" else 8
    expanded_chroma_limit = max(chroma_limit * 3, chroma_limit + 4)

    ranking_cfg = _ranking_cfg()
    sparse_hits: list[dict[str, Any]] = []
    if paths.sqlite_path.exists():
        conn = sqlite3.connect(paths.sqlite_path)
        sparse_hits = _sqlite_variant_hits(conn, query, sqlite_limit)
        conn.close()
    sparse_hits = _rerank_hits(sparse_hits, source_kind="sqlite", cfg=ranking_cfg, mode=mode)
    corroborated_paths = {_normalize_path(hit.get("path")) for hit in sparse_hits}
    dense_candidates = _call_chroma_hits(
        query,
        chroma_limit,
        query_variants=_query_variants(query),
        candidate_limit=chroma_limit,
    )
    dense_hits, best_suppressed_chroma_hit, suppressed_reason_counts = _rerank_chroma_hits(
        dense_candidates,
        cfg=ranking_cfg,
        query=query,
        mode=mode,
        corroborated_paths=corroborated_paths,
    )
    if not dense_hits and _is_phrase_like_technical_query(query):
        expanded_candidates = _call_chroma_hits(
            query,
            chroma_limit,
            query_variants=_dense_query_variants(query),
            candidate_limit=expanded_chroma_limit,
            priority_paths=corroborated_paths,
        )
        dense_hits, best_suppressed_chroma_hit, suppressed_reason_counts = _rerank_chroma_hits(
            expanded_candidates,
            cfg=ranking_cfg,
            query=query,
            mode=mode,
            corroborated_paths=corroborated_paths,
        )
    note_hits = _rerank_fused_hits(reciprocal_rank_fusion([sparse_hits, dense_hits], k=60), ranking_cfg, query)[:sqlite_limit]

    folder_hits = _folder_hits(gold, query, folder_limit)
    state_hits = []
    handoff_text = json.dumps(handoff, ensure_ascii=False)
    if query.lower().strip() and query.lower().strip() in handoff_text.lower():
        state_hits.append({"source": "handoff", "snippet": handoff_text[:240]})
    gold_text = json.dumps(gold, ensure_ascii=False)
    if query.lower().strip() and query.lower().strip() in gold_text.lower():
        state_hits.append({"source": "gold_summary", "snippet": gold_text[:240]})

    enough_evidence = bool(note_hits or folder_hits or state_hits)
    needs_deepening = (mode == "fast") and not enough_evidence

    package = {
        "mode": mode,
        "query": query,
        "enough_evidence": enough_evidence,
        "needs_deepening": needs_deepening,
        "note_hits": note_hits,
        "sqlite_hits": sparse_hits,
        "chroma_hits": dense_hits,
        "best_suppressed_chroma_hit": best_suppressed_chroma_hit,
        "dense_diagnostics": _dense_gate_diagnostics(dense_hits, suppressed_reason_counts=suppressed_reason_counts),
        "graph_prep_hints": _graph_prep_hints(note_hits),
        "folder_hits": folder_hits,
        "state_hits": state_hits,
        "sources_used": [source for source, hits in {"sqlite": sparse_hits, "chroma": dense_hits, "gold_state": state_hits}.items() if hits],
        "training_readiness": (gold.get("training_readiness") or {}),
    }
    append_jsonl(
        paths.state_root / "retrieval" / "events.jsonl",
        {
            "ts": now_iso(),
            "query": query,
            "mode": mode,
            "sources_used": package["sources_used"],
            "note_hits": len(note_hits),
            "folder_hits": len(folder_hits),
            "enough_evidence": enough_evidence,
            "needs_deepening": needs_deepening,
        },
    )
    logger.info(f"[retrieve] mode={mode} note_hits={len(note_hits)} folder_hits={len(folder_hits)} sources={package['sources_used']}")
    return package


def retrieve(query: str, mode: str = "fast") -> dict[str, Any]:
    return retrieve_breakdown(query, mode=mode)
