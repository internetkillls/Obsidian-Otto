from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from otto.soul.paths import build_root_audit, to_host_path


def _patch_paths(monkeypatch, tmp_path):
    paths = SimpleNamespace(
        repo_root=tmp_path,
        vault_path=tmp_path / "vault",
        sqlite_path=tmp_path / "sqlite.db",
        chroma_path=tmp_path / "chroma",
        bronze_root=tmp_path / "bronze",
        artifacts_root=tmp_path / "artifacts",
        logs_root=tmp_path / "logs",
        state_root=tmp_path / "state",
    )
    monkeypatch.setattr("otto.config.load_paths", lambda: paths)
    monkeypatch.setattr("otto.governance_utils.load_paths", lambda: paths)
    monkeypatch.setattr("otto.orchestration.ops_health.load_paths", lambda: paths)
    monkeypatch.setattr("otto.soul.paths.load_paths", lambda: paths)
    monkeypatch.setattr("otto.soul.paths.repo_root", lambda: tmp_path)
    return paths


def test_to_host_path_keeps_mnt_path_inside_wsl(monkeypatch):
    monkeypatch.setattr("otto.soul.paths.is_wsl", lambda: True)
    raw = "/mnt/c/Users/joshu/Josh Obsidian/.Otto-Realm"
    resolved = to_host_path(raw)
    assert str(resolved).replace("\\", "/") == raw


def test_root_audit_detects_legacy_wrong_root(monkeypatch, tmp_path):
    canonical = tmp_path / "vault" / ".Otto-Realm"
    legacy = tmp_path / "repo" / "Otto-Realm"
    (canonical / "Heartbeats").mkdir(parents=True, exist_ok=True)
    (legacy / "Brain").mkdir(parents=True, exist_ok=True)
    (legacy / "Brain" / "legacy-note.md").write_text("legacy", encoding="utf-8")

    mapping = {
        "/canonical": canonical,
        "/legacy": legacy,
    }
    monkeypatch.setattr("otto.soul.paths.to_host_path", lambda raw: mapping[raw])
    roots = SimpleNamespace(
        soul_root_windows="C:/vault/.Otto-Realm",
        soul_root_wsl="/canonical",
        legacy_wrong_root_wsl="/legacy",
    )
    audit = build_root_audit(roots, sample_limit=5)
    assert audit["legacy_wrong_root_exists"] is True
    assert "Brain/legacy-note.md" in audit["wrong_root_candidates"]
    assert audit["canonical_soul_root"]["exists"] is True


def test_soul_rehydrate_seeds_profile_snapshot_with_frontmatter(monkeypatch, tmp_path):
    from otto.soul import rehydrate as rehydrate_module

    paths = _patch_paths(monkeypatch, tmp_path)
    vault = paths.vault_path
    vault.mkdir(parents=True, exist_ok=True)

    roots = SimpleNamespace(
        repo_root_windows=str(tmp_path).replace("\\", "/"),
        repo_root_wsl=str(tmp_path).replace("\\", "/"),
        vault_root_windows=str(vault).replace("\\", "/"),
        vault_root_wsl=str(vault).replace("\\", "/"),
        soul_root_windows=str(vault / ".Otto-Realm").replace("\\", "/"),
        soul_root_wsl=str(vault / ".Otto-Realm").replace("\\", "/"),
        legacy_wrong_root_wsl=str(tmp_path / "Otto-Realm").replace("\\", "/"),
    )
    monkeypatch.setattr("otto.soul.paths.infer_soul_roots", lambda: roots)
    monkeypatch.setattr("otto.soul.rehydrate.infer_soul_roots", lambda: roots)

    result = rehydrate_module._seed_missing_canonical_soul(write=True)
    profile = vault / ".Otto-Realm" / "Profile Snapshot.md"
    assert result["ok"] is True
    assert profile.exists()
    text = profile.read_text(encoding="utf-8")
    assert "otto_state: seeded_missing_canonical_file" in text
    assert "review_required: true" in text
    assert "source: soul_rehydrate" in text
    assert (vault / ".Otto-Realm" / "Heartbeats").exists()


def test_qmd_vault_roundtrip_writes_controlled_gold_target(monkeypatch, tmp_path):
    from otto.orchestration.ops_health import run_qmd_vault_roundtrip

    paths = _patch_paths(monkeypatch, tmp_path)
    paths.vault_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("otto.orchestration.ops_health.run_qmd_index_refresh", lambda timeout_seconds=60: {"ok": True})
    monkeypatch.setattr(
        "otto.orchestration.ops_health.qmd_search",
        lambda query, max_results=8, timeout_seconds=60: {"ok": True, "hit_count": 1, "hits": [{"title": query}]},
    )

    result = run_qmd_vault_roundtrip(strict=True, write=True)
    target = paths.vault_path / ".Otto-Realm" / "Memory-Tiers" / "Ops" / "OPS1 Roundtrip Proof.md"

    assert result["ok"] is True
    assert result["query"] == "OPS1 Roundtrip Proof"
    assert result["target_path"] == str(target)
    assert target.exists()
    assert "reviewed_gold_test_artifact" in target.read_text(encoding="utf-8")

    golden_results = paths.state_root / "ops" / "golden_path_results.json"
    assert golden_results.exists()
    assert "qmd_vault_roundtrip" in golden_results.read_text(encoding="utf-8")

