from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from otto.orchestration import metadata_enrichment as me
from otto.orchestration.metadata_enrichment import run_metadata_enrichment


def _prepare_env(monkeypatch, root: Path) -> None:
    monkeypatch.setenv("OTTO_VAULT_PATH", str(root / "vault"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(root / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(root / "chroma"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(root / "artifacts"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(root / "state"))
    monkeypatch.setenv("OTTO_BRONZE_ROOT", str(root / "bronze"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(root / "logs"))


def _write_sample_note(vault: Path) -> Path:
    note = vault / "Notes" / "sample.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "title: Sample Note\n"
        "tags:\n"
        "  - Alpha\n"
        "  - alpha\n"
        "aliases: Sample Alias\n"
        "---\n\n"
        "Body with #Gamma, [[Linked Note|alias text]], and [[Second Link]].\n",
        encoding="utf-8",
    )
    return note


def test_metadata_enrichment_review_normalizes_without_writing(tmp_path, monkeypatch):
    _prepare_env(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    note = _write_sample_note(vault)
    original = note.read_text(encoding="utf-8")

    result = run_metadata_enrichment(mode="review", scope="active")

    assert result["mode"] == "review"
    assert result["backend"]["name"] == "metadata_menu"
    assert result["changed_count"] == 0
    assert note.read_text(encoding="utf-8") == original
    assert result["results"][0]["normalized_tags"] == ["Alpha", "Gamma"]
    assert result["results"][0]["wikilinks"] == ["Linked Note", "Second Link"]
    assert result["results"][0]["command_plan"]["command_name"] == "Metadata Menu: Review and normalize metadata"
    assert result["results"][0]["command_plan"]["uri"].startswith("obsidian://adv-uri?")
    assert Path(result["report_path"]).exists()
    assert Path(result["report_md_path"]).exists()


def test_metadata_enrichment_review_serializes_dates_in_report(tmp_path, monkeypatch):
    _prepare_env(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    note = vault / "Notes" / "dated.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "title: Dated Note\n"
        "date: 2026-04-28\n"
        "---\n\n"
        "Body text.\n",
        encoding="utf-8",
    )

    result = run_metadata_enrichment(mode="review", scope="active")
    report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))

    assert result["results"][0]["candidate_frontmatter"]["date"].isoformat() == "2026-04-28"
    assert report["results"][0]["candidate_frontmatter"]["date"] == "2026-04-28"


def test_metadata_enrichment_apply_updates_frontmatter_and_bridge(tmp_path, monkeypatch):
    _prepare_env(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    note = _write_sample_note(vault)

    result = run_metadata_enrichment(mode="apply", scope="active", confirm=True)

    updated = note.read_text(encoding="utf-8")
    assert result["mode"] == "apply"
    assert result["changed_count"] == 1
    assert "tags:" in updated
    assert "Alpha" in updated
    assert "Gamma" in updated
    assert "aliases:" in updated
    assert "Sample Alias" in updated
    assert Path(result["bridge_path"]).exists()
    assert Path(result["checkpoint_path"]).exists()
    assert result["results"][0]["verification"]["matches"] is True


def test_metadata_enrichment_entity_round_trips_wikidata_fields(tmp_path, monkeypatch):
    _prepare_env(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    note = vault / "Notes" / "entity.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "title: Douglas Adams\n"
        "wikidata_id: Q42\n"
        "---\n\n"
        "Short note.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        me,
        "_fetch_wikidata_entity",
        lambda qid, api_base, user_agent, timeout_seconds=20: {
            "qid": qid,
            "label": "Douglas Adams",
            "description": "English writer and humorist",
            "aliases": ["Douglas Noel Adams"],
            "url": "https://www.wikidata.org/wiki/Q42",
        },
    )

    result = run_metadata_enrichment(mode="entity", scope="active", confirm=True)
    updated = note.read_text(encoding="utf-8")

    assert result["backend"]["name"] == "wikidata_importer"
    assert result["results"][0]["wikidata"]["qid"] == "Q42"
    assert "wikidata_label: Douglas Adams" in updated
    assert "wikidata_description: English writer and humorist" in updated
    assert "wikidata_id: Q42" in updated


def test_metadata_enrichment_falls_back_to_metaedit_when_menu_disabled(tmp_path, monkeypatch):
    _prepare_env(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    _write_sample_note(vault)

    monkeypatch.setattr(
        me,
        "load_metadata_enrichment_config",
        lambda: {
            "metadata_enrichment": {
                "core_backend_priority": ["metadata_menu", "metaedit"],
                "entity_backend_priority": ["wikidata_importer", "metadata_menu", "metaedit"],
                "backends": {
                    "metadata_menu": {
                        "enabled": False,
                        "label": "Metadata Menu",
                        "command_labels": {"review": "Metadata Menu: Review"},
                        "write": {"tags": True, "aliases": True, "wikilinks": False, "entity_fields": True},
                    },
                    "metaedit": {
                        "enabled": True,
                        "label": "MetaEdit",
                        "command_labels": {"review": "MetaEdit: Review"},
                        "write": {"tags": True, "aliases": False, "wikilinks": False, "entity_fields": True},
                    },
                    "wikidata_importer": {
                        "enabled": True,
                        "label": "Wikidata Importer",
                        "command_labels": {"entity": "Wikidata Importer: Import"},
                        "write": {"tags": False, "aliases": False, "wikilinks": False, "entity_fields": True},
                    },
                },
            }
        },
    )

    result = run_metadata_enrichment(mode="review", scope="active")

    assert result["backend"]["name"] == "metaedit"
    assert result["backend"]["label"] == "MetaEdit"


def test_metadata_enrichment_dispatch_command_skips_multi_target_scope(tmp_path, monkeypatch):
    _prepare_env(monkeypatch, tmp_path)
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    _write_sample_note(vault)
    extra = vault / "Notes" / "second.md"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("---\ntitle: Second\n---\n\nBody.\n", encoding="utf-8")

    result = run_metadata_enrichment(mode="review", scope="active", dispatch_command=True)

    assert result["target_count"] == 2
    assert all(item.get("command_dispatch", {}).get("skipped") for item in result["results"] if item.get("command_plan"))


def test_metadata_enrichment_cli_serializes_dates(tmp_path, monkeypatch, capsys):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "manage" / "run_metadata_enrichment.py"
    spec = importlib.util.spec_from_file_location("run_metadata_enrichment_script_test", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "run_metadata_enrichment",
        lambda **kwargs: {
            "status": "ok",
            "results": [{"candidate_frontmatter": {"date": __import__("datetime").date(2026, 4, 28)}}],
        },
    )

    exit_code = module.main([])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["results"][0]["candidate_frontmatter"]["date"] == "2026-04-28"
