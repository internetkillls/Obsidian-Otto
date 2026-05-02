from __future__ import annotations

import json
import sqlite3
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import chromadb
except Exception:  # pragma: no cover
    chromadb = None

from ..config import load_paths, load_retrieval_config
from ..db import pg_available, read_signals
from ..logging_utils import get_logger


# ── token estimation (rough: 1 token ≈ 4 chars for English) ──────────────────
CHARS_PER_TOKEN = 4
MAX_CONTEXT_TOKENS = 120_000  # leave headroom below model's limit


@dataclass
class ContextSlice:
    source: str          # "sqlite"|"chroma"|"postgres"|"vault_signals"
    label: str           # human-readable label
    tokens: int
    content: str
    meta: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.content.strip()


class LongContextLimiter:
    """Bounds the combined context to MAX_CONTEXT_TOKENS tokens.

    Strategy: reserve slots by importance, then shrink lower-priority slices
    proportionally if the total exceeds the budget.
    """

    def __init__(self, max_tokens: int = MAX_CONTEXT_TOKENS):
        self.max_tokens = max_tokens

    def bound(self, slices: list[ContextSlice]) -> list[ContextSlice]:
        total = sum(s.tokens for s in slices)
        if total <= self.max_tokens:
            return slices

        # Priority order: postgres signals > sqlite > chroma > vault_signals
        priority = {"postgres": 0, "sqlite": 1, "chroma": 2, "vault_signals": 3}
        sorted_slices = sorted(slices, key=lambda s: priority.get(s.source, 99))

        budget = self.max_tokens
        result: list[ContextSlice] = []
        overflow = []

        for s in sorted_slices:
            if s.tokens <= budget:
                budget -= s.tokens
                result.append(s)
            else:
                overflow.append(s)

        # Shrink overflow slices to fit budget (proportional cut)
        if overflow and budget > 0:
            total_overflow = sum(s.tokens for s in overflow)
            for s in overflow:
                fraction = budget / total_overflow
                chars_to_keep = int(len(s.content) * fraction)
                s.content = s.content[:chars_to_keep] + "\n[...truncated...]"
                s.tokens = chars_to_keep // CHARS_PER_TOKEN

        # Re-sort back to original order (sqlite → chroma → postgres → vault_signals)
        result.extend(overflow)
        priority2 = {"sqlite": 0, "chroma": 1, "postgres": 2, "vault_signals": 3}
        return sorted(result, key=lambda s: priority2.get(s.source, 99))


# ── SQLite FTS5 retriever ──────────────────────────────────────────────────────

def _sqlite_fts(query: str, limit: int = 8) -> ContextSlice:
    paths = load_paths()
    if not paths.sqlite_path.exists():
        return ContextSlice(source="sqlite", label="SQLite FTS5", tokens=0, content="")

    conn = sqlite3.connect(paths.sqlite_path)
    conn.set_trace_callback(None)
    match_query = " ".join(re.findall(r"\w+", query)) or query.strip()
    try:
        rows = conn.execute(
            """
            SELECT notes.path, notes.title, notes.frontmatter_text, notes.body_excerpt, notes.mtime, bm25(notes_fts) AS rank
            FROM notes_fts
            JOIN notes ON notes.path = notes_fts.path
            WHERE notes_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match_query, limit),
        ).fetchall()
        if rows and not rows[0][0]:
            rows = []
    except sqlite3.Error:
        rows = []
    if not rows:
        rows = conn.execute(
            """
            SELECT path, title, frontmatter_text, body_excerpt, mtime
            FROM notes
            WHERE title LIKE ? OR frontmatter_text LIKE ? OR body_excerpt LIKE ?
            ORDER BY mtime DESC
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", f"%{query}%", limit),
        ).fetchall()
    conn.close()

    if not rows:
        return ContextSlice(source="sqlite", label="SQLite FTS5", tokens=0, content="")

    lines = ["## SQLite FTS5 — note hits", ""]
    for row in rows:
        path, title, fm, body, mtime, *_ = row
        mtime_str = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()[:10] if mtime else "?"
        lines.append(f"### {title} ({mtime_str})")
        if fm:
            lines.append(f"FM: {fm[:200]}")
        if body:
            lines.append(f"Body: {body[:300]}")
        lines.append(f"Source: [[{path}]]")
        lines.append("")

    content = "\n".join(lines)
    return ContextSlice(
        source="sqlite", label="SQLite FTS5", tokens=len(content) // CHARS_PER_TOKEN,
        content=content, meta={"note_count": len(rows)},
    )


