from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from otto.fs_utils import write_text
from otto.orchestration.metadata_enrichment import run_metadata_enrichment
from otto.orchestration.notion_export_hygiene import run_notion_export_hygiene


def _prepare_env(monkeypatch, root: Path) -> None:
    monkeypatch.setenv("OTTO_VAULT_PATH", str(root / "vault"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(root / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(root / "chroma"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(root / "artifacts"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(root / "state"))
    monkeypatch.setenv("OTTO_BRONZE_ROOT", str(root / "bronze"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(root / "logs"))


def _write_hashy_note(vault: Path, folder: str = "Notion") -> Path:
    note = vault / folder / "Project Alpha - e1cf9b796bbf42fc92ac9ffc73386e11.md"
    write_text(
        note,
        "---\n"
        "tags:\n"
        "  - notion\n"
        "---\n\n"
        "# Project Alpha\n"
        "\n"
        "Body of the note.\n",
    )
    return note


def test_metadata_enrichment_handles_long_paths(tmp_path, monkeypatch):
    _prepare_env(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    long_folder = vault
    while len(str(long_folder / "x")) < 265:
        long_folder = long_folder / "Database Central" / "Misc 2024-2025" / "[Archived] 0tt0 Dashboard" / "Journal"
    note = long_folder / "[Untuk Debby Juni] Representasi 2 0 e1cf9b796bbf42fc92ac9ffc73386e11.md"
    write_text(
        note,
        "---\n"
        "title: Representasi 2 0\n"
        "---\n\n"
        "# Representasi 2 0\n"
        "\n"
        "Long path note.\n",
    )

    result = run_metadata_enrichment(mode="review", scope=str(long_folder))

    assert result["target_count"] == 1
    assert result["results"][0]["path"].endswith("e1cf9b796bbf42fc92ac9ffc73386e11.md")


def test_notion_export_hygiene_apply_renames_and_rewrites_links(tmp_path, monkeypatch):
    _prepare_env(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    target = _write_hashy_note(vault)
    ref = vault / "Notion" / "Reference.md"
    write_text(
        ref,
        "---\n"
        "title: Reference\n"
        "---\n\n"
        "See [[Project Alpha - e1cf9b796bbf42fc92ac9ffc73386e11]].\n",
    )

    result = run_notion_export_hygiene(mode="apply", scope="Notion", confirm=True, rewrite_links=True)

    renamed = vault / "Notion" / "Project Alpha.md"
    assert result["renamed_count"] == 1
    assert renamed.exists()
    assert not target.exists()
    renamed_text = renamed.read_text(encoding="utf-8")
    assert "title: Project Alpha" in renamed_text
    assert "aliases:" in renamed_text
    assert "Project Alpha - e1cf9b796bbf42fc92ac9ffc73386e11" in renamed_text
    ref_text = ref.read_text(encoding="utf-8")
    assert "[[Project Alpha]]" in ref_text


def test_notion_export_hygiene_review_surfaces_target_plan(tmp_path, monkeypatch):
    _prepare_env(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    _write_hashy_note(vault)

    result = run_notion_export_hygiene(mode="review", scope="Notion")

    assert result["target_count"] == 1
    assert result["results"][0]["rename_needed"] is True
    assert "hash_suffix" in result["results"][0]["flags"]


def test_notion_export_hygiene_cli_serializes_dates(tmp_path, monkeypatch, capsys):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "manage" / "run_notion_export_hygiene.py"
    spec = importlib.util.spec_from_file_location("run_notion_export_hygiene_script_test", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "run_notion_export_hygiene",
        lambda **kwargs: {
            "status": "ok",
            "results": [{"candidate_frontmatter": {"date": __import__("datetime").date(2026, 4, 28)}}],
        },
    )

    exit_code = module.main([])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["results"][0]["candidate_frontmatter"]["date"] == "2026-04-28"
