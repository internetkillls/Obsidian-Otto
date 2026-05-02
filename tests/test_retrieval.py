from __future__ import annotations

import sqlite3
from pathlib import Path

from otto.retrieval.evaluate import evaluate_retrieval
from otto.retrieval.hybrid import reciprocal_rank_fusion
from otto.retrieval.memory import retrieve, retrieve_breakdown


def _seed_sqlite(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE notes (
            path TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            aliases_json TEXT,
            frontmatter_text TEXT,
            body_excerpt TEXT,
            mtime REAL
        );
        CREATE VIRTUAL TABLE notes_fts USING fts5(path, title, aliases_text, frontmatter_text, body_excerpt);
        """
    )
    rows = [
        ("Inbox/Daily Note.md", "Daily Note", "[]", "type: daily", "This daily note tracks operator rhythm.", 1.0, ""),
        ("Projects/Policy Study.md", "Policy Study", '["policy memo"]', "type: project", "Policy research and study notes.", 2.0, "policy memo"),
    ]
    for row in rows:
        conn.execute(
            "INSERT INTO notes(path, title, aliases_json, frontmatter_text, body_excerpt, mtime) VALUES (?, ?, ?, ?, ?, ?)",
            row[:6],
        )
        conn.execute(
            "INSERT INTO notes_fts(path, title, aliases_text, frontmatter_text, body_excerpt) VALUES (?, ?, ?, ?, ?)",
            (row[0], row[1], row[6], row[3], row[4]),
        )
    conn.commit()
    conn.close()


def test_rrf_merges_sources():
    fused = reciprocal_rank_fusion(
        [
            [{"path": "a.md", "source": "sqlite_fts"}, {"path": "b.md", "source": "sqlite_fts"}],
            [{"path": "b.md", "source": "chroma"}, {"path": "c.md", "source": "chroma"}],
        ]
    )
    assert fused[0]["path"] == "b.md"
    assert set(fused[0]["sources"]) == {"sqlite_fts", "chroma"}
    assert fused[0]["source_rrf"]["sqlite_fts"] > 0
    assert fused[0]["source_rrf"]["chroma"] > 0


def test_retrieve_prefers_fts_and_logs(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    package = retrieve("policy", mode="fast")
    assert package["enough_evidence"] is True
    assert package["note_hits"][0]["path"] == "Projects/Policy Study.md"
    assert "sqlite" in package["sources_used"]
    assert (tmp_path / "state" / "retrieval" / "events.jsonl").exists()


def test_retrieval_eval_writes_report(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr("otto.retrieval.evaluate.repo_root", lambda: tmp_path)
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir.joinpath("retrieval_eval.yaml").write_text(
        "test_queries:\n  - query: policy\n    relevant_paths:\n      - Projects/Policy Study.md\n",
        encoding="utf-8",
    )

    result = evaluate_retrieval()
    assert result["query_count"] >= 1
    assert (tmp_path / "artifacts" / "reports" / "retrieval_eval.json").exists()


def test_retrieval_eval_normalizes_windows_paths(monkeypatch, tmp_path):
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir.joinpath("retrieval_eval.yaml").write_text(
        "test_queries:\n  - query: semantic embedding\n    relevant_paths:\n      - 20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr("otto.retrieval.evaluate.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "otto.retrieval.evaluate.retrieve",
        lambda query, mode="fast": {
            "note_hits": [
                {
                    "path": "20-Programs\\Neural-Network-Learning\\00 - Smart Connections, Transformer, dan Embedding.md",
                }
            ]
        },
    )

    result = evaluate_retrieval()

    assert result["hit_rate_at_8"] == 1.0
    assert result["mrr"] == 1.0


def test_retrieval_eval_supports_same_concern_fixture(monkeypatch, tmp_path):
    fixture_dir = tmp_path / "tests" / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture_dir.joinpath("retrieval_eval.yaml").write_text(
        (
            "test_queries:\n"
            "  - query: institutional friction\n"
            "    relevant_paths:\n"
            "      - Projects/Legitimation Thesis.md\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr("otto.retrieval.evaluate.repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "otto.retrieval.evaluate.retrieve",
        lambda query, mode="fast": {
            "note_hits": [
                {
                    "path": "Projects/Legitimation Thesis.md",
                }
            ]
        },
    )

    result = evaluate_retrieval()

    assert result["query_count"] == 1
    assert result["hit_rate_at_8"] == 1.0


def test_retrieve_breakdown_penalizes_archive_noise(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    monkeypatch.setattr("otto.retrieval.memory._sqlite_hits", lambda conn, query, limit: [])
    monkeypatch.setattr(
        "otto.retrieval.memory._chroma_hits",
        lambda query, limit: [
            {
                "path": "90-Archive/04 Archive/Misc/index.md",
                "title": "index",
                "frontmatter_text": "",
                "body_excerpt": "operator rhythm archive note",
                "distance": 0.02,
                "source": "chroma",
            },
            {
                "path": "Projects/Operator Rhythm.md",
                "title": "Operator Rhythm",
                "frontmatter_text": "type: project",
                "body_excerpt": "operator rhythm working note",
                "distance": 0.15,
                "source": "chroma",
            },
        ],
    )

    package = retrieve_breakdown("operator rhythm", mode="fast")

    assert package["note_hits"][0]["path"] == "Projects/Operator Rhythm.md"
    assert all("90-Archive" not in item["path"] for item in package["note_hits"])


def test_retrieve_breakdown_uses_aliases_from_silver(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    package = retrieve_breakdown("policy memo", mode="fast")

    assert package["enough_evidence"] is True
    assert package["note_hits"][0]["path"] == "Projects/Policy Study.md"
    assert "sqlite" in package["sources_used"]


def test_retrieve_breakdown_carries_relation_hints_for_graph_prep(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    monkeypatch.setattr(
        "otto.retrieval.memory._sqlite_hits",
        lambda conn, query, limit: [
            {
                "path": "Projects/Legitimation Thesis.md",
                "title": "Legitimation Thesis",
                "frontmatter_text": "orientation: thesis\nscarcity: legitimation\nfamily: theory\n",
                "body_excerpt": "note about institutional friction",
                "rank": 0.01,
                "aliases_json": "[]",
                "source": "sqlite_fts",
            }
        ],
    )
    monkeypatch.setattr("otto.retrieval.memory._chroma_hits", lambda query, limit, **kwargs: [])

    package = retrieve_breakdown("legitimation thesis", mode="fast")

    hit = package["note_hits"][0]
    assert hit["relation_hints"]["orientation"] == ["thesis"]
    assert hit["relation_hints"]["scarcity"] == ["legitimation"]
    assert hit["relation_hint_support"] > 0
    assert hit["score_breakdown"]["relation_hint_support"] > 0
    assert package["graph_prep_hints"][0]["path"] == "Projects/Legitimation Thesis.md"


def test_retrieve_breakdown_ignores_meta_schema_relation_hints(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    monkeypatch.setattr(
        "otto.retrieval.memory._sqlite_hits",
        lambda conn, query, limit: [
            {
                "path": "00-Meta/Theory.md",
                "title": "Theory",
                "frontmatter_text": "orientation: thesis\nscarcity: legitimation\nfamily: theory\n",
                "body_excerpt": "meta schema note",
                "rank": 0.01,
                "aliases_json": "[]",
                "source": "sqlite_fts",
            },
            {
                "path": "Projects/Legitimation Thesis.md",
                "title": "Legitimation Thesis",
                "frontmatter_text": "orientation: thesis\nscarcity: legitimation\nfamily: theory\n",
                "body_excerpt": "working note",
                "rank": 0.011,
                "aliases_json": "[]",
                "source": "sqlite_fts",
            },
        ],
    )
    monkeypatch.setattr("otto.retrieval.memory._chroma_hits", lambda query, limit, **kwargs: [])

    package = retrieve_breakdown("legitimation thesis", mode="fast")

    by_path = {item["path"]: item for item in package["note_hits"]}
    assert by_path["00-Meta/Theory.md"]["relation_hint_support"] == 0.0
    assert by_path["Projects/Legitimation Thesis.md"]["relation_hint_support"] > 0.0
    assert all(item["path"] != "00-Meta/Theory.md" for item in package["graph_prep_hints"])


def test_retrieve_breakdown_coalesces_chroma_query_variants(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    queries: list[str] = []

    class FakeCollection:
        def query(self, *, query_texts, n_results, include):
            query = query_texts[0]
            queries.append(query)
            if query == "neural-network":
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
            if query == "neural network":
                return {
                    "documents": [[
                        "dense smart connections note",
                        "dense smart connections note fallback",
                    ]],
                    "metadatas": [[
                        {
                            "path": "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md",
                            "title": "00 - Smart Connections, Transformer, dan Embedding",
                        },
                        {
                            "path": "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md",
                            "title": "00 - Smart Connections, Transformer, dan Embedding",
                        },
                    ]],
                    "distances": [[0.42, 0.18]],
                }
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def get_or_create_collection(self, name, metadata):
            return FakeCollection()

    fake_chromadb = type("FakeChromaDb", (), {"PersistentClient": FakeClient})
    monkeypatch.setattr("otto.retrieval.memory.chromadb", fake_chromadb)

    package = retrieve_breakdown("neural-network", mode="fast")

    assert package["enough_evidence"] is True
    assert package["chroma_hits"]
    assert queries == ["neural-network", "neural network"]
    assert len(package["chroma_hits"]) == 1
    assert package["chroma_hits"][0]["distance"] == 0.18
    assert package["chroma_hits"][0]["matched_queries"] == ["neural network"]


def test_retrieve_breakdown_expands_semantic_embedding_dense_candidates(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    monkeypatch.setattr(
        "otto.retrieval.memory._sqlite_hits",
        lambda conn, query, limit: [
            {
                "path": "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md",
                "title": "00 - Smart Connections, Transformer, dan Embedding",
                "frontmatter_text": "type: program-note",
                "body_excerpt": "semantic embedding overview",
                "rank": 0.01,
                "aliases_json": "[]",
                "source": "sqlite_fts",
            }
        ],
    )

    queries: list[tuple[str, int]] = []

    class FakeCollection:
        def query(self, *, query_texts, n_results, include):
            query = query_texts[0]
            queries.append((query, n_results))
            if query == "semantic embedding" and n_results <= 4:
                return {
                    "documents": [["poetry and metaphor"]],
                    "metadatas": [[{"path": "00-Meta/Poet.md", "title": "Poet"}]],
                    "distances": [[1.33]],
                }
            if query == "semantic vector" and n_results > 4:
                return {
                    "documents": [["semantic vector embedding systems note"]],
                    "metadatas": [[
                        {
                            "path": "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md",
                            "title": "00 - Smart Connections, Transformer, dan Embedding",
                        }
                    ]],
                    "distances": [[1.56]],
                }
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def get_or_create_collection(self, name, metadata):
            return FakeCollection()

    fake_chromadb = type("FakeChromaDb", (), {"PersistentClient": FakeClient})
    monkeypatch.setattr("otto.retrieval.memory.chromadb", fake_chromadb)

    package = retrieve_breakdown("semantic embedding", mode="fast")

    assert package["enough_evidence"] is True
    assert package["chroma_hits"]
    assert package["note_hits"][0]["path"] == "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md"
    assert "chroma" in package["note_hits"][0]["sources"]
    assert package["chroma_hits"][0]["distance_gate"] == "technical_rewrite_relaxed"
    assert queries[0] == ("semantic embedding", 4)
    assert any(query == "semantic vector" and n_results > 4 for query, n_results in queries)


def test_retrieve_breakdown_uses_sparse_semantic_embedding_variant_for_semantic_vector(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    def fake_sqlite_hits(conn, query, limit):
        if query == "semantic embedding":
            return [
                {
                    "path": "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md",
                    "title": "00 - Smart Connections, Transformer, dan Embedding",
                    "frontmatter_text": "type: program-note",
                    "body_excerpt": "semantic embedding overview",
                    "rank": 0.01,
                    "aliases_json": "[]",
                    "source": "sqlite_fts",
                }
            ]
        return []

    monkeypatch.setattr("otto.retrieval.memory._sqlite_hits", fake_sqlite_hits)
    monkeypatch.setattr(
        "otto.retrieval.memory._chroma_hits",
        lambda query, limit, **kwargs: [
            {
                "path": "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md",
                "title": "00 - Smart Connections, Transformer, dan Embedding",
                "frontmatter_text": "",
                "body_excerpt": "semantic embedding systems note",
                "distance": 1.44,
                "source": "chroma",
                "matched_queries": ["semantic-vector", "vector embedding"],
                "best_variant": "semantic-vector",
            }
        ],
    )

    package = retrieve_breakdown("semantic vector", mode="fast")

    assert package["enough_evidence"] is True
    assert package["sqlite_hits"][0]["best_variant"] == "semantic embedding"
    assert package["chroma_hits"][0]["distance_gate"] == "technical_rewrite_relaxed"
    assert package["note_hits"][0]["path"] == "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md"
    assert "sqlite" in package["sources_used"]
    assert "chroma" in package["sources_used"]
    assert package["dense_diagnostics"]["technical_rewrite_relaxed_hits"][0]["best_variant"] == "semantic-vector"


def test_retrieve_breakdown_filters_weak_technical_context_near_miss(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    monkeypatch.setattr("otto.retrieval.memory._sqlite_hits", lambda conn, query, limit: [])
    monkeypatch.setattr(
        "otto.retrieval.memory._chroma_hits",
        lambda query, limit, **kwargs: [
            {
                "path": "10-Personal/02 Personlicher Zettelkasten/Phi-mind-1.md",
                "title": "Phi mind 1",
                "frontmatter_text": "",
                "body_excerpt": "semantics makes us human",
                "distance": 1.21,
                "source": "chroma",
                "matched_queries": ["semantic vectors"],
                "best_variant": "semantic vectors",
            }
        ],
    )

    package = retrieve_breakdown("semantic vector", mode="fast")

    assert package["chroma_hits"] == []
    assert package["best_suppressed_chroma_hit"] is None
    assert package["dense_diagnostics"]["suppressed_reason_counts"]["weak_technical_context"] == 1


def test_retrieve_breakdown_prefers_token_supported_near_miss(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    monkeypatch.setattr("otto.retrieval.memory._sqlite_hits", lambda conn, query, limit: [])
    monkeypatch.setattr(
        "otto.retrieval.memory._chroma_hits",
        lambda query, limit, **kwargs: [
            {
                "path": "00-Meta/Poet.md",
                "title": "Poet",
                "frontmatter_text": "",
                "body_excerpt": "lyric fragment",
                "distance": 1.32,
                "source": "chroma",
                "matched_queries": ["semantic embedding"],
                "best_variant": "semantic embedding",
            },
            {
                "path": "Projects/Semantic Embedding Primer.md",
                "title": "Semantic Embedding Primer",
                "frontmatter_text": "",
                "body_excerpt": "semantic vector primer",
                "distance": 1.37,
                "source": "chroma",
                "matched_queries": ["semantic vector"],
                "best_variant": "semantic vector",
            },
        ],
    )

    package = retrieve_breakdown("semantic embedding", mode="fast")

    assert package["chroma_hits"] == []
    assert package["best_suppressed_chroma_hit"]["path"] == "Projects/Semantic Embedding Primer.md"
    assert package["best_suppressed_chroma_hit"]["reason"] == "distance_above_cap"
    assert package["best_suppressed_chroma_hit"]["best_variant"] == "semantic vector"


def test_retrieve_breakdown_boosts_shared_dense_support(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    monkeypatch.setattr(
        "otto.retrieval.memory._sqlite_hits",
        lambda conn, query, limit: [
            {
                "path": "20-Programs/Neural-Network-Learning/index.md",
                "title": "Neural Network Learning - Program",
                "frontmatter_text": "type: program",
                "body_excerpt": "neural network smart connections overview",
                "rank": 0.01,
                "aliases_json": "[]",
                "source": "sqlite_fts",
            },
            {
                "path": "20-Programs/Neural-Network-Learning/remix-smart-connector.md",
                "title": "Remix Smart Connector",
                "frontmatter_text": "type: product",
                "body_excerpt": "smart connections modular refactor",
                "rank": 0.011,
                "aliases_json": "[]",
                "source": "sqlite_fts",
            },
        ],
    )
    monkeypatch.setattr(
        "otto.retrieval.memory._chroma_hits",
        lambda query, limit: [
            {
                "path": "20-Programs/Neural-Network-Learning/remix-smart-connector.md",
                "title": "Remix Smart Connector",
                "frontmatter_text": "",
                "body_excerpt": "semantic embedding smart connections refactor",
                "distance": 0.03,
                "source": "chroma",
            }
        ],
    )

    package = retrieve_breakdown("smart connections", mode="fast")

    assert package["enough_evidence"] is True
    assert package["chroma_hits"]
    assert package["note_hits"][0]["path"] == "20-Programs/Neural-Network-Learning/remix-smart-connector.md"
    assert "chroma" in package["note_hits"][0]["sources"]
    assert "sqlite_fts" in package["note_hits"][0]["sources"]
    assert package["note_hits"][0]["source_support_boost"] > 0


def test_retrieve_breakdown_keeps_relation_hints_weak_against_stronger_evidence(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    monkeypatch.setattr(
        "otto.retrieval.memory._sqlite_hits",
        lambda conn, query, limit: [
            {
                "path": "Projects/Systems Friction.md",
                "title": "Systems Friction",
                "frontmatter_text": "type: project",
                "body_excerpt": "legitimation thesis and institutional friction",
                "rank": 0.01,
                "aliases_json": "[]",
                "source": "sqlite_fts",
            },
            {
                "path": "Projects/Legitimation Thesis.md",
                "title": "Legitimation Thesis",
                "frontmatter_text": "orientation: thesis\nscarcity: legitimation\nfamily: theory\n",
                "body_excerpt": "working note",
                "rank": 0.011,
                "aliases_json": "[]",
                "source": "sqlite_fts",
            },
        ],
    )
    monkeypatch.setattr(
        "otto.retrieval.memory._chroma_hits",
        lambda query, limit, **kwargs: [
            {
                "path": "Projects/Systems Friction.md",
                "title": "Systems Friction",
                "frontmatter_text": "",
                "body_excerpt": "institutional friction and legitimation pressure",
                "distance": 0.11,
                "source": "chroma",
            }
        ],
    )

    package = retrieve_breakdown("legitimation thesis", mode="fast")

    assert package["note_hits"][0]["path"] == "Projects/Systems Friction.md"
    by_path = {item["path"]: item for item in package["note_hits"]}
    assert by_path["Projects/Legitimation Thesis.md"]["relation_hint_support"] > 0.0
    assert by_path["Projects/Systems Friction.md"]["rank_score"] > by_path["Projects/Legitimation Thesis.md"]["rank_score"]


def test_retrieve_breakdown_accepts_corroborated_chroma_near_miss(monkeypatch, tmp_path):
    sqlite_path = tmp_path / "otto_silver.db"
    _seed_sqlite(sqlite_path)
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))

    monkeypatch.setattr(
        "otto.retrieval.memory._sqlite_hits",
        lambda conn, query, limit: [
            {
                "path": "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md",
                "title": "00 - Smart Connections, Transformer, dan Embedding",
                "frontmatter_text": "type: program-note",
                "body_excerpt": "neural network embedding overview",
                "rank": 0.01,
                "aliases_json": "[]",
                "source": "sqlite_fts",
            }
        ],
    )
    monkeypatch.setattr(
        "otto.retrieval.memory._chroma_hits",
        lambda query, limit: [
            {
                "path": "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md",
                "title": "00 - Smart Connections, Transformer, dan Embedding",
                "frontmatter_text": "",
                "body_excerpt": "neural network semantic chunk",
                "distance": 1.33,
                "source": "chroma",
                "matched_queries": ["neural network"],
            },
            {
                "path": "Projects/Other Neural Note.md",
                "title": "Other Neural Note",
                "frontmatter_text": "",
                "body_excerpt": "other neural note",
                "distance": 1.34,
                "source": "chroma",
                "matched_queries": ["neural network"],
            },
        ],
    )

    package = retrieve_breakdown("neural-network", mode="fast")

    assert package["enough_evidence"] is True
    assert package["chroma_hits"][0]["distance_gate"] == "corroborated_relaxed"
    assert package["note_hits"][0]["path"] == "20-Programs/Neural-Network-Learning/00 - Smart Connections, Transformer, dan Embedding.md"
    assert "chroma" in package["note_hits"][0]["sources"]
    assert package["best_suppressed_chroma_hit"]["path"] == "Projects/Other Neural Note.md"
    assert package["best_suppressed_chroma_hit"]["reason"] == "distance_above_cap"
