from __future__ import annotations

import json
import sqlite3
from typing import Any

from otto.config import AppPaths
from otto.orchestration.kairos_chat import KAIROSChatHandler


def test_kairos_chat_routes_find_to_ask(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(handler, "_ask", lambda query, mode="fast": {"route": "ask", "query": query, "mode": mode})

    result = handler.handle("find notes about operator rhythm")

    assert result["route"] == "ask"
    assert result["query"] == "operator rhythm"


def test_kairos_chat_routes_compare(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(handler, "_compare", lambda query, mode="fast": {"route": "compare", "query": query})

    result = handler.handle("compare operator rhythm")

    assert result == {"route": "compare", "query": "operator rhythm"}


def test_kairos_chat_routes_deepen(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(handler, "_deepen", lambda query: {"route": "deepen", "query": query})

    result = handler.handle("deepen operator rhythm")

    assert result == {"route": "deepen", "query": "operator rhythm"}


def test_kairos_chat_routes_vector_status(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(handler, "_vector_status", lambda: {"route": "vector"})

    result = handler.handle("show vector status")

    assert result == {"route": "vector"}


def test_kairos_chat_routes_cron_status(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(handler, "_cron_status", lambda: {"route": "cron-status"})

    result = handler.handle("cron status")

    assert result == {"route": "cron-status"}


def test_kairos_chat_routes_cron_focus(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(
        "otto.orchestration.kairos_chat.steer_essay_control",
        lambda **kwargs: {"route": "steer", **kwargs},
    )

    result = handler.handle("focus paper topics for 2 days: open access journals")

    assert result["route"] == "steer"
    assert result["mode"] == "paper_topics"
    assert result["topic"] == "open access journals"
    assert result["days"] == 2


def test_kairos_chat_routes_paper_now(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(
        "otto.orchestration.kairos_chat.steer_essay_control",
        lambda **kwargs: {"route": "steer", **kwargs},
    )

    result = handler.handle("paper now")

    assert result["route"] == "steer"
    assert result["mode"] == "paper_now"


def test_kairos_chat_format_telegram_shows_cron_status():
    handler = KAIROSChatHandler()

    text = handler.format_telegram(
        {
            "generated_at": "2026-04-28T10:00:00+07:00",
            "job_count": 4,
            "enabled_job_count": 3,
            "managed_job_count": 2,
            "managed_jobs": [{"name": "otto_daily_essay_lab"}],
            "contract_drift_free": True,
            "essay_control": {
                "mode": "paper_topics",
                "focus_topic": "open access journals",
                "focus_until": "2026-04-30T10:00:00+07:00",
            },
            "steering": {
                "mode": "paper_topics",
                "topic": "open access journals",
                "active": True,
                "expires_at": "2026-04-30T10:00:00+07:00",
            },
        }
    )

    assert "Cron Status" in text
    assert "Jobs" in text
    assert "open access journals" in text


def test_kairos_chat_routes_chunks(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(handler, "_chunks_for_path", lambda path: {"route": "chunks", "path": path})

    result = handler.handle("show chunks for Projects/Policy Study.md")

    assert result == {"route": "chunks", "path": "Projects/Policy Study.md"}


def test_kairos_chat_adds_fallback_when_no_evidence(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(
        "otto.orchestration.kairos_chat.retrieve_breakdown",
        lambda query, mode="fast": {
            "query": query,
            "mode": mode,
            "sources_used": [],
            "enough_evidence": False,
            "needs_deepening": mode == "fast",
            "note_hits": [],
            "sqlite_hits": [],
            "chroma_hits": [],
            "best_suppressed_chroma_hit": None,
            "folder_hits": [],
            "state_hits": [],
        },
    )
    monkeypatch.setattr(handler, "_vector_status", lambda: {"vector_enabled": True, "chunk_count": 1713})

    result = handler._ask("operator rhythm", mode="fast")

    assert result["enough_evidence"] is False
    assert result["fallback"]["status"] == "no_evidence"
    assert "deepen operator rhythm" in result["suggested_commands"]
    assert result["auto_escalate"]["recommended"] is True


def test_kairos_chat_auto_mode_internal_deepen(monkeypatch):
    handler = KAIROSChatHandler()
    calls: list[tuple[str, str]] = []

    def fake_retrieve(query: str, mode: str = "fast") -> dict[str, Any]:
        calls.append((query, mode))
        if mode == "fast":
            return {
                "query": query,
                "mode": mode,
                "sources_used": [],
                "enough_evidence": False,
                "needs_deepening": True,
                "note_hits": [],
                "sqlite_hits": [],
                "chroma_hits": [],
                "best_suppressed_chroma_hit": None,
                "folder_hits": [],
                "state_hits": [],
            }
        return {
            "query": query,
            "mode": mode,
            "sources_used": ["sqlite"],
            "enough_evidence": True,
            "needs_deepening": False,
            "note_hits": [{"path": "Projects/Operator Rhythm.md", "title": "Operator Rhythm"}],
            "sqlite_hits": [{"path": "Projects/Operator Rhythm.md", "title": "Operator Rhythm"}],
            "chroma_hits": [],
            "best_suppressed_chroma_hit": None,
            "folder_hits": [],
            "state_hits": [],
        }

    monkeypatch.setattr("otto.orchestration.kairos_chat.retrieve_breakdown", fake_retrieve)
    monkeypatch.setattr(handler, "_auto_deepen_enabled", lambda: True)

    result = handler._ask("operator rhythm", mode="auto")

    assert calls == [("operator rhythm", "fast"), ("operator rhythm", "deep")]
    assert result["requested_mode"] == "auto"
    assert result["search_policy"]["resolved"] == "deep"
    assert result["note_hits"][0]["path"] == "Projects/Operator Rhythm.md"


def test_kairos_chat_result_carries_best_suppressed_chroma_hit():
    handler = KAIROSChatHandler()

    result = handler._result_from_package(
        "neural-network",
        {
            "sources_used": ["sqlite", "chroma"],
            "enough_evidence": True,
            "needs_deepening": False,
            "note_hits": [{"path": "Projects/Neural.md", "title": "Neural"}],
            "sqlite_hits": [{"path": "Projects/Neural.md", "title": "Neural"}],
            "chroma_hits": [{"path": "Projects/Neural.md", "title": "Neural"}],
            "best_suppressed_chroma_hit": {
                "path": "Projects/Other.md",
                "title": "Other",
                "distance": 1.34,
                "reason": "distance_above_cap",
            },
            "folder_hits": [],
            "state_hits": [],
        },
        resolved_mode="fast",
    )

    assert result["best_suppressed_chroma_hit"]["path"] == "Projects/Other.md"


def test_kairos_chat_result_carries_dense_diagnostics():
    handler = KAIROSChatHandler()

    result = handler._result_from_package(
        "semantic vector",
        {
            "sources_used": ["sqlite", "chroma"],
            "enough_evidence": True,
            "needs_deepening": False,
            "note_hits": [{"path": "Projects/Neural.md", "title": "Neural"}],
            "sqlite_hits": [{"path": "Projects/Neural.md", "title": "Neural"}],
            "chroma_hits": [{"path": "Projects/Neural.md", "title": "Neural", "distance_gate": "technical_rewrite_relaxed"}],
            "best_suppressed_chroma_hit": None,
            "dense_diagnostics": {
                "gate_counts": {"technical_rewrite_relaxed": 1},
                "technical_rewrite_relaxed_hits": [
                    {"path": "Projects/Neural.md", "best_variant": "semantic embedding", "distance": 1.44}
                ],
            },
            "folder_hits": [],
            "state_hits": [],
        },
        resolved_mode="fast",
    )

    assert result["dense_diagnostics"]["gate_counts"]["technical_rewrite_relaxed"] == 1


def test_kairos_chat_result_carries_graph_prep_hints():
    handler = KAIROSChatHandler()

    result = handler._result_from_package(
        "legitimation thesis",
        {
            "sources_used": ["sqlite"],
            "enough_evidence": True,
            "needs_deepening": False,
            "note_hits": [{"path": "Projects/Legitimation Thesis.md", "title": "Legitimation Thesis"}],
            "sqlite_hits": [{"path": "Projects/Legitimation Thesis.md", "title": "Legitimation Thesis"}],
            "chroma_hits": [],
            "best_suppressed_chroma_hit": None,
            "dense_diagnostics": {},
            "graph_prep_hints": [
                {
                    "path": "Projects/Legitimation Thesis.md",
                    "title": "Legitimation Thesis",
                    "relation_hints": {"orientation": ["thesis"], "scarcity": ["legitimation"]},
                }
            ],
            "folder_hits": [],
            "state_hits": [],
        },
        resolved_mode="fast",
    )

    assert result["graph_prep_hints"][0]["relation_hints"]["orientation"] == ["thesis"]


def test_kairos_chat_format_telegram_shows_retrieval_near_miss():
    handler = KAIROSChatHandler()

    text = handler.format_telegram(
        {
            "query": "neural-network",
            "sources_used": ["sqlite", "chroma"],
            "note_hits": [
                {
                    "path": "Projects/Neural.md",
                    "title": "Neural",
                    "score_breakdown": {
                        "semantic_similarity": 0.016,
                        "evidence_support": 0.132,
                        "relation_hint_support": 0.01,
                        "noise_penalty": 0.0,
                    },
                    "relation_hint_matches": {"matched_fields": ["orientation"]},
                }
            ],
            "dense_diagnostics": {
                "layer": "debug",
                "gate_counts": {"technical_rewrite_relaxed": 1},
                "suppressed_reason_counts": {"weak_technical_context": 1},
                "technical_rewrite_relaxed_hits": [
                    {"path": "Projects/Neural.md", "best_variant": "semantic vector", "distance": 1.341}
                ],
            },
            "best_suppressed_chroma_hit": {
                "path": "Projects/Other.md",
                "title": "Other Neural Note",
                "distance": 1.341,
                "best_variant": "semantic vector",
                "reason": "weak_token_support",
            },
        }
    )

    assert "Chroma near-miss" in text
    assert "1.341" in text
    assert "Dense gates: technical_rewrite_relaxed=1" in text
    assert "Dense suppressed: weak_technical_context=1" in text
    assert "Technical rewrite kept:" in text
    assert "semantic vector" in text
    assert "weak_token_support" in text
    assert "why: semantic, evidence, relation hints (orientation)" in text
    assert "score: s=0.016 e=0.132 r=0.010 n=0.000" in text


def test_kairos_chat_format_telegram_shows_compare_near_miss():
    handler = KAIROSChatHandler()

    text = handler.format_telegram(
        {
            "query": "neural-network",
            "sqlite_hits": [{"path": "Projects/Neural.md"}],
            "chroma_hits": [{"path": "Projects/Neural.md"}],
            "fused_hits": [
                {
                    "path": "Projects/Neural.md",
                    "title": "Neural",
                    "score_breakdown": {
                        "semantic_similarity": 0.016,
                        "evidence_support": 0.132,
                        "relation_hint_support": 0.01,
                        "noise_penalty": 0.0,
                    },
                    "relation_hint_matches": {"matched_fields": ["orientation"]},
                }
            ],
            "dense_diagnostics": {
                "layer": "debug",
                "gate_counts": {"technical_rewrite_relaxed": 1},
                "suppressed_reason_counts": {"weak_technical_context": 1},
                "technical_rewrite_relaxed_hits": [
                    {"path": "Projects/Neural.md", "best_variant": "semantic vector", "distance": 1.341}
                ],
            },
            "best_suppressed_chroma_hit": {
                "path": "Projects/Other.md",
                "title": "Other Neural Note",
                "distance": 1.341,
                "best_variant": "semantic vector",
                "reason": "weak_token_support",
            },
        }
    )

    assert "Best suppressed Chroma near-miss" in text
    assert "1.341" in text
    assert "Dense gates: technical_rewrite_relaxed=1" in text
    assert "Dense suppressed: weak_technical_context=1" in text
    assert "Technical rewrite kept:" in text
    assert "semantic vector" in text
    assert "weak_token_support" in text
    assert "why: semantic, evidence, relation hints (orientation)" in text
    assert "score: s=0.016 e=0.132 r=0.010 n=0.000" in text


def test_kairos_chat_rewrite_helper_suggests_corpus_near_queries(tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    conn = sqlite3.connect(sqlite_path)
    conn.executescript(
        """
        CREATE TABLE notes (
            path TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            frontmatter_text TEXT,
            body_excerpt TEXT,
            mtime REAL
        );
        """
    )
    conn.execute(
        "INSERT INTO notes(path, title, frontmatter_text, body_excerpt, mtime) VALUES (?, ?, ?, ?, ?)",
        (
            "Projects/Operator Rhythm.md",
            "Operator Rhythm",
            "aliases:\n- work rhythm\n- operator cadence\n",
            "working note about operator cadence",
            1.0,
        ),
    )
    conn.commit()
    conn.close()

    artifacts_root = tmp_path / "artifacts"
    (artifacts_root / "summaries").mkdir(parents=True, exist_ok=True)
    (artifacts_root / "summaries" / "gold_summary.json").write_text(
        json.dumps({"top_folders": [{"folder": "Projects", "risk_score": 4.0}]}),
        encoding="utf-8",
    )

    handler = KAIROSChatHandler()
    handler.paths = AppPaths(
        repo_root=handler.paths.repo_root,
        vault_path=handler.paths.vault_path,
        sqlite_path=sqlite_path,
        chroma_path=handler.paths.chroma_path,
        bronze_root=handler.paths.bronze_root,
        artifacts_root=artifacts_root,
        logs_root=handler.paths.logs_root,
        state_root=handler.paths.state_root,
    )

    rewrite = handler._query_rewrite_helper("operator rhythm")

    assert any(item["text"] == "Operator Rhythm" for item in rewrite["suggestions"])
    assert any(query == "find Operator Rhythm" for query in rewrite["queries"])
    assert all(not query.startswith("dig ") for query in rewrite["queries"][:2])


def test_kairos_chat_rewrite_helper_uses_configured_aliases(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(
        handler,
        "_rewrite_cfg",
        lambda: {
            "title_aliases": [
                {"title": "self model", "aliases": ["operator rhythm", "work rhythm"]},
            ],
            "folder_aliases": [
                {"folder": "Action/Daily Thought", "aliases": ["operator rhythm"]},
            ],
        },
    )
    monkeypatch.setattr(handler, "paths", handler.paths)

    rewrite = handler._query_rewrite_helper("operator rhythm")

    assert rewrite["queries"][0] == "find self model"
    assert any(item["text"] == "Action/Daily Thought" for item in rewrite["suggestions"])


def test_kairos_chat_rewrite_helper_reads_aliases_from_note_metadata(tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    conn = sqlite3.connect(sqlite_path)
    conn.executescript(
        """
        CREATE TABLE notes (
            path TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            frontmatter_text TEXT,
            body_excerpt TEXT,
            mtime REAL
        );
        """
    )
    conn.execute(
        "INSERT INTO notes(path, title, frontmatter_text, body_excerpt, mtime) VALUES (?, ?, ?, ?, ?)",
        (
            ".Otto-Realm/Brain/self_model.md",
            "self model",
            "title: Otto Self-Model\naliases:\n- operator rhythm\n- work rhythm\n",
            "profile note",
            1.0,
        ),
    )
    conn.commit()
    conn.close()

    artifacts_root = tmp_path / "artifacts"
    (artifacts_root / "summaries").mkdir(parents=True, exist_ok=True)
    (artifacts_root / "summaries" / "gold_summary.json").write_text(
        json.dumps({"top_folders": [{"folder": "00-Meta/scarcity", "risk_score": 45.4}]}),
        encoding="utf-8",
    )

    handler = KAIROSChatHandler()
    handler.paths = AppPaths(
        repo_root=handler.paths.repo_root,
        vault_path=handler.paths.vault_path,
        sqlite_path=sqlite_path,
        chroma_path=handler.paths.chroma_path,
        bronze_root=handler.paths.bronze_root,
        artifacts_root=artifacts_root,
        logs_root=handler.paths.logs_root,
        state_root=handler.paths.state_root,
    )
    handler._rewrite_cfg = lambda: {
        "high_confidence_title_score": 8.0,
        "prefer_titles_over_folders_gap": 3.0,
        "max_folder_fallbacks_when_title_confident": 0,
        "title_aliases": [],
        "folder_aliases": [],
    }

    rewrite = handler._query_rewrite_helper("operator rhythm")

    assert rewrite["queries"][0] == "find self model"
    assert all(not query.startswith("dig ") for query in rewrite["queries"])


def test_kairos_chat_rewrite_helper_collapses_whitespace_in_title_suggestions(tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    conn = sqlite3.connect(sqlite_path)
    conn.executescript(
        """
        CREATE TABLE notes (
            path TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            frontmatter_text TEXT,
            body_excerpt TEXT,
            mtime REAL
        );
        """
    )
    conn.execute(
        "INSERT INTO notes(path, title, frontmatter_text, body_excerpt, mtime) VALUES (?, ?, ?, ?, ?)",
        (
            ".Otto-Realm/Brain/clinical-summary.md",
            "Ringkasan Klinis   Re Evaluasi Psikiatri",
            "aliases:\n- laporan psikiater\n",
            "clinical summary note",
            1.0,
        ),
    )
    conn.commit()
    conn.close()

    artifacts_root = tmp_path / "artifacts"
    (artifacts_root / "summaries").mkdir(parents=True, exist_ok=True)
    (artifacts_root / "summaries" / "gold_summary.json").write_text(
        json.dumps({"top_folders": [{"folder": "00-Meta/scarcity", "risk_score": 45.4}]}),
        encoding="utf-8",
    )

    handler = KAIROSChatHandler()
    handler.paths = AppPaths(
        repo_root=handler.paths.repo_root,
        vault_path=handler.paths.vault_path,
        sqlite_path=sqlite_path,
        chroma_path=handler.paths.chroma_path,
        bronze_root=handler.paths.bronze_root,
        artifacts_root=artifacts_root,
        logs_root=handler.paths.logs_root,
        state_root=handler.paths.state_root,
    )
    handler._rewrite_cfg = lambda: {
        "high_confidence_title_score": 8.0,
        "prefer_titles_over_folders_gap": 3.0,
        "max_folder_fallbacks_when_title_confident": 0,
        "title_aliases": [],
        "folder_aliases": [],
    }

    rewrite = handler._query_rewrite_helper("laporan psikiater")

    assert rewrite["queries"][0] == "find Ringkasan Klinis Re Evaluasi Psikiatri"


def test_kairos_chat_deepen_escalates_after_fast_failure(monkeypatch):
    handler = KAIROSChatHandler()
    calls: list[tuple[str, str]] = []

    def fake_retrieve(query: str, mode: str = "fast") -> dict[str, Any]:
        calls.append((query, mode))
        if mode == "fast":
            return {
                "query": query,
                "mode": mode,
                "sources_used": [],
                "enough_evidence": False,
                "needs_deepening": True,
                "note_hits": [],
                "sqlite_hits": [],
                "chroma_hits": [],
                "folder_hits": [],
                "state_hits": [],
            }
        return {
            "query": query,
            "mode": mode,
            "sources_used": ["sqlite"],
            "enough_evidence": True,
            "needs_deepening": False,
            "note_hits": [{"path": "Projects/Operator Rhythm.md", "title": "Operator Rhythm"}],
            "sqlite_hits": [{"path": "Projects/Operator Rhythm.md", "title": "Operator Rhythm"}],
            "chroma_hits": [],
            "folder_hits": [],
            "state_hits": [],
        }

    monkeypatch.setattr("otto.orchestration.kairos_chat.retrieve_breakdown", fake_retrieve)

    result = handler._deepen("operator rhythm")

    assert calls == [("operator rhythm", "fast"), ("operator rhythm", "deep")]
    assert result["mode"] == "deep"
    assert result["escalation"]["performed"] is True
    assert result["note_hits"][0]["path"] == "Projects/Operator Rhythm.md"


def test_kairos_chat_deepen_no_evidence_disables_auto_retry(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(
        "otto.orchestration.kairos_chat.retrieve_breakdown",
        lambda query, mode="fast": {
            "query": query,
            "mode": mode,
            "sources_used": [],
            "enough_evidence": False,
            "needs_deepening": mode == "fast",
            "note_hits": [],
            "sqlite_hits": [],
            "chroma_hits": [],
            "folder_hits": [],
            "state_hits": [],
        },
    )
    monkeypatch.setattr(handler, "_vector_status", lambda: {"vector_enabled": True, "chunk_count": 1713})
    monkeypatch.setattr(
        handler,
        "_query_rewrite_helper",
        lambda query, limit=5: {
            "suggestions": [{"kind": "note_title", "text": "Operator Rhythm", "score": 5.0, "reason": "nearby"}],
            "queries": ["find Operator Rhythm"],
            "next_hint": "Try one of these corpus-near rewrites: find Operator Rhythm",
        },
    )

    result = handler._deepen("operator rhythm")

    assert result["auto_escalate"]["recommended"] is False
    assert result["suggested_queries"] == ["find Operator Rhythm"]


def test_kairos_chat_routes_indonesian_find(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(handler, "_ask", lambda query, mode="fast": {"route": "ask", "query": query, "mode": mode})

    result = handler.handle("cari catatan tentang operator rhythm")

    assert result["route"] == "ask"
    assert result["query"] == "operator rhythm"


def test_kairos_chat_routes_indonesian_compare(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(handler, "_compare", lambda query, mode="fast": {"route": "compare", "query": query})

    result = handler.handle("bandingkan sparse vs vector untuk operator rhythm")

    assert result == {"route": "compare", "query": "operator rhythm"}


def test_kairos_chat_routes_indonesian_chunks(monkeypatch):
    handler = KAIROSChatHandler()
    monkeypatch.setattr(handler, "_chunks_for_path", lambda path: {"route": "chunks", "path": path})

    result = handler.handle("ambil chunk note Projects/Policy Study.md")

    assert result == {"route": "chunks", "path": "Projects/Policy Study.md"}
