from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_graph_rollup_module():
    repo = Path(__file__).resolve().parents[1]
    script_path = repo / "scripts" / "c4_graph_rollup_audit.py"
    sys.path.insert(0, str(repo / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location("graph_rollup_audit", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_policy_demotes_sentence_like_allocation():
    mod = _load_graph_rollup_module()
    ref = mod.EntityRef(
        kind="allocation",
        value="Integrate key findings into thesis argument; verify cross-references to primary sources are accurate.",
        label="Integrate key findings into thesis argument; verify cross-references to primary sources are accurate.",
        slug="ALLO-integrate-key-findings",
        file_path=Path("00-Meta/allocation/ALLO-integrate-key-findings.md"),
        moc_target="ALLOCATION-FAMILY",
        pillar="ALLOCATION",
    )

    decision = mod._policy_decision(
        kind="allocation",
        value=ref.value,
        ref=ref,
        inventory_entry={"normalized_key": "integrate_key_findings", "notes": ["Projects/A.md"], "values": [ref.value]},
        existing_by_label={},
        protected_cfg={"protected_entities": [], "protected_families": []},
        block_words=set(),
        go_words=set(),
        semantic_threshold=0.78,
    )

    assert decision.decision == "demote_frontmatter"
    assert decision.reason == "granular_allocation_sentence"


def test_policy_keeps_reused_stable_label():
    mod = _load_graph_rollup_module()
    ref = mod.EntityRef(
        kind="scarcity",
        value="legitimation",
        label="legitimation",
        slug="LACK-legitimation",
        file_path=Path("00-Meta/scarcity/LACK-legitimation.md"),
        moc_target="VOICE",
        pillar="SCARCITY",
    )

    decision = mod._policy_decision(
        kind="scarcity",
        value=ref.value,
        ref=ref,
        inventory_entry={
            "normalized_key": "legitimation",
            "notes": ["Projects/A.md", "Projects/B.md", "Projects/C.md"],
            "values": [ref.value],
        },
        existing_by_label={"legitimation": Path("00-Meta/scarcity/LACK-legitimation.md")},
        protected_cfg={"protected_entities": [], "protected_families": []},
        block_words=set(),
        go_words=set(),
        semantic_threshold=0.78,
    )

    assert decision.decision == "keep"
    assert decision.score_breakdown["reuse_count"] == 3


def test_policy_respects_protected_entity():
    mod = _load_graph_rollup_module()
    ref = mod.EntityRef(
        kind="allocation",
        value="synthesize",
        label="synthesize",
        slug="ALLO-synthesize",
        file_path=Path("00-Meta/allocation/ALLO-synthesize.md"),
        moc_target="ALLOCATION-FAMILY",
        pillar="ALLOCATION",
    )

    decision = mod._policy_decision(
        kind="allocation",
        value=ref.value,
        ref=ref,
        inventory_entry={"normalized_key": "synthesize", "notes": ["Projects/A.md"], "values": [ref.value]},
        existing_by_label={"synthesize": Path("00-Meta/allocation/ALLO-synthesize.md")},
        protected_cfg={
            "protected_entities": [{"kind": "allocation", "slug": "ALLO-synthesize", "reason": "human expensive node"}],
            "protected_families": [],
        },
        block_words=set(),
        go_words=set(),
        semantic_threshold=0.78,
    )

    assert decision.decision == "keep"
    assert decision.protected is True
    assert decision.reason == "human expensive node"


def test_shadow_artifact_emits_hidden_relations_for_shared_demotions():
    mod = _load_graph_rollup_module()
    artifact = mod._shadow_machine_artifact(
        entities=[
            {
                "note": "Projects/A.md",
                "kind": "allocation",
                "value": "Integrate findings into thesis",
                "normalized_key": "integrate_findings_into_thesis",
                "decision": "demote_frontmatter",
                "reason": "granular_allocation_sentence",
                "merge_target": "ALLOCATION-FAMILY",
            },
            {
                "note": "Projects/B.md",
                "kind": "allocation",
                "value": "Integrate findings into thesis",
                "normalized_key": "integrate_findings_into_thesis",
                "decision": "demote_frontmatter",
                "reason": "granular_allocation_sentence",
                "merge_target": "ALLOCATION-FAMILY",
            },
        ],
        protected_hits=[],
    )

    assert artifact["decisions"][0]["decision"] == "demote_frontmatter"
    assert artifact["merge_targets"] == []
    assert artifact["hidden_relations"][0]["relation"] == "shared_shadow_entity"


def test_shadow_review_groups_proposals_by_prefix():
    mod = _load_graph_rollup_module()
    artifact = mod._shadow_machine_artifact(
        entities=[
            {
                "note": "Projects/A.md",
                "kind": "allocation",
                "value": "Integrate findings into thesis",
                "normalized_key": "integrate_findings_into_thesis",
                "decision": "ignore_route",
                "reason": "route_like_low_reuse",
                "merge_target": "ALLOCATION-FAMILY",
                "protected": False,
            },
            {
                "note": "Projects/A2.md",
                "kind": "allocation",
                "value": "Micro tactical note-local label",
                "normalized_key": "micro_tactical_note_local_label",
                "decision": "demote_tag",
                "reason": "small_local_allocation",
                "merge_target": "ALLO-MICRO",
                "protected": False,
            },
            {
                "note": "Projects/B.md",
                "kind": "orientation",
                "value": "support thesis",
                "normalized_key": "support_thesis",
                "decision": "keep",
                "reason": "stable_or_reused",
                "merge_target": "ORIENTATION-FAMILY",
                "protected": False,
            },
            {
                "note": "Projects/B2.md",
                "kind": "allocation",
                "value": "synthesize",
                "normalized_key": "synthesize",
                "decision": "keep",
                "reason": "human expensive node",
                "merge_target": "ALLOCATION-FAMILY",
                "protected": True,
            },
            {
                "note": "Projects/C.md",
                "kind": "scarcity",
                "value": "legitimation",
                "normalized_key": "legitimation",
                "decision": "merge_into_family",
                "reason": "merge_to_existing_or_family",
                "merge_target": "VOICE",
                "protected": False,
            },
        ],
        protected_hits=[],
    )

    groups = {item["prefix"]: item for item in artifact["review_groups"]}
    assert groups["ALLO-*"]["family_groups"][0]["family"] == "ALLO-MICRO"
    assert groups["ALLO-*"]["family_groups"][0]["primary_triage"] == "cheap_metadata"
    assert groups["ALLO-*"]["triage_counts"]["human_expensive_keep"] == 1
    assert groups["TO-*"]["decision_counts"]["keep"] == 1
    assert groups["LACK-*"]["family_groups"][0]["family"] == "VOICE"
    review_md = mod._shadow_review_markdown(artifact)
    assert "## ALLO-* Review" in review_md
    assert "## TO-* Review" in review_md
    assert "## LACK-* Review" in review_md
    assert "human_expensive_keep" in review_md
    summary_table = mod._shadow_family_summary_table(artifact)
    assert "Prefix" in summary_table
    assert "ALLO-*" in summary_table
    assert "human_expensive_keep" in summary_table
    assert "Action" in summary_table
    csv_rows = mod._shadow_family_csv_rows(artifact)
    assert csv_rows[0]["family"] == "ALLO-MICRO"
    assert csv_rows[0]["triage"] == "cheap_metadata"
    assert csv_rows[0]["action"] in {"convert to tag", "demote frontmatter"}
    assert csv_rows[0]["why"]
    filtered_table = mod._shadow_family_summary_table(artifact, family_prefix="ALLO")
    assert "ALLO-*" in filtered_table
    assert "TO-*" not in filtered_table
    filtered_rows = mod._shadow_family_csv_rows(artifact, family_prefix="LACK")
    assert len(filtered_rows) == 1
    assert filtered_rows[0]["prefix"] == "LACK-*"
    filtered_triage_rows = mod._shadow_family_csv_rows(artifact, family_prefix="ALLO", only_triage="cheap_metadata")
    assert len(filtered_triage_rows) == 1
    assert filtered_triage_rows[0]["family"] == "ALLO-MICRO"
    filtered_action_rows = mod._shadow_family_csv_rows(artifact, family_prefix="ALLO", only_action="convert to tag")
    assert len(filtered_action_rows) == 1
    assert filtered_action_rows[0]["action"] == "convert to tag"
    top_limited_table = mod._shadow_family_summary_table(artifact, top_family_rows=1)
    assert "ALLO-MICRO" in top_limited_table
    assert "ALLOCATION-FAMILY" not in top_limited_table
    assert "TO-*" not in top_limited_table
    allo_hotspots_md = mod._allo_hotspots_markdown(artifact)
    assert "# ALLO Inflation Hotspots" in allo_hotspots_md
    assert "highest cleanup payoff first" in allo_hotspots_md
    assert "ALLO-MICRO" in allo_hotspots_md


def test_demotion_plan_preview_proposes_note_level_rewrite(scratch_path):
    mod = _load_graph_rollup_module()
    vault = scratch_path / "vault"
    note = vault / "Projects" / "Specific Synthesis.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "allocation: specific synthesis\n"
        "---\n"
        "# Specific Synthesis\n",
        encoding="utf-8",
    )

    artifact = mod._demotion_plan_artifact(
        vault=vault,
        shadow_entities=[
            {
                "note": "Projects/Specific Synthesis.md",
                "kind": "allocation",
                "value": "specific synthesis",
                "decision": "demote_tag",
                "reason": "small_local_allocation",
                "merge_target": "ALLOCATION-FAMILY",
            }
        ],
        dry_run=True,
    )
    markdown = mod._demotion_plan_markdown(artifact)

    assert artifact["plan_count"] == 1
    plan = artifact["plans"][0]
    assert plan["action"] == "convert to tag"
    assert plan["after"]["tags"] == ["allocation/specific-synthesis"]
    assert "allocation:" not in plan["after"]
    assert "# Demotion Plan Preview" in markdown
    assert "Projects/Specific Synthesis.md" in markdown
    assert "allocation/specific-synthesis" in markdown


def test_apply_demotion_plan_writes_note_and_records_result(scratch_path):
    mod = _load_graph_rollup_module()
    vault = scratch_path / "vault"
    note = vault / "Projects" / "Applied Synthesis.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "allocation: specific synthesis\n"
        "---\n"
        "# Applied Synthesis\n",
        encoding="utf-8",
    )

    artifact = mod._demotion_plan_artifact(
        vault=vault,
        shadow_entities=[
            {
                "note": "Projects/Applied Synthesis.md",
                "kind": "allocation",
                "value": "specific synthesis",
                "decision": "demote_tag",
                "reason": "small_local_allocation",
                "merge_target": "ALLOCATION-FAMILY",
            }
        ],
        dry_run=False,
    )
    result = mod._apply_demotion_plan(vault=vault, artifact=artifact, max_writes=5)
    updated = note.read_text(encoding="utf-8")

    assert artifact["applied_count"] == 1
    assert artifact["skipped_count"] == 0
    assert result["applied"][0]["note"] == "Projects/Applied Synthesis.md"
    assert "allocation: specific synthesis" not in updated
    assert "allocation/specific-synthesis" in updated
    assert "# Applied Synthesis" in updated


def test_apply_demotion_plan_rebases_multiple_entries_on_same_note(scratch_path):
    mod = _load_graph_rollup_module()
    vault = scratch_path / "vault"
    note = vault / "Projects" / "Dual Apply.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "allocation: write + update positioning stack; maintain research spine\n"
        "orientation: multiregister self-positioning (academic / professional / public)\n"
        "---\n"
        "# Dual Apply\n",
        encoding="utf-8",
    )

    artifact = mod._demotion_plan_artifact(
        vault=vault,
        shadow_entities=[
            {
                "note": "Projects/Dual Apply.md",
                "kind": "allocation",
                "value": "write + update positioning stack; maintain research spine",
                "decision": "demote_frontmatter",
                "reason": "granular_allocation_sentence",
                "merge_target": "ALLOCATION-FAMILY",
            },
            {
                "note": "Projects/Dual Apply.md",
                "kind": "orientation",
                "value": "multiregister self-positioning (academic / professional / public)",
                "decision": "demote_frontmatter",
                "reason": "sentence_like_orientation",
                "merge_target": "ORIENTATION-FAMILY",
            },
        ],
        dry_run=False,
    )
    mod._apply_demotion_plan(vault=vault, artifact=artifact, max_writes=5)

    _, _, frontmatter = mod._split_frontmatter_raw(note.read_text(encoding="utf-8"))
    assert frontmatter.get("allocation") is None
    assert frontmatter.get("orientation") is None
    assert frontmatter.get("allocation_detail") == "write + update positioning stack; maintain research spine"
    assert frontmatter.get("orientation_detail") == "multiregister self-positioning (academic / professional / public)"


