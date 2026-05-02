from __future__ import annotations

from pathlib import Path

from otto.config import AppPaths
from otto.tooling.obsidian_scan import scan_vault


def test_scan_vault_extracts_scarcity_with_frontmatter_precedence(scratch_path, monkeypatch):
    repo_root = scratch_path / "repo"
    vault = scratch_path / "vault"
    bronze_root = repo_root / "data" / "bronze"
    artifacts_root = repo_root / "artifacts"
    logs_root = repo_root / "logs"
    state_root = repo_root / "state"
    sqlite_path = repo_root / "external" / "sqlite" / "otto_silver.db"
    chroma_path = repo_root / "external" / "chroma"

    vault.mkdir(parents=True)
    repo_root.mkdir(parents=True)

    (vault / "frontmatter.md").write_text(
        "---\n"
        "scarcity: [memory]\n"
        "necessity: 0.9\n"
        "artificial: 0.1\n"
        "aliases:\n"
        "  - memory anchor\n"
        "---\n"
        "# Note\n"
        "#scarcity/design #orientation/clarity\n",
        encoding="utf-8",
    )
    (vault / "tags-only.md").write_text(
        "# Tags only\n"
        "#scarcity/context #allocation/focus #necessity/0.4 #artificial/0.7\n",
        encoding="utf-8",
    )

    paths = AppPaths(
        repo_root=repo_root,
        vault_path=vault,
        sqlite_path=sqlite_path,
        chroma_path=chroma_path,
        bronze_root=bronze_root,
        artifacts_root=artifacts_root,
        logs_root=logs_root,
        state_root=state_root,
    )
    monkeypatch.setattr("otto.tooling.obsidian_scan.load_paths", lambda: paths)

    payload = scan_vault()
    notes = {note["path"]: note for note in payload["notes"]}

    frontmatter = notes["frontmatter.md"]
    assert frontmatter["scarcity"] == ["memory"]
    assert frontmatter["necessity"] == 0.9
    assert frontmatter["artificial"] == 0.1
    assert frontmatter["orientation"] == "clarity"
    assert frontmatter["cluster_membership"] == ["memory"]
    assert frontmatter["aliases"] == ["memory anchor"]

    tags_only = notes["tags-only.md"]
    assert tags_only["scarcity"] == ["context"]
    assert tags_only["allocation"] == "focus"
    assert tags_only["necessity"] == 0.4
    assert tags_only["artificial"] == 0.7
    assert tags_only["cluster_membership"] == ["context"]
