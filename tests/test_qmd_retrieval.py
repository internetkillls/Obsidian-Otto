from __future__ import annotations

from types import SimpleNamespace

from otto.adapters.qmd.retrieval import normalize_openclaw_memory_results


def test_normalize_openclaw_memory_results_builds_evidence_hits(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    brain = vault / ".Otto-Realm" / "Brain"
    brain.mkdir(parents=True)
    note = brain / "profile.md"
    note.write_text("# Profile\n", encoding="utf-8")
    monkeypatch.setattr("otto.adapters.qmd.retrieval.load_paths", lambda: SimpleNamespace(vault_path=vault, repo_root=tmp_path))
    monkeypatch.setattr(
        "otto.adapters.qmd.retrieval.iter_sources",
        lambda: [
            SimpleNamespace(
                id="otto-brain",
                path_windows=str(brain),
                path_wsl=str(brain),
            )
        ],
    )
    payload = {
        "results": [
            {
                "path": ".Otto-Realm/Brain/profile.md",
                "score": 0.7,
                "snippet": "Profile snippet",
                "source": "memory",
            }
        ]
    }

    hits = normalize_openclaw_memory_results("profile", payload)

    assert len(hits) == 1
    assert hits[0].source_id == "otto-brain"
    assert hits[0].score == 0.7
    assert hits[0].evidence.uri.startswith("file://")
    assert hits[0].to_dict()["evidence_uri"] == hits[0].evidence.uri
