from __future__ import annotations

from pathlib import Path

from otto.memory.source_registry import (
    qmd_indexable_sources,
    validate_source_registry,
)


def test_source_registry_rejects_raw_social_qmd_index():
    registry = {
        "version": 1,
        "sources": [
            {
                "id": "instagram_graph_raw",
                "kind": "social_raw",
                "path_windows": "state/social/instagram/raw",
                "path_wsl": "/mnt/c/repo/state/social/instagram/raw",
                "required": False,
                "qmd_index": True,
                "vault_writeback": False,
                "privacy": "sensitive",
                "owner": "otto",
            }
        ],
    }

    result = validate_source_registry(registry)

    assert result["ok"] is False
    assert "raw-source-qmd-enabled:instagram_graph_raw" in result["errors"]


def test_source_registry_reports_missing_required_source(monkeypatch, tmp_path):
    missing = tmp_path / "missing"
    registry = {
        "version": 1,
        "sources": [
            {
                "id": "required",
                "kind": "curated_memory",
                "path_windows": str(missing),
                "path_wsl": str(missing),
                "required": True,
                "qmd_index": True,
                "vault_writeback": True,
                "privacy": "private_reviewed",
                "owner": "otto",
            }
        ],
    }
    monkeypatch.setattr("otto.memory.source_registry.is_wsl", lambda: False)

    result = validate_source_registry(registry)

    assert result["ok"] is False
    assert "required-source-missing:required" in result["errors"]


def test_qmd_indexable_sources_excludes_raw_social(tmp_path):
    curated = tmp_path / "curated"
    curated.mkdir()
    registry = {
        "version": 1,
        "sources": [
            {
                "id": "curated",
                "kind": "curated_memory",
                "path_windows": str(curated),
                "path_wsl": str(curated),
                "required": True,
                "qmd_index": True,
                "vault_writeback": True,
                "privacy": "private_reviewed",
                "owner": "otto",
            },
            {
                "id": "instagram_graph_raw",
                "kind": "social_raw",
                "path_windows": str(Path("state/social/instagram/raw")),
                "path_wsl": "/mnt/c/repo/state/social/instagram/raw",
                "required": False,
                "qmd_index": False,
                "vault_writeback": False,
                "privacy": "sensitive",
                "owner": "otto",
            },
        ],
    }

    sources = qmd_indexable_sources(registry)

    assert [source.id for source in sources] == ["curated"]