def _sqlite_top_folders(limit: int = 5) -> ContextSlice:
    paths = load_paths()
    gold_path = paths.artifacts_root / "summaries" / "gold_summary.json"
    if not gold_path.exists():
        return ContextSlice(source="sqlite", label="SQLite folder risk", tokens=0, content="")

    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    folders = (gold.get("top_folders") or [])[:limit]
    if not folders:
        return ContextSlice(source="sqlite", label="SQLite folder risk", tokens=0, content="")

    lines = ["## SQLite — top risky folders (folder_risk table)", ""]
    for f in folders:
        lines.append(
            f"- `{f['folder']}` — risk={f['risk_score']}, "
            f"missing_fm={f['missing_frontmatter']}, dupes={f['duplicate_titles']}"
        )
    lines.append("")

    content = "\n".join(lines)
    return ContextSlice(
        source="sqlite", label="SQLite folder risk", tokens=len(content) // CHARS_PER_TOKEN,
        content=content, meta={"folder_count": len(folders)},
    )


# ── ChromaDB semantic retriever ───────────────────────────────────────────────

def _chroma_semantic(
    query: str,
    collection: str = "otto_gold",
    limit: int = 10,
    max_chars: int = 4000,
) -> ContextSlice:
    if chromadb is None:
        return ContextSlice(source="chroma", label="ChromaDB semantic", tokens=0, content="")

    paths = load_paths()
    cfg = load_retrieval_config()
    collection = str(cfg.get("vector", {}).get("collection_name", collection))

    try:
        client = chromadb.PersistentClient(path=str(paths.chroma_path))
        coll = client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})
        results = coll.query(query_texts=[query], n_results=limit, include=["documents", "metadatas"])
    except Exception:
        return ContextSlice(source="chroma", label="ChromaDB semantic", tokens=0, content="")

    docs = results.get("documents") or [[]]
    metas = results.get("metadatas") or [[]]

    if not docs or not docs[0]:
        return ContextSlice(source="chroma", label="ChromaDB semantic", tokens=0, content="")

    # Build context, hard-cap total chars
    lines = ["## ChromaDB — semantic vector matches", ""]
    total_chars = 0
    for i, (doc, meta) in enumerate(zip(docs[0], metas[0])):
        path = meta.get("path", "?") if meta else "?"
        title = meta.get("title", "?") if meta else "?"
        chunk = f"[chunk {i+1}] {doc[:600]}"
        if total_chars + len(chunk) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 80:
                lines.append(chunk[:remaining] + "\n[...truncated...]")
            break
        lines.append(chunk)
        total_chars += len(chunk)

    lines.append("")
    content = "\n".join(lines)
    return ContextSlice(
        source="chroma", label="ChromaDB semantic", tokens=len(content) // CHARS_PER_TOKEN,
        content=content, meta={"chunk_count": len(docs[0]), "collection": collection},
    )


def _chroma_otto_realm(limit: int = 3, max_chars: int = 2000) -> ContextSlice:
    """Read .Otto-Realm embeddings for KAIROS self-referential memory."""
    if chromadb is None:
        return ContextSlice(source="chroma", label="ChromaDB .Otto-Realm", tokens=0, content="")

    paths = load_paths()
    cfg = load_retrieval_config()
    collection = str(cfg.get("vector", {}).get("collection_name", "otto_gold"))

    try:
        client = chromadb.PersistentClient(path=str(paths.chroma_path))
        coll = client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})
        results = coll.query(
            query_texts=["Otto KAIROS dream self-model prediction memory"],
            n_results=limit,
            where={"path": {"$contains": ".Otto-Realm"}},
        )
    except Exception:
        return ContextSlice(source="chroma", label="ChromaDB .Otto-Realm", tokens=0, content="")

    docs = results.get("documents") or [[]]
    if not docs or not docs[0]:
        return ContextSlice(source="chroma", label="ChromaDB .Otto-Realm", tokens=0, content="")

    lines = ["## ChromaDB — .Otto-Realm memory embeddings", ""]
    total = 0
    for doc in docs[0]:
        trimmed = doc[:800]
        if total + len(trimmed) > max_chars:
            break
        lines.append(trimmed)
        total += len(trimmed)

    content = "\n".join(lines) + "\n"
    return ContextSlice(
        source="chroma", label="ChromaDB .Otto-Realm", tokens=len(content) // CHARS_PER_TOKEN,
        content=content, meta={"embedding_count": len(docs[0])},
    )