def test_match_frontmatter_value_normalizes_datetime_null_and_wikilinks():
    mod = _load_graph_rollup_module()

    assert mod._match_frontmatter_value(mod.datetime.fromisoformat("2025-11-08T17:04:50"), "2025-11-08T17:04:50")
    assert mod._match_frontmatter_value(None, "null")
    assert mod._match_frontmatter_value([["crack-research-framework"]], "[[crack-research-framework]]")


def test_graph_review_next_action_skips_openclaw_when_not_ready(scratch_path):
    mod = _load_graph_rollup_module()
    vault = scratch_path / "vault"
    note = vault / "Projects" / "Mismatch.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "allocation: specific synthesis\n"
        "---\n"
        "# Mismatch\n",
        encoding="utf-8",
    )

    demotion_plan_artifact = {
        "mode": "apply",
        "applied_count": 1,
        "skipped_count": 0,
        "plans": [
            {
                "note": "Projects/Mismatch.md",
                "kind": "allocation",
                "decision": "demote_frontmatter",
                "reason": "granular_allocation_sentence",
                "current_value": "specific synthesis",
                "merge_target": "ALLOCATION-FAMILY",
                "action": "demote frontmatter",
                "before": {"allocation": "specific synthesis"},
                "after": {"allocation_detail": "specific synthesis"},
            }
        ],
        "applied": [
            {
                "note": "Projects/Mismatch.md",
                "action": "demote frontmatter",
                "decision": "demote_frontmatter",
                "reason": "granular_allocation_sentence",
            }
        ],
    }
    review = mod._build_graph_demotion_review_artifact(
        vault=vault,
        demotion_plan_artifact=demotion_plan_artifact,
        shadow_artifact={"review_groups": []},
        checkpoint_payload={"ts": "2026-04-25T02:10:15+07:00"},
    )

    assert review["ready_for_openclaw_fetch"] is False
    assert "OpenClaw fetch" not in review["recommended_next_action"]
    assert "rerun the bounded batch" in review["recommended_next_action"]


