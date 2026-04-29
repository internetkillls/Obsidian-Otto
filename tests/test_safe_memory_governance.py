from __future__ import annotations

from types import SimpleNamespace

from otto.adapters.obsidian.markdown import render_note
from otto.adapters.obsidian.vault import is_allowed_otto_realm_target
from otto.adapters.obsidian.writeback import (
    create_writeback_candidate,
    evaluate_writeback_policy,
    preview_writeback,
    write_reviewed_by_id,
)
from otto.memory.gold import promote_review_to_gold
from otto.memory.memory_policy import evaluate_memory_export
from otto.memory.promotion import create_candidate, promote_candidate
from otto.memory.review_queue import decide_review, enqueue_candidate


def _patch_paths(monkeypatch, tmp_path):
    state = tmp_path / "state"
    vault = tmp_path / "vault"
    (vault / ".Otto-Realm" / "Handoff").mkdir(parents=True)
    (vault / ".Otto-Realm" / "Brain").mkdir(parents=True)
    paths = SimpleNamespace(state_root=state, vault_path=vault)
    monkeypatch.setattr("otto.governance_utils.load_paths", lambda: paths)
    monkeypatch.setattr("otto.adapters.obsidian.vault.load_paths", lambda: paths)
    return state, vault


def test_vault_paths_allow_only_otto_realm_targets(monkeypatch, tmp_path):
    _state, vault = _patch_paths(monkeypatch, tmp_path)

    assert is_allowed_otto_realm_target(vault / ".Otto-Realm" / "Handoff" / "x.md", root=vault)
    assert not is_allowed_otto_realm_target(vault / "random.md", root=vault)


def test_writeback_blocks_raw_social(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    policy = evaluate_writeback_policy(
        {
            "kind": "social_raw",
            "status": "reviewed",
            "privacy": "private",
            "target_path": str(tmp_path / "vault" / ".Otto-Realm" / "Handoff" / "x.md"),
        }
    )

    assert policy["allowed_to_write"] is False
    assert "raw_social_blocked" in policy["blocked_reasons"]


def test_writeback_blocks_candidate_profile_claim(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    policy = evaluate_writeback_policy(
        {
            "kind": "profile_claim_candidate",
            "domain": "profile",
            "status": "candidate",
            "privacy": "private_reviewed",
            "target_path": str(tmp_path / "vault" / ".Otto-Realm" / "Brain" / "x.md"),
        }
    )

    assert policy["allowed_to_write"] is False
    assert policy["blocked_reason"] in {
        "candidate_profile_claim_blocked",
        "unreviewed_profile_or_psychometric_claim_blocked",
    }


def test_markdown_renderer_includes_frontmatter():
    rendered = render_note(
        {
            "writeback_id": "wb_test",
            "kind": "handoff_note",
            "status": "reviewed",
            "source_refs": ["state/runtime/smoke_last.json"],
            "privacy": "private_reviewed",
            "title": "Otto Handoff",
            "body": "Safe bridge.",
        }
    )

    assert rendered.startswith("---\notto_type: handoff_note")
    assert "otto_writeback_id: wb_test" in rendered
    assert "source_refs:" in rendered


def test_writeback_dry_run_does_not_touch_vault(monkeypatch, tmp_path):
    _state, vault = _patch_paths(monkeypatch, tmp_path)

    candidate = create_writeback_candidate(dry_run=True)["candidate"]
    result = write_reviewed_by_id(candidate["writeback_id"], dry_run=True)

    assert result["ok"] is True
    assert not (vault / ".Otto-Realm" / "Handoff" / "2026-04-29.md").exists()


def test_writeback_reviewed_writes_file_and_records_last(monkeypatch, tmp_path):
    state, vault = _patch_paths(monkeypatch, tmp_path)

    candidate = create_writeback_candidate(dry_run=True)["candidate"]
    preview = preview_writeback(candidate["writeback_id"])
    result = write_reviewed_by_id(candidate["writeback_id"], dry_run=False)

    assert preview["ok"] is True
    assert result["ok"] is True
    assert (vault / ".Otto-Realm" / "Handoff").glob("*.md")
    assert (state / "exports" / "obsidian" / "writeback_last.json").exists()


def test_memory_policy_blocks_raw_and_candidate_export(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    raw = evaluate_memory_export({"state": "RAW", "kind": "social_raw", "privacy": "sensitive"})
    candidate = evaluate_memory_export({"state": "CANDIDATE", "kind": "handoff_note", "evidence_refs": ["x"]})

    assert raw["qmd_index_allowed"] is False
    assert raw["vault_writeback_allowed"] is False
    assert candidate["qmd_index_allowed"] is False


def test_candidate_requires_evidence_and_promotion_explains_blockers(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    blocked = enqueue_candidate({"candidate_id": "cand_nope", "state": "CANDIDATE", "evidence_refs": []})
    candidate = create_candidate(dry_run=True)["candidate"]
    promotion = promote_candidate(candidate["candidate_id"], dry_run=True)

    assert blocked["ok"] is False
    assert promotion["ok"] is True
    assert promotion["promotion"]["next_state"] == "REVIEW_REQUIRED"
    assert "qmd" in promotion["promotion"]["blocked_outputs"]


def test_review_approve_promotes_to_gold(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    candidate = create_candidate(dry_run=True)["candidate"]
    review = enqueue_candidate(candidate, dry_run=False)["review"]
    decision = decide_review(review["review_id"], "approved", note="safe", dry_run=False)
    gold = promote_review_to_gold(review["review_id"], dry_run=False)

    assert decision["ok"] is True
    assert gold["ok"] is True
    assert gold["gold"]["state"] == "GOLD"
    assert gold["gold"]["qmd_index_allowed"] is True
