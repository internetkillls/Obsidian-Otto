from __future__ import annotations

import json
import os
from pathlib import Path

from otto.app.status import build_status
from otto.orchestration.dream import run_dream_once
from otto.orchestration.kairos import run_kairos_once
from otto.pipeline import run_pipeline
from otto.retrieval.memory import retrieve


def test_pipeline(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    sample_vault = repo / "data" / "sample" / "vault"
    monkeypatch.setenv("OTTO_VAULT_PATH", str(sample_vault))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma_store"))

    result = run_pipeline()
    assert result["checkpoint"]["bronze_notes"] >= 1
    assert Path(result["checkpoint"]["silver_db"]).exists()

    status = build_status()
    assert "top_folders" in status
    assert status["checkpoint"]["training_ready"] in {True, False}

    retrieval = retrieve("policy", mode="fast")
    assert retrieval["enough_evidence"] is True
    assert len(retrieval["note_hits"]) >= 1

    kairos = run_kairos_once()
    dream = run_dream_once()
    assert "model_hint" in kairos
    assert "model_hint" in dream


def test_promised_files_exist():
    repo = Path(__file__).resolve().parents[1]
    required = [
        repo / "initial.bat",
        repo / "tui.bat",
        repo / "status.bat",
        repo / "sanity-check.bat",
        repo / "AGENTS.md",
        repo / ".codex" / "config.toml",
        repo / ".agents" / "skills" / "memory-fast" / "SKILL.md",
        repo / "docs" / "openclud-injection-map.md",
    ]
    for path in required:
        assert path.exists(), f"missing: {path}"