def test_review_applied_entry_ignore_route_accepts_tag_subset(scratch_path):
    mod = _load_graph_rollup_module()
    vault = scratch_path / "vault"
    note = vault / "Projects" / "Ignore Route.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\n"
        "tags:\n"
        "  - allocation/first-tag\n"
        "  - orientation/second-tag\n"
        "---\n"
        "# Ignore Route\n",
        encoding="utf-8",
    )

    ok, issues = mod._review_applied_entry(
        note,
        {
            "kind": "allocation",
            "decision": "ignore_route",
            "after": {"tags": ["allocation/first-tag"]},
            "before": {"allocation": "review the route"},
        },
    )

    assert ok is True
    assert issues == []


def test_main_writes_shadow_graph_artifacts_for_demoted_candidates(scratch_path, monkeypatch):
    mod = _load_graph_rollup_module()
    repo = scratch_path / "repo"
    vault = scratch_path / "vault"
    (repo / "config").mkdir(parents=True)
    (repo / "state" / "openclaw").mkdir(parents=True)
    (repo / "state" / "pids").mkdir(parents=True)
    (repo / "state" / "handoff" / "from_cowork").mkdir(parents=True)
    (vault / "Projects").mkdir(parents=True)
    (vault / "00-Meta").mkdir(parents=True)

    (repo / "config" / "graph_shaper_noise_words.json").write_text(
        json.dumps({"block_words": [], "go_words": []}),
        encoding="utf-8",
    )
    (repo / "config" / "graph_shadow_protected_nodes.json").write_text(
        json.dumps({"protected_entities": [], "protected_families": []}),
        encoding="utf-8",
    )
    (vault / "Projects" / "Thesis Working Note.md").write_text(
        "---\n"
        "allocation: Integrate key findings into thesis argument; verify cross-references to primary sources are accurate.\n"
        "orientation: support thesis\n"
        "---\n"
        "# Thesis Working Note\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_repo_root", lambda: repo)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "c4_graph_rollup_audit.py",
            "--vault",
            str(vault),
            "--scope",
            "full",
            "--batch-size",
            "10",
            "--output",
            "state/run_journal/graph_shape_audit.json",
            "--markdown-output",
            "state/run_journal/graph_shape_audit.md",
            "--shadow-output",
            "state/run_journal/graph_shadow_decisions.json",
            "--shadow-markdown-output",
            "state/run_journal/graph_shadow_decisions.md",
            "--shadow-review-output",
            "state/run_journal/graph_shadow_review.md",
        ],
    )

    exit_code = mod.main()
    assert exit_code == 0

    shadow_json = repo / "state" / "run_journal" / "graph_shadow_decisions.json"
    shadow_md = repo / "state" / "run_journal" / "graph_shadow_decisions.md"
    shadow_review_md = repo / "state" / "run_journal" / "graph_shadow_review.md"
    report_json = repo / "state" / "run_journal" / "graph_shape_audit.json"

    artifact = json.loads(shadow_json.read_text(encoding="utf-8"))
    report = json.loads(report_json.read_text(encoding="utf-8"))
    markdown = shadow_md.read_text(encoding="utf-8")
    review_markdown = shadow_review_md.read_text(encoding="utf-8")
    allocation_decisions = [
        item["decision"]
        for item in artifact["entities"]
        if item.get("kind") == "allocation"
    ]

    assert shadow_json.exists()
    assert shadow_md.exists()
    assert shadow_review_md.exists()
    assert artifact["entities"]
    assert allocation_decisions
    assert any(
        decision in {"demote_frontmatter", "demote_tag", "merge_into_family", "ignore_route"}
        for decision in allocation_decisions
    )
    assert "Inflation Hotspots" in markdown
    assert "allocation" in markdown.lower()
    assert "## ALLO-* Review" in review_markdown
    assert report["shadow_graph"]["decision_count"] >= 1
    assert report["shadow_graph"]["review_groups"] >= 1
    assert report["shadow_graph"]["allo_hotspots_markdown"].endswith("graph_allo_hotspots.md")


