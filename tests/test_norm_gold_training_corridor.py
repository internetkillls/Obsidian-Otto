from __future__ import annotations

from pathlib import Path

import yaml

from otto.corridor import split_frontmatter
from otto.gold.gold_audit import build_gold_audit
from otto.gold.gold_compiler import compile_gold_candidate
from otto.gold_rehab.auto_append import apply_safe_enrichment
from otto.gold_rehab.discuss_later import discuss_later_path
from otto.gold_rehab.patch_ledger import patch_ledger_path
from otto.gold_rehab.review_needed import review_needed_path
from otto.gold_rehab.rollback_patch import rollback_patch_dry_run
from otto.governance_utils import append_jsonl, read_jsonl
from otto.memory.source_registry import validate_source_registry
from otto.normalize.source_normalizer import normalize_event_payload
from otto.enrichment.silver_to_candidate import create_candidate_from_event
from otto.enrichment.candidate_enricher import enrich_candidate
from otto.enrichment.gold_readiness import evaluate_gold_readiness
from otto.features.feature_vector import create_feature_vector
from otto.training.training_manifest import build_training_candidates, build_training_manifest


def _set_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))
    (tmp_path / "vault").mkdir(parents=True, exist_ok=True)


def test_norm_to_gold_to_training_corridor(monkeypatch, tmp_path):
    _set_env(monkeypatch, tmp_path)

    silver = normalize_event_payload(
        source="vault:research/interface-constraints.md",
        text="Interface constraints shape research onboarding, seminar survival, and critique readiness.",
        kind="idea_fragment",
        dry_run=False,
    )["silver_event"]
    fv = create_feature_vector(silver["event_id"], dry_run=False)["feature_vector"]
    candidate = create_candidate_from_event(silver["event_id"], dry_run=False)["candidate_insight"]
    enriched = enrich_candidate(candidate["candidate_id"], dry_run=False)["enriched_candidate"]
    readiness = evaluate_gold_readiness(candidate["candidate_id"], dry_run=False)["gold_readiness"]

    append_jsonl(
        tmp_path / "state" / "memory" / "reviewed.jsonl",
        {
            "review_id": "rev_contract_001",
            "item_id": candidate["candidate_id"],
            "state": "APPROVED",
            "kind": candidate["kind"],
            "evidence_refs": candidate["evidence_refs"],
        },
    )
    gold = compile_gold_candidate(candidate["candidate_id"], dry_run=False)["gold"]
    training = build_training_candidates()
    manifest = build_training_manifest()["manifest"]

    assert silver["state"] == "SILVER_EVENT"
    assert fv["state"] == "FEATURE_VECTOR"
    assert fv["qmd_index_allowed"] is False
    assert candidate["state"] == "CANDIDATE_INSIGHT"
    assert candidate["qmd_index_allowed"] is False
    assert enriched["state"] == "ENRICHED_CANDIDATE"
    assert readiness["gold_readiness"]["overall"] >= readiness["thresholds"]["gold_candidate"]
    assert gold["state"] == "GOLD"
    assert gold["review_id"] == "rev_contract_001"
    assert gold["qmd_index_allowed"] is True
    assert training["ok"] is True
    assert len(training["training_candidates"]) == 1
    assert manifest["item_count"] == 1


