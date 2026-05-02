from __future__ import annotations

from otto.adapters.qmd.manifest import build_qmd_manifest, qmd_manifest_health


def _source(
    source_id: str,
    *,
    kind: str = "curated_memory",
    required: bool = False,
    qmd_index: bool = True,
) -> dict[str, object]:
    return {
        "id": source_id,
        "kind": kind,
        "path_windows": f"C:/repo/{source_id}",
        "path_wsl": f"/mnt/c/repo/{source_id}",
        "required": required,
        "qmd_index": qmd_index,
        "vault_writeback": False,
        "privacy": "private_reviewed" if not kind.endswith("_raw") else "sensitive",
        "owner": "otto",
    }


def test_qmd_manifest_is_generated_from_indexable_registry_sources():
    registry = {
        "version": 1,
        "sources": [
            _source("curated"),
            _source("instagram_graph_raw", kind="social_raw", qmd_index=False),
        ],
    }

    manifest = build_qmd_manifest(registry)

    assert manifest["ok"] is True
    assert [source["id"] for source in manifest["sources"]] == ["curated"]
    assert manifest["sources"][0]["path"] == "/mnt/c/repo/curated"


def test_qmd_manifest_keeps_required_missing_as_hard_failure():
    registry = {
        "version": 1,
        "sources": [
            _source("missing_required", required=True),
        ],
    }

    manifest = build_qmd_manifest(registry)

    assert manifest["ok"] is False
    assert manifest["required_missing"] == ["missing_required"]
    assert "required-source-missing:missing_required" in manifest["registry_errors"]


def test_qmd_manifest_health_rejects_raw_sources_if_they_reappear():
    manifest = {
        "version": 1,
        "sources": [
            {
                "id": "instagram_graph_raw",
                "kind": "social_raw",
                "path": "/mnt/c/repo/state/social/instagram/raw",
            }
        ],
    }

    health = qmd_manifest_health(manifest)

    assert health["ok"] is False
    assert "raw-source-in-qmd-manifest:instagram_graph_raw" in health["errors"]