def test_main_prints_family_summary_table(scratch_path, monkeypatch, capsys):
    mod = _load_graph_rollup_module()
    repo = scratch_path / "repo"
    vault = scratch_path / "vault"
    (repo / "config").mkdir(parents=True)
    (repo / "state" / "openclaw").mkdir(parents=True)
    (repo / "state" / "pids").mkdir(parents=True)
    (repo / "state" / "handoff" / "from_cowork").mkdir(parents=True)
    (vault / "Projects").mkdir(parents=True)
    (vault / "00-Meta").mkdir(parents=True)

    (repo / "config" / "graph_shaper_noise_words.json").write_text(
        json.dumps({"block_words": [], "go_words": []}),
        encoding="utf-8",
    )
    (repo / "config" / "graph_shadow_protected_nodes.json").write_text(
        json.dumps(
            {
                "protected_entities": [
                    {"kind": "allocation", "slug": "ALLO-synthesize", "reason": "human expensive node"}
                ],
                "protected_families": [],
            }
        ),
        encoding="utf-8",
    )
    (vault / "Projects" / "Node Inflation Note.md").write_text(
        "---\n"
        "allocation: synthesize\n"
        "orientation: support thesis\n"
        "---\n"
        "# Node Inflation Note\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_repo_root", lambda: repo)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "c4_graph_rollup_audit.py",
            "--vault",
            str(vault),
            "--scope",
            "full",
            "--batch-size",
            "10",
            "--shadow-review-output",
            "state/run_journal/graph_shadow_review.md",
            "--print-family-summary",
            "--top-family-rows",
            "1",
        ],
    )

    exit_code = mod.main()
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Prefix" in captured
    assert "Family" in captured
    assert "ALLO-*" in captured
    assert "human_expensive_keep" in captured
    assert "Action" in captured
    assert "TO-*" not in captured


