from __future__ import annotations

import json

from otto.orchestration.morpheus import MorpheusEnrichment
from otto.orchestration.morpheus_openclaw_bridge import (
    build_morpheus_openclaw_bridge,
    load_morpheus_openclaw_bridge,
)


def test_build_morpheus_openclaw_bridge_marks_candidates_as_investigative(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))

    (tmp_path / "artifacts" / "reports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "reports" / "vector_summary.json").write_text(
        json.dumps({"enabled": False, "note": "chromadb not installed"}),
        encoding="utf-8",
    )

    enrichment = MorpheusEnrichment(
        layer="continuity-topology",
        continuity_threads=["Repair metadata in Projects", "Economic pressure around runway"],
        persisting_pressures=["Repair metadata in Projects"],
        ridges=["Projects"],
        valleys=["Repair metadata in Projects"],
        fault_lines=["Projects: high-value area under recurring pressure"],
        love_surface=["Projects deserve a more durable operating pattern"],
    )

    payload = build_morpheus_openclaw_bridge(
        enrichment=enrichment,
        stable_facts=["Goal: reduce fragmentation"],
        unresolved=["Repair metadata in Projects"],
        rag_summary={"slice_count": 2, "total_tokens": 480, "sources": ["sqlite", "chroma"]},
        vault_materials=[],
    )

    assert payload["ok"] is True
    assert payload["bridge_mode"] == "investigate-first"
    assert payload["ready_for_openclaw_dreaming"] is False
    assert payload["memory_contract"]["current_status"] == "hypothesis"
    assert payload["memory_contract"]["promotion_blocked_until"] == ["reviewed", "verified"]
    assert payload["retrieval_basis"]["markdown_body_required"] is True
    assert payload["retrieval_basis"]["frontmatter_only_forbidden"] is True
    assert payload["candidate_count"] >= 1
    assert all(candidate["status"] == "hypothesis" for candidate in payload["candidates"])
    assert all(candidate["ready_for_openclaw_dreaming"] is False for candidate in payload["candidates"])
    assert any("vector" in warning.lower() for warning in payload["warnings"])


def test_load_morpheus_openclaw_bridge_refreshes_from_latest_state(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))

    state_root = tmp_path / "state"
    artifacts_root = tmp_path / "artifacts"
    (artifacts_root / "reports").mkdir(parents=True, exist_ok=True)
    (artifacts_root / "reports" / "vector_summary.json").write_text(
        json.dumps({"enabled": True, "note": "vector cache live"}),
        encoding="utf-8",
    )
    (state_root / "dream").mkdir(parents=True, exist_ok=True)
    (state_root / "handoff").mkdir(parents=True, exist_ok=True)
    (state_root / "dream" / "morpheus_latest.json").write_text(
        json.dumps(
            {
                "layer": "continuity-topology",
                "continuity_threads": ["Bridge candidate thread"],
                "persisting_pressures": ["Repair metadata in Projects"],
                "fault_lines": ["Projects: high-value area under recurring pressure"],
                "ridges": ["Projects"],
                "valleys": ["Repair metadata in Projects"],
                "love_surface": ["Projects deserve a more durable operating pattern"],
            }
        ),
        encoding="utf-8",
    )
    (state_root / "dream" / "dream_state.json").write_text(
        json.dumps({"rag_tokens": 120, "rag_sources": ["sqlite"]}),
        encoding="utf-8",
    )
    (state_root / "handoff" / "latest.json").write_text(
        json.dumps({"goal": "Reduce fragmentation", "next_actions": ["Repair metadata in Projects"]}),
        encoding="utf-8",
    )

    payload = load_morpheus_openclaw_bridge(refresh=True)

    assert payload["ok"] is True
    assert payload["retrieval_basis"]["vector_cache_live"] is True
    assert payload["stable_facts"][0] == "Goal: Reduce fragmentation"
    assert payload["candidate_count"] >= 1
    assert "state_path" in payload