# ── Postgres event retriever ──────────────────────────────────────────────────

def _postgres_events(event_type: str | None = None, limit: int = 10, days: int = 7) -> ContextSlice:
    if not pg_available():
        return ContextSlice(source="postgres", label="Postgres events", tokens=0, content="")

    try:
        import psycopg2
    except Exception:
        return ContextSlice(source="postgres", label="Postgres events", tokens=0, content="")

    from ..config import load_postgres_config
    cfg = load_postgres_config()

    try:
        conn = psycopg2.connect(
            host=cfg.get("host", "localhost"),
            port=int(cfg.get("port", 54329)),
            dbname=cfg.get("database", "otto"),
            user=cfg.get("user", "otto"),
            password=cfg.get("password", "otto"),
        )
    except Exception:
        return ContextSlice(source="postgres", label="Postgres events", tokens=0, content="")

    cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    where_clause = f"WHERE ts >= '{cutoff}' AND ts >= NOW() - INTERVAL '{days} days'"
    if event_type:
        where_clause += f" AND type = '{event_type}'"

    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT type, source, payload, ts
            FROM events
            {where_clause}
            ORDER BY ts DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception:
        return ContextSlice(source="postgres", label="Postgres events", tokens=0, content="")

    if not rows:
        return ContextSlice(source="postgres", label="Postgres events", tokens=0, content="")

    lines = [f"## Postgres events — last {days} days", ""]
    for row in rows:
        etype, source, payload, ts = row
        ts_str = str(ts)[:19] if ts else "?"
        payload_str = json.dumps(payload, ensure_ascii=False)[:200] if payload else "{}"
        lines.append(f"- [{ts_str}] {etype} ({source}): {payload_str}")
    lines.append("")

    content = "\n".join(lines)
    return ContextSlice(
        source="postgres", label="Postgres events", tokens=len(content) // CHARS_PER_TOKEN,
        content=content, meta={"event_count": len(rows), "days": days},
    )


def _postgres_signals(limit: int = 20) -> ContextSlice:
    signals = read_signals(limit=limit, unresolved_only=True)
    if not signals:
        return ContextSlice(source="postgres", label="Postgres vault_signals", tokens=0, content="")

    lines = ["## Postgres vault_signals — unresolved chaos/signal records", ""]
    for s in signals:
        ts_str = str(s.get("ts", ""))[:19] if s.get("ts") else "?"
        factors = s.get("factors", {})
        factor_str = ", ".join(f"{k}={v}" for k, v in (factors.items() if isinstance(factors, dict) else []))
        lines.append(
            f"- [{s['signal_type']}] score={s['score']:.1f} {factor_str} → [[{s['note_path']}]] [{ts_str}]"
        )
    lines.append("")

    content = "\n".join(lines)
    return ContextSlice(
        source="postgres", label="Postgres vault_signals", tokens=len(content) // CHARS_PER_TOKEN,
        content=content, meta={"signal_count": len(signals)},
    )


# ── vault signal tools (JSON manifest) ───────────────────────────────────────