def test_main_prints_dry_run_demotion_plan_and_writes_allo_hotspots(scratch_path, monkeypatch, capsys):
    mod = _load_graph_rollup_module()
    repo = scratch_path / "repo"
    vault = scratch_path / "vault"
    (repo / "config").mkdir(parents=True)
    (repo / "state" / "openclaw").mkdir(parents=True)
    (repo / "state" / "pids").mkdir(parents=True)
    (repo / "state" / "handoff" / "from_cowork").mkdir(parents=True)
    (vault / "Projects").mkdir(parents=True)
    (vault / "00-Meta").mkdir(parents=True)

    (repo / "config" / "graph_shaper_noise_words.json").write_text(
        json.dumps({"block_words": [], "go_words": []}),
        encoding="utf-8",
    )
    (repo / "config" / "graph_shadow_protected_nodes.json").write_text(
        json.dumps({"protected_entities": [], "protected_families": []}),
        encoding="utf-8",
    )
    (vault / "Projects" / "Dry Run Note.md").write_text(
        "---\n"
        "allocation: specific synthesis\n"
        "---\n"
        "# Dry Run Note\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_repo_root", lambda: repo)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "c4_graph_rollup_audit.py",
            "--vault",
            str(vault),
            "--scope",
            "full",
            "--batch-size",
            "10",
            "--apply-demotion-plan",
            "--dry-run",
            "--demotion-plan-output",
            "state/run_journal/graph_demotion_plan.md",
            "--demotion-plan-json-output",
            "state/run_journal/graph_demotion_plan.json",
            "--allo-hotspots-output",
            "state/run_journal/graph_allo_hotspots.md",
        ],
    )

    exit_code = mod.main()
    assert exit_code == 0
    captured = capsys.readouterr().out
    plan_md = repo / "state" / "run_journal" / "graph_demotion_plan.md"
    plan_json = repo / "state" / "run_journal" / "graph_demotion_plan.json"
    allo_hotspots = repo / "state" / "run_journal" / "graph_allo_hotspots.md"

    assert "# Demotion Plan Preview" in captured
    assert "Dry Run Note.md" in captured
    assert plan_md.exists()
    assert plan_json.exists()
    assert allo_hotspots.exists()
    assert "allocation/specific-synthesis" in plan_md.read_text(encoding="utf-8")
    hotspots_text = allo_hotspots.read_text(encoding="utf-8")
    assert "# ALLO Inflation Hotspots" in hotspots_text
    assert "highest cleanup payoff first" in hotspots_text


