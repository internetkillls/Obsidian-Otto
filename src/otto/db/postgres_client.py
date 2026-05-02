from __future__ import annotations

import logging
from typing import Any

try:
    import psycopg2
    from psycopg2 import extras as pg_extras
except Exception:  # pragma: no cover
    psycopg2 = None
    pg_extras = None

from ..config import load_postgres_config
from ..schema_registry import schema_fingerprint, schema_registry


def _pg_conn() -> Any:
    if psycopg2 is None:
        raise RuntimeError("psycopg2 not installed")
    cfg = load_postgres_config()
    return psycopg2.connect(
        host=cfg.get("host", "localhost"),
        port=int(cfg.get("port", 54329)),
        dbname=cfg.get("database", "otto"),
        user=cfg.get("user", "otto"),
        password=cfg.get("password", "otto"),
    )


def pg_available() -> bool:
    if psycopg2 is None:
        return False
    try:
        conn = _pg_conn()
        conn.close()
        return True
    except Exception:
        return False


def init_pg_schema() -> None:
    """Create all Otto tables if they don't exist."""
    if not pg_available():
        return
    conn = _pg_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id          TEXT PRIMARY KEY,
                        type        TEXT NOT NULL,
                        source      TEXT NOT NULL,
                        payload     JSONB NOT NULL,
                        ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        session_id  TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_events_type   ON events(type);
                    CREATE INDEX IF NOT EXISTS idx_events_ts    ON events(ts DESC);
                    CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);

                    CREATE TABLE IF NOT EXISTS vault_signals (
                        id          SERIAL PRIMARY KEY,
                        note_path   TEXT NOT NULL,
                        signal_type TEXT NOT NULL,
                        score       REAL NOT NULL,
                        factors     JSONB,
                        ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        resolved    BOOLEAN NOT NULL DEFAULT FALSE,
                        UNIQUE(note_path, signal_type, ts)
                    );
                    CREATE INDEX IF NOT EXISTS idx_signals_type ON vault_signals(signal_type);
                    CREATE INDEX IF NOT EXISTS idx_signals_score ON vault_signals(score DESC);
                    CREATE INDEX IF NOT EXISTS idx_signals_unresolved ON vault_signals(resolved) WHERE resolved = FALSE;

                    CREATE TABLE IF NOT EXISTS profiles (
                        id          SERIAL PRIMARY KEY,
                        session_id  TEXT NOT NULL,
                        model       TEXT,
                        strengths   JSONB,
                        weaknesses  JSONB,
                        ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_profiles_session ON profiles(session_id);
                """)
        logging.getLogger("otto.pg").debug("[pg] schema initialized fingerprint=%s targets=%s", schema_fingerprint(), len(schema_registry()))
    finally:
        conn.close()


def write_event(event_dict: dict[str, Any]) -> None:
    """Write a single event to the events table."""
    if not pg_available():
        return
    conn = _pg_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO events (id, type, source, payload, ts)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        event_dict.get("id"),
                        event_dict.get("type"),
                        event_dict.get("source"),
                        psycopg2.extras.Json(event_dict.get("payload", {})),
                        event_dict.get("ts"),
                    ),
                )
    finally:
        conn.close()


def write_signals(signals: list[dict[str, Any]]) -> None:
    """Bulk-write vault signal records."""
    if not pg_available() or not signals:
        return
    conn = _pg_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                for sig in signals:
                    cur.execute(
                        """
                        INSERT INTO vault_signals (note_path, signal_type, score, factors, ts)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            sig.get("path"),
                            sig.get("signal_type"),
                            sig.get("score", 0.0),
                            psycopg2.extras.Json(sig.get("factors")),
                        ),
                    )
    finally:
        conn.close()


def read_signals(signal_type: str | None = None, limit: int = 50, unresolved_only: bool = False) -> list[dict[str, Any]]:
    """Read vault signal records, optionally filtered."""
    if not pg_available():
        return []
    conn = _pg_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                where = []
                args: list[Any] = []
                if signal_type:
                    where.append("signal_type = %s")
                    args.append(signal_type)
                if unresolved_only:
                    where.append("resolved = FALSE")
                clause = ("WHERE " + " AND ".join(where)) if where else ""
                # Deduplicate: keep latest (max ts) per note_path + signal_type
                cur.execute(
                    f"""
                    SELECT DISTINCT ON (note_path, signal_type)
                           note_path, signal_type, score, factors, ts, resolved
                    FROM vault_signals {clause}
                    ORDER BY note_path, signal_type, ts DESC
                    LIMIT %s
                    """,
                    [*args, limit],
                )
                rows = cur.fetchall()
                return [
                    {
                        "note_path": r[0],
                        "signal_type": r[1],
                        "score": r[2],
                        "factors": r[3],
                        "ts": r[4],
                        "resolved": r[5],
                    }
                    for r in rows
                ]
    finally:
        conn.close()