def _vault_chaos_signals(query: str, limit: int = 10) -> ContextSlice:
    """Read chaos scores from bronze_manifest.json via VaultSignalTools."""
    try:
        from ..orchestration.vault_signal_tools import VaultSignalTools
    except Exception:
        return ContextSlice(source="vault_signals", label="Vault chaos signals", tokens=0, content="")

    try:
        vst = VaultSignalTools()
        chaos = vst.list_chaos_to_order(limit=limit, focus="all")
    except Exception:
        return ContextSlice(source="vault_signals", label="Vault chaos signals", tokens=0, content="")

    if not chaos:
        return ContextSlice(source="vault_signals", label="Vault chaos signals", tokens=0, content="")

    lines = ["## Vault chaos signals (from bronze_manifest.json)", ""]
    for c in chaos:
        factors_str = ", ".join(c.factors.keys())
        lines.append(f"- score={c.score:.1f} [{factors_str}] → [[{c.path}]]")
    lines.append("")

    content = "\n".join(lines)
    return ContextSlice(
        source="vault_signals", label="Vault chaos signals",
        tokens=len(content) // CHARS_PER_TOKEN,
        content=content, meta={"chaos_count": len(chaos)},
    )


# ── public API ────────────────────────────────────────────────────────────────

class RagContextBuilder:
    """Builds bounded RAG context from all 3 DBs for model consumption.

    Usage:
        builder = RagContextBuilder()
        context = builder.build(goal="kairos strategy", query="metadata repair")
        print(context.summary())       # token count + source breakdown
        print(context.prompt_block())  # formatted string ready for model input
    """

    def __init__(
        self,
        *,
        sqlite_limit: int = 8,
        chroma_limit: int = 10,
        pg_event_limit: int = 10,
        pg_signal_limit: int = 20,
        chaos_limit: int = 10,
        max_tokens: int = MAX_CONTEXT_TOKENS,
    ):
        self.sqlite_limit = sqlite_limit
        self.chroma_limit = chroma_limit
        self.pg_event_limit = pg_event_limit
        self.pg_signal_limit = pg_signal_limit
        self.chaos_limit = chaos_limit
        self._limiter = LongContextLimiter(max_tokens=max_tokens)
        self._slices: list[ContextSlice] = []

    def add_sqlite(self, query: str) -> "RagContextBuilder":
        self._slices.append(_sqlite_fts(query, self.sqlite_limit))
        self._slices.append(_sqlite_top_folders(5))
        return self

    def add_chroma(self, query: str) -> "RagContextBuilder":
        self._slices.append(_chroma_semantic(query, limit=self.chroma_limit))
        self._slices.append(_chroma_otto_realm(limit=3))
        return self

    def add_postgres(self, event_type: str | None = None) -> "RagContextBuilder":
        self._slices.append(_postgres_events(event_type=event_type, limit=self.pg_event_limit))
        self._slices.append(_postgres_signals(self.pg_signal_limit))
        return self

    def add_vault_chaos(self, query: str = "") -> "RagContextBuilder":
        self._slices.append(_vault_chaos_signals(query, self.chaos_limit))
        return self

    def build(self) -> list[ContextSlice]:
        bounded = self._limiter.bound(self._slices)
        # Prune empty slices
        return [s for s in bounded if not s.is_empty()]

    def summary(self) -> dict[str, Any]:
        slices = self.build()
        total_tokens = sum(s.tokens for s in slices)
        return {
            "slice_count": len(slices),
            "total_tokens": total_tokens,
            "sources": {s.source: {"label": s.label, "tokens": s.tokens, "meta": s.meta} for s in slices},
        }

    def prompt_block(self) -> str:
        slices = self.build()
        if not slices:
            return "# RAG Context — no data available\n*(run pipeline first to populate DBs)*"

        header = "# RAG Context\n"
        sections = [f"## {s.label} [{s.source}, ~{s.tokens} tokens]\n{s.content}" for s in slices]
        return header + "\n".join(sections)


def build_rag_context(goal: str, query: str) -> list[ContextSlice]:
    """One-liner: build full RAG context for a given goal + query."""
    return (
        RagContextBuilder()
        .add_sqlite(query)
        .add_chroma(query)
        .add_postgres()
        .add_vault_chaos(query)
        .build()
    )


def rag_prompt_block(goal: str, query: str) -> str:
    """One-liner: get the formatted prompt block for a given goal + query."""
    return RagContextBuilder().add_sqlite(query).add_chroma(query).add_postgres().add_vault_chaos(query).prompt_block()