def test_main_applies_demotion_plan_to_note(scratch_path, monkeypatch):
    mod = _load_graph_rollup_module()
    repo = scratch_path / "repo"
    vault = scratch_path / "vault"
    (repo / "config").mkdir(parents=True)
    (repo / "state" / "openclaw").mkdir(parents=True)
    (repo / "state" / "pids").mkdir(parents=True)
    (repo / "state" / "handoff" / "from_cowork").mkdir(parents=True)
    (vault / "Projects").mkdir(parents=True)
    (vault / "00-Meta").mkdir(parents=True)

    (repo / "config" / "graph_shaper_noise_words.json").write_text(
        json.dumps({"block_words": [], "go_words": []}),
        encoding="utf-8",
    )
    (repo / "config" / "graph_shadow_protected_nodes.json").write_text(
        json.dumps({"protected_entities": [], "protected_families": []}),
        encoding="utf-8",
    )
    note = vault / "Projects" / "Apply Mode Note.md"
    note.write_text(
        "---\n"
        "allocation: specific synthesis\n"
        "---\n"
        "# Apply Mode Note\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_repo_root", lambda: repo)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "c4_graph_rollup_audit.py",
            "--vault",
            str(vault),
            "--scope",
            "full",
            "--batch-size",
            "10",
            "--apply-demotion-plan",
            "--max-demotion-writes",
            "3",
            "--demotion-plan-output",
            "state/run_journal/graph_demotion_plan.md",
            "--demotion-plan-json-output",
            "state/run_journal/graph_demotion_plan.json",
            "--allo-hotspots-output",
            "state/run_journal/graph_allo_hotspots.md",
        ],
    )

    exit_code = mod.main()
    assert exit_code == 0
    report = json.loads((repo / "state" / "run_journal" / "graph_shape_audit.json").read_text(encoding="utf-8"))
    plan = json.loads((repo / "state" / "run_journal" / "graph_demotion_plan.json").read_text(encoding="utf-8"))
    updated = note.read_text(encoding="utf-8")

    assert report["shadow_graph"]["demotion_applied_count"] == 1
    assert plan["mode"] == "apply"
    assert plan["applied_count"] == 1
    assert "allocation/specific-synthesis" in updated
    assert "allocation: specific synthesis" not in updated