def test_gold_rehab_auto_append_preserves_human_fields_and_ledgers(monkeypatch, tmp_path):
    _set_env(monkeypatch, tmp_path)
    note = tmp_path / "vault" / "Interface Note.md"
    note.write_text(
        "---\n"
        "title: Human title\n"
        "tags:\n"
        "  - human-tag\n"
        "---\n\n"
        "Interface as constraint machine for research onboarding.\n",
        encoding="utf-8",
    )

    append_jsonl(
        tmp_path / "state" / "gold_rehab" / "semantic_enrichment_candidates.jsonl",
        {
            "path": str(note),
            "title": "Human title",
            "risk": "R1_LOW_RISK_SEMANTIC",
            "otto": {
                "state": "G1_MECHANICALLY_REPAIRED",
                "enriched_by": "otto",
                "enrichment_version": 1,
                "source_checksum": "sha256:test",
                "review_status": "auto_applied_low_risk",
                "qmd_index_allowed": False,
                "vault_writeback_allowed": False,
                "provenance": {"method": "gold_rehab_safe_append"},
            },
            "otto_suggestions": {
                "suggested_kind": [{"value": "research_note", "confidence": 0.74}],
                "suggested_tags": [{"tag": "interface", "confidence": 0.71}],
                "suggested_entities": ["interface", "constraint"],
            },
            "markdown_block": "<!-- OTTO:ENRICHMENT v1 risk=R1_LOW_RISK_SEMANTIC review=auto_applied_low_risk -->\n## Otto Enrichment\n<!-- /OTTO:ENRICHMENT -->",
        },
    )

    result = apply_safe_enrichment(risk_max="R1_LOW_RISK_SEMANTIC", batch_size=1)
    patch = read_jsonl(patch_ledger_path())[0]
    rollback = rollback_patch_dry_run(str(patch["patch_id"]))

    fm, body, had_frontmatter = split_frontmatter(note.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert had_frontmatter is True
    assert fm["tags"] == ["human-tag"]
    assert fm["otto"]["state"] == "G1_MECHANICALLY_REPAIRED"
    assert fm["otto_suggestions"]["suggested_tags"][0]["tag"] == "interface"
    assert "OTTO:ENRICHMENT" in body
    assert patch["reversible"] is True
    assert rollback["ok"] is True
    assert rollback["reversible"] is True


def test_gold_rehab_risky_items_queue_instead_of_auto_apply(monkeypatch, tmp_path):
    _set_env(monkeypatch, tmp_path)
    note = tmp_path / "vault" / "Profile Note.md"
    note.write_text("# Profile Note\n\nAuDHD support context only.\n", encoding="utf-8")

    append_jsonl(
        tmp_path / "state" / "gold_rehab" / "semantic_enrichment_candidates.jsonl",
        {
            "path": str(note),
            "title": "Profile Note",
            "risk": "R3_REVIEW_REQUIRED",
            "otto": {"state": "G4_REVIEW_READY"},
            "otto_suggestions": {},
            "markdown_block": "Potential weakness/support claim.",
        },
    )

    result = apply_safe_enrichment(risk_max="R1_LOW_RISK_SEMANTIC", batch_size=1)

    assert result["ok"] is True
    assert len(read_jsonl(review_needed_path())) == 1
    assert len(read_jsonl(discuss_later_path())) == 0
    assert len(read_jsonl(patch_ledger_path())) == 0


def test_gold_audit_allows_zero_gold_when_rehab_path_is_active(monkeypatch, tmp_path):
    _set_env(monkeypatch, tmp_path)
    append_jsonl(
        tmp_path / "state" / "gold_rehab" / "review_needed.jsonl",
        {
            "review_id": "grev_001",
            "risk": "R3_REVIEW_REQUIRED",
            "path": "vault:note.md",
        },
    )

    audit = build_gold_audit()["audit"]

    assert audit["gold_count"] == 0
    assert audit["rehab_active"] is True
    assert audit["ok"] is True


def test_source_registry_blocks_feature_vector_qmd_index():
    result = validate_source_registry(
        {
            "version": 1,
            "sources": [
                {
                    "id": "feature-vector-store",
                    "kind": "feature_vector",
                    "path_windows": "C:/repo/state/features",
                    "path_wsl": "/mnt/c/repo/state/features",
                    "required": False,
                    "qmd_index": True,
                    "vault_writeback": False,
                    "privacy": "private",
                    "owner": "otto",
                }
            ],
        }
    )

    assert result["ok"] is False
    assert "raw-source-qmd-enabled:feature-vector-store" in result["errors"]
