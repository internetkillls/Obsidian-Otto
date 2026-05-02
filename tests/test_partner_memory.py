from __future__ import annotations

from otto.brain.partner_memory import embed_care_moment, record_interaction
from otto.retrieval import retrieve_partner
from otto.tooling.vector_store import build_vector_cache


def test_vector_cache_builds_enriched_partner_collection(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))

    calls: dict[str, list[dict]] = {}

    class FakeCollection:
        def __init__(self, name):
            self.name = name

        def delete(self, where):
            calls.setdefault(self.name, [])

        def add(self, *, documents, ids, metadatas):
            calls[self.name] = [
                {"document": doc, "id": doc_id, "metadata": metadata}
                for doc, doc_id, metadata in zip(documents, ids, metadatas)
            ]

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def delete_collection(self, name):
            pass

        def get_or_create_collection(self, name):
            return FakeCollection(name)

    monkeypatch.setattr("otto.tooling.vector_store.chromadb", type("FakeChromaDb", (), {"PersistentClient": FakeClient}))
    monkeypatch.setattr("otto.tooling.vector_store.RecursiveCharacterTextSplitter", None)

    result = build_vector_cache(
        [
            {
                "path": ".Otto-Realm/Memory-Tiers/02-Interpretations/2026-04-26_mood.md",
                "title": "Recovery mood note",
                "frontmatter_text": (
                    "signal_type: mood_note\n"
                    "mood_phase: low\n"
                    "audhd_state: overloaded\n"
                    "ts: 2026-04-26T01:02:03+07:00\n"
                    "source: heartbeat\n"
                ),
                "render_text": "Josh is tired and needs gentle recovery support.",
            },
            {
                "path": "Projects/Policy Study.md",
                "title": "Policy Study",
                "frontmatter_text": "type: project\n",
                "render_text": "Policy note about institutions.",
            },
        ]
    )

    assert result.enabled is True
    assert result.collections == ["otto_gold", "otto_partner"]
    assert len(calls["otto_gold"]) == 2
    assert len(calls["otto_partner"]) == 1
    metadata = calls["otto_partner"][0]["metadata"]
    assert metadata["signal_type"] == "mood_note"
    assert metadata["mood_phase"] == "low"
    assert metadata["audhd_state"] == "overloaded"
    assert metadata["ts"] == "2026-04-26T01:02:03+07:00"
    assert metadata["ts_epoch"] > 0
    assert metadata["source"] == "heartbeat"


def test_live_partner_memory_upserts_to_otto_partner(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))

    upserts: list[dict] = []

    class FakeCollection:
        def upsert(self, *, documents, ids, metadatas):
            upserts.append({"documents": documents, "ids": ids, "metadatas": metadatas})

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def get_or_create_collection(self, name, metadata):
            assert name == "otto_partner"
            assert metadata == {"hnsw:space": "cosine"}
            return FakeCollection()

    monkeypatch.setattr("otto.brain.partner_memory.chromadb", type("FakeChromaDb", (), {"PersistentClient": FakeClient}))

    care = embed_care_moment(
        "Josh said he felt held by a previous check-in.",
        ts="2026-04-26T01:02:03+07:00",
        mood_phase="recovery",
        audhd_state="settling",
        source="test",
    )
    mood = record_interaction("takut", mood_phase="low", ts="2026-04-26T01:03:03+07:00")

    assert care["embedded"] is True
    assert mood["embedded"] is True
    assert upserts[0]["metadatas"][0]["signal_type"] == "care_moment"
    assert upserts[0]["metadatas"][0]["mood_phase"] == "recovery"
    assert upserts[1]["metadatas"][0]["signal_type"] == "mood_note"
    assert upserts[1]["metadatas"][0]["mood_phase"] == "low"


def test_retrieve_partner_uses_strict_then_relaxed_threshold(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))

    class FakeCollection:
        def query(self, *, query_texts, n_results, include):
            assert query_texts == ["Josh lagi di fase apa?"]
            assert include == ["documents", "metadatas", "distances"]
            return {
                "documents": [["near care moment", "too far care moment"]],
                "metadatas": [[
                    {
                        "path": "live/mood",
                        "title": "Mood",
                        "signal_type": "mood_note",
                        "mood_phase": "low",
                        "audhd_state": "overloaded",
                        "ts": "2026-04-26T01:02:03+07:00",
                        "ts_epoch": 1777140123.0,
                        "source": "live_partner_memory",
                    },
                    {
                        "path": "live/care",
                        "title": "Care",
                        "signal_type": "care_moment",
                        "mood_phase": "recovery",
                        "audhd_state": "settling",
                        "ts": "2026-04-26T01:02:03+07:00",
                        "ts_epoch": 1777140123.0,
                        "source": "live_partner_memory",
                    },
                ]],
                "distances": [[0.82, 0.95]],
            }

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def get_or_create_collection(self, name, metadata):
            assert name == "otto_partner"
            return FakeCollection()

    monkeypatch.setattr("otto.retrieval.memory.chromadb", type("FakeChromaDb", (), {"PersistentClient": FakeClient}))

    package = retrieve_partner("Josh lagi di fase apa?", n_results=3)

    assert package["collection"] == "otto_partner"
    assert package["distance_gate"] == "relaxed"
    assert package["max_distance"] == 0.9
    assert package["enough_evidence"] is True
    assert len(package["hits"]) == 1
    assert package["hits"][0]["source"] == "chroma_partner"
    assert package["hits"][0]["signal_type"] == "mood_note"
    assert package["hits"][0]["mood_phase"] == "low"
    assert package["hits"][0]["audhd_state"] == "overloaded"


def test_retrieve_partner_applies_metadata_filters(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))

    class FakeCollection:
        def query(self, *, query_texts, n_results, include):
            return {
                "documents": [["mood care", "support care"]],
                "metadatas": [[
                    {"path": "live/mood", "title": "Mood", "signal_type": "mood_note", "mood_phase": "low", "ts_epoch": 200.0},
                    {"path": "live/care", "title": "Care", "signal_type": "care_moment", "mood_phase": "recovery", "ts_epoch": 200.0},
                ]],
                "distances": [[0.2, 0.3]],
            }

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def get_or_create_collection(self, name, metadata):
            return FakeCollection()

    monkeypatch.setattr("otto.retrieval.memory.chromadb", type("FakeChromaDb", (), {"PersistentClient": FakeClient}))

    package = retrieve_partner("support", signal_type="care_moment", mood_phase="recovery")

    assert package["distance_gate"] == "strict"
    assert [hit["path"] for hit in package["hits"]] == ["live/care"]