def test_main_writes_graph_review_and_canonical_bridge_drop(scratch_path, monkeypatch):
    mod = _load_graph_rollup_module()
    repo = scratch_path / "repo"
    vault = scratch_path / "vault"
    (repo / "config").mkdir(parents=True)
    (repo / "state" / "openclaw").mkdir(parents=True)
    (repo / "state" / "pids").mkdir(parents=True)
    (repo / "state" / "handoff" / "from_cowork").mkdir(parents=True)
    (repo / "state" / "run_journal" / "checkpoints").mkdir(parents=True)
    (vault / "Projects").mkdir(parents=True)
    (vault / "00-Meta").mkdir(parents=True)

    (repo / "config" / "graph_shaper_noise_words.json").write_text(
        json.dumps({"block_words": [], "go_words": []}),
        encoding="utf-8",
    )
    (repo / "config" / "graph_shadow_protected_nodes.json").write_text(
        json.dumps({"protected_entities": [], "protected_families": []}),
        encoding="utf-8",
    )
    (repo / "state" / "run_journal" / "checkpoints" / "2026-04-25_021015_graph_shadow_demotion_apply.json").write_text(
        json.dumps({"ts": "2026-04-25T02:10:15+07:00"}),
        encoding="utf-8",
    )
    note = vault / "Projects" / "Canonical Bridge Note.md"
    note.write_text(
        "---\n"
        "allocation: specific synthesis\n"
        "---\n"
        "# Canonical Bridge Note\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_repo_root", lambda: repo)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "c4_graph_rollup_audit.py",
            "--vault",
            str(vault),
            "--scope",
            "full",
            "--batch-size",
            "10",
            "--apply-demotion-plan",
            "--max-demotion-writes",
            "3",
            "--graph-demotion-review-output",
            "state/run_journal/graph_demotion_review_latest.json",
        ],
    )

    exit_code = mod.main()
    assert exit_code == 0

    review_path = repo / "state" / "run_journal" / "graph_demotion_review_latest.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    bridge_files = sorted((repo / "state" / "handoff" / "from_cowork").glob("*_c_handoff.json"))
    assert review_path.exists()
    assert review["reviewed_note_count"] == 1
    assert review["recommended_next_apply_mode"] == "ALLO-only"
    assert review["primary_hotspot_family"] == "ALLOCATION-FAMILY"
    assert bridge_files, "expected canonical bridge drop"
    bridge = json.loads(bridge_files[0].read_text(encoding="utf-8"))
    assert bridge["next_actions"][0] == review["recommended_next_action"]
    assert str(review_path) in bridge["artifacts"]
    assert not (repo / "state" / "handoff" / "from_cowork" / "c_graph_rollup.jsonl").exists()


def test_main_exports_family_summary_csv(scratch_path, monkeypatch):
    mod = _load_graph_rollup_module()
    repo = scratch_path / "repo"
    vault = scratch_path / "vault"
    (repo / "config").mkdir(parents=True)
    (repo / "state" / "openclaw").mkdir(parents=True)
    (repo / "state" / "pids").mkdir(parents=True)
    (repo / "state" / "handoff" / "from_cowork").mkdir(parents=True)
    (vault / "Projects").mkdir(parents=True)
    (vault / "00-Meta").mkdir(parents=True)

    (repo / "config" / "graph_shaper_noise_words.json").write_text(
        json.dumps({"block_words": [], "go_words": []}),
        encoding="utf-8",
    )
    (repo / "config" / "graph_shadow_protected_nodes.json").write_text(
        json.dumps({"protected_entities": [], "protected_families": []}),
        encoding="utf-8",
    )
    (vault / "Projects" / "CSV Export Note.md").write_text(
        "---\n"
        "allocation: specific synthesis\n"
        "---\n"
        "# CSV Export Note\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_repo_root", lambda: repo)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "c4_graph_rollup_audit.py",
            "--vault",
            str(vault),
            "--scope",
            "full",
            "--batch-size",
            "10",
            "--export-family-summary-csv",
            "--family-prefix",
            "ALLO",
            "--only-action",
            "convert to tag",
            "--shadow-review-csv-output",
            "state/run_journal/graph_shadow_review.csv",
        ],
    )

    exit_code = mod.main()
    assert exit_code == 0
    csv_path = repo / "state" / "run_journal" / "graph_shadow_review.csv"
    report_path = repo / "state" / "run_journal" / "graph_shape_audit.json"
    assert csv_path.exists()
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "prefix,family,triage,action,why,candidate_count,protected_example_count,decisions,example_notes,example_values,example_reasons" in csv_text
    assert "ALLO-*" in csv_text
    assert "TO-*" not in csv_text
    assert "LACK-*" not in csv_text
    assert "cheap_metadata" in csv_text
    assert "ignore_route" not in csv_text
    assert "convert to tag" in csv_text
    assert "demote frontmatter" not in csv_text
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["shadow_graph"]["review_csv"].endswith("graph_shadow_review.csv")
