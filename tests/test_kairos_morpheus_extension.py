from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from otto.events import EVENT_KAIROS_GOLD_SCORED
from otto.orchestration.council import CouncilEngine
from otto.orchestration.dream import run_dream_once
from otto.orchestration.kairos import run_kairos_once
from otto.orchestration.kairos_gold import KairosGoldEngine, KairosGoldResult
from otto.orchestration.meta_gov import MetaGovObserver
from otto.orchestration.morpheus import MorpheusEngine
from otto.pipeline import run_pipeline
from otto.state import now_iso, write_json


def _seed_sqlite_for_meta(path: Path, *, old_days: int = 20) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE notes (
            path TEXT PRIMARY KEY,
            mtime REAL NOT NULL
        );
        """
    )
    ts = (datetime.now(timezone.utc) - timedelta(days=old_days)).timestamp()
    conn.execute("INSERT INTO notes(path, mtime) VALUES (?, ?)", ("Projects/Old.md", ts))
    conn.commit()
    conn.close()


def test_build_claim_uses_full_note_context(monkeypatch, tmp_path):
    vault = tmp_path / "vault"
    note_path = vault / "Projects" / "Long.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    long_body = ("alpha " * 600) + "\nUNIQUE_TAIL_MARKER\n"
    note_path.write_text(long_body, encoding="utf-8")

    monkeypatch.setenv("OTTO_VAULT_PATH", str(vault))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))

    engine = KairosGoldEngine()
    claim = engine.build_claim_for_signal(
        {
            "path": "Projects/Long.md",
            "title": "Long",
            "frontmatter_text": "",
            "tags_json": "[]",
            "wikilinks_json": "[]",
            "body_excerpt": "short excerpt",
        }
    )
    assert "UNIQUE_TAIL_MARKER" in claim
    assert "short excerpt" not in claim


def test_council_recurrence_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))

    result = KairosGoldResult(
        ts=now_iso(),
        kairos_score=5.5,
        gold_promoted_count=0,
        silver_count=2,
        noise_count=6,
        scored_signals=[],
        contradictions=[],
        dynamic_thresholds={},
        promoted_paths=[],
    )
    unresolved = [f"task-{i}" for i in range(6)]

    engine = CouncilEngine()
    run1 = engine.run(gold_result=result, unresolved=unresolved)
    run2 = engine.run(gold_result=result, unresolved=unresolved)
    run3 = engine.run(gold_result=result, unresolved=unresolved)

    assert run1.triggered is False
    assert run2.triggered is False
    assert run3.triggered is True
    assert any(item.trigger_category == "cognitive_weakness" for item in run3.debates)


def test_council_prefers_ranked_graph_action_candidate(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))

    result = KairosGoldResult(
        ts=now_iso(),
        kairos_score=5.5,
        gold_promoted_count=0,
        silver_count=2,
        noise_count=6,
        scored_signals=[],
        contradictions=[],
        dynamic_thresholds={},
        promoted_paths=[],
    )
    unresolved = [f"task-{i}" for i in range(6)]
    action_candidates = [
        {
            "action": "Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for ALLOCATION-FAMILY, then apply the next ALLO-only batch.",
            "priority": 100,
            "source": "graph_demotion_review",
            "reason": "ALLO-only via ALLOCATION-FAMILY (improved_allocation_signal)",
            "context": {
                "recommended_next_apply_mode": "ALLO-only",
                "primary_hotspot_family": "ALLOCATION-FAMILY",
            },
        }
    ]

    engine = CouncilEngine()
    engine.run(gold_result=result, unresolved=unresolved, action_candidates=action_candidates)
    engine.run(gold_result=result, unresolved=unresolved, action_candidates=action_candidates)
    run3 = engine.run(gold_result=result, unresolved=unresolved, action_candidates=action_candidates)

    assert run3.triggered is True
    assert run3.debates[0].next_action == action_candidates[0]["action"]
    assert run3.debates[0].action_source == "graph_demotion_review"
    assert "ALLO-only" in run3.debates[0].synthesis


def test_meta_gov_economic_and_consistency(monkeypatch, tmp_path):
    state_root = tmp_path / "state"
    artifacts_root = tmp_path / "artifacts"
    vault = tmp_path / "vault"
    heartbeat_dir = vault / ".Otto-Realm" / "Heartbeats"
    heartbeat_dir.mkdir(parents=True, exist_ok=True)
    heartbeat_dir.joinpath("2026-04-21.md").write_text("ok", encoding="utf-8")

    sqlite_path = tmp_path / "otto.db"
    _seed_sqlite_for_meta(sqlite_path, old_days=21)

    monkeypatch.setenv("OTTO_STATE_ROOT", str(state_root))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(artifacts_root))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(vault))

    write_json(
        artifacts_root / "summaries" / "gold_summary.json",
        {"top_folders": [{"folder": "Projects", "risk_score": 4.2}]},
    )
    contradiction_ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    (state_root / "run_journal").mkdir(parents=True, exist_ok=True)
    with (state_root / "run_journal" / "contradiction_signals.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": contradiction_ts,
                    "note_path": "Projects/Old.md",
                    "primary_claim": "revenue collapse risk",
                    "resolved": False,
                }
            )
            + "\n"
        )
    with (state_root / "run_journal" / "events.jsonl").open("w", encoding="utf-8") as fh:
        for _ in range(2):
            fh.write(
                json.dumps(
                    {
                        "type": EVENT_KAIROS_GOLD_SCORED,
                        "ts": now_iso(),
                        "payload": {"gold_promoted_count": 1},
                    }
                )
                + "\n"
            )

    findings = MetaGovObserver().observe()
    flags = {item.flag for item in findings}
    assert "economic_threat_stale" in flags
    assert "gold_vault_inconsistency" in flags
    assert "gold_low" not in flags


def test_morpheus_change_vectors_and_mode(monkeypatch, tmp_path):
    state_root = tmp_path / "state"
    monkeypatch.setenv("OTTO_STATE_ROOT", str(state_root))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))

    (state_root / "run_journal").mkdir(parents=True, exist_ok=True)
    events = [
        {
            "type": "kairos.heartbeat",
            "ts": now_iso(),
            "payload": {"next_actions": ["Repair metadata in Projects", "Close inbox loop"]},
        },
        {
            "type": EVENT_KAIROS_GOLD_SCORED,
            "ts": now_iso(),
            "payload": {"gold_promoted_count": 2, "promoted_paths": ["Projects/A.md"]},
        },
        {
            "type": "council.debate",
            "ts": now_iso(),
            "payload": {"trigger_category": "cognitive_weakness"},
        },
    ]
    with (state_root / "run_journal" / "events.jsonl").open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")

    enrichment = MorpheusEngine().enrich(
        stable_facts=["Training ready: True"],
        unresolved=["Repair metadata in Projects", "Resolve revenue runway"],
        vault_materials=[],
        telemetry=None,
    )
    assert enrichment.new_pressures
    assert enrichment.resolved_this_cycle
    assert enrichment.embodiment_mode == "protection"
    assert enrichment.suffering_surface


def test_morpheus_surfaces_graph_demotion_continuity(monkeypatch, tmp_path):
    state_root = tmp_path / "state"
    monkeypatch.setenv("OTTO_STATE_ROOT", str(state_root))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))

    write_json(
        state_root / "run_journal" / "graph_demotion_review_latest.json",
        {
            "updated_at": now_iso(),
            "reviewed_note_count": 12,
            "quality_verdict": "ready",
            "graph_readability_verdict": "improved_allocation_signal",
            "recommended_next_apply_mode": "ALLO-only",
            "primary_hotspot_family": "ALLOCATION-FAMILY",
            "recommended_next_action": "Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for ALLOCATION-FAMILY, then apply the next ALLO-only batch.",
        },
    )

    enrichment = MorpheusEngine().enrich(
        stable_facts=["Training ready: True"],
        unresolved=["Repair metadata in Projects"],
        vault_materials=[],
        telemetry=None,
    )
    assert any("Graph demotion track" in item for item in enrichment.continuity_threads)
    assert any("ALLOCATION-FAMILY" in item for item in enrichment.expressive_outlets)


def test_kairos_prefers_graph_review_and_executes_openclaw(monkeypatch, tmp_path):
    state_root = tmp_path / "state"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("OTTO_STATE_ROOT", str(state_root))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(artifacts_root))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))

    write_json(
        artifacts_root / "summaries" / "gold_summary.json",
        {"top_folders": [{"folder": "Projects", "risk_score": 42.0, "missing_frontmatter": 1, "duplicate_titles": 2}]},
    )
    write_json(
        state_root / "run_journal" / "graph_demotion_review_latest.json",
        {
            "updated_at": now_iso(),
            "reviewed_note_count": 12,
            "quality_verdict": "ready",
            "graph_readability_verdict": "improved_allocation_signal",
            "recommended_next_apply_mode": "ALLO-only",
            "primary_hotspot_family": "ALLOCATION-FAMILY",
            "recommended_next_action": "Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for ALLOCATION-FAMILY, then apply the next ALLO-only batch.",
            "ready_for_openclaw_fetch": True,
            "openclaw_topic": "ALLO-only graph demotion follow-up for ALLOCATION-FAMILY after reviewed 12-note bounded apply",
        },
    )

    monkeypatch.setattr(
        "otto.orchestration.kairos.KairosGoldEngine.score_signals",
        lambda self: KairosGoldResult(
            ts=now_iso(),
            kairos_score=4.2,
            gold_promoted_count=0,
            silver_count=0,
            noise_count=3,
            scored_signals=[],
            contradictions=[],
            dynamic_thresholds={},
            promoted_paths=[],
        ),
    )
    monkeypatch.setattr("otto.orchestration.kairos.run_brain_predictions", lambda: None)
    monkeypatch.setattr("otto.orchestration.kairos.MetaGovObserver.observe", lambda self: [])

    def _fake_execute(self, *, topic_text: str, priority: str = "medium"):
        return SimpleNamespace(
            ts=now_iso(),
            approved=True,
            budget_reason="review-backed fetch",
            fetch_cycles=1,
            topic=SimpleNamespace(
                topic=topic_text,
                topic_class="systems",
                priority=priority,
                source_tiers=["expert blogs"],
                needs_freshness_check=False,
                effect_size_required=False,
            ),
            hypothesis=f"Research should clarify the highest-leverage decision behind: {topic_text}",
            search_query=f"query:{topic_text}",
            search_provider="duckduckgo-html",
            fetch_provider="python-requests",
            search_ok=True,
            fetch_ok=True,
            search_hits=[{"title": "hit"}],
            fetched_documents=[{"url": "https://example.com"}],
            warnings=[],
            cache_path=str(state_root / "openclaw" / "research" / "latest.json"),
        )

    monkeypatch.setattr("otto.orchestration.kairos.OpenClawResearchEngine.execute", _fake_execute)

    result = run_kairos_once()
    handoff = json.loads((state_root / "handoff" / "latest.json").read_text(encoding="utf-8"))
    strategy = (artifacts_root / "reports" / "kairos_daily_strategy.md").read_text(encoding="utf-8")

    assert result["graph_demotion_next_action"] == handoff["graph_demotion_next_action"]
    assert result["graph_demotion_next_apply_mode"] == "ALLO-only"
    assert result["openclaw_fetch"] is True
    assert handoff["next_actions"][0].startswith("Use the reviewed graph-demotion batch")
    assert "graph-demotion cleanup" in handoff["goal"]
    assert "## Graph Demotion" in strategy
    assert "ALLOCATION-FAMILY" in strategy


def test_kairos_falls_back_without_graph_review(monkeypatch, tmp_path):
    state_root = tmp_path / "state"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("OTTO_STATE_ROOT", str(state_root))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(artifacts_root))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))

    write_json(
        artifacts_root / "summaries" / "gold_summary.json",
        {"top_folders": [{"folder": "Projects", "risk_score": 42.0, "missing_frontmatter": 1, "duplicate_titles": 2}]},
    )
    monkeypatch.setattr(
        "otto.orchestration.kairos.KairosGoldEngine.score_signals",
        lambda self: KairosGoldResult(
            ts=now_iso(),
            kairos_score=6.5,
            gold_promoted_count=1,
            silver_count=1,
            noise_count=0,
            scored_signals=[],
            contradictions=[],
            dynamic_thresholds={},
            promoted_paths=[],
        ),
    )
    monkeypatch.setattr("otto.orchestration.kairos.run_brain_predictions", lambda: None)
    monkeypatch.setattr("otto.orchestration.kairos.MetaGovObserver.observe", lambda self: [])
    monkeypatch.setattr(
        "otto.orchestration.kairos.build_research_plan",
        lambda *, topic_text, priority="medium": {
            "ts": now_iso(),
            "topic": topic_text,
            "topic_class": "systems",
            "priority": priority,
            "approved": True,
            "budget_reason": "fallback",
            "planned_cycles": 1,
            "source_tiers": [],
            "needs_freshness_check": False,
            "effect_size_required": False,
            "search_query": topic_text,
            "hypothesis": topic_text,
            "plan_only": True,
            "fetch_executed": False,
        },
    )
    monkeypatch.setattr(
        "otto.orchestration.kairos.OpenClawResearchEngine.execute",
        lambda self, *, topic_text, priority="medium": (_ for _ in ()).throw(AssertionError("execute should not run")),
    )

    result = run_kairos_once()
    handoff = json.loads((state_root / "handoff" / "latest.json").read_text(encoding="utf-8"))

    assert result["graph_demotion_next_action"] is None
    assert handoff["next_actions"][0] == "Repair metadata in Projects"
    assert handoff["graph_demotion_review_path"] is None


def test_kairos_and_dream_integration(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    sample_vault = repo / "data" / "sample" / "vault"
    monkeypatch.setenv("OTTO_VAULT_PATH", str(sample_vault))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))

    run_pipeline()
    kairos = run_kairos_once()
    dream = run_dream_once()

    assert "cycle_id" in kairos
    assert "kairos_score" in kairos
    assert "gold_promoted_count" in kairos
    assert "morpheus_layer" in dream

    events_path = tmp_path / "state" / "run_journal" / "events.jsonl"
    assert events_path.exists()
    events_text = events_path.read_text(encoding="utf-8")
    assert "kairos.gold.scored" in events_text
    assert "openclaw.research.executed" in events_text
    assert (tmp_path / "state" / "dream" / "morpheus_latest.json").exists()
    assert (tmp_path / "state" / "openclaw" / "morpheus_openclaw_bridge_latest.json").exists()
    assert (tmp_path / "artifacts" / "reports" / "morpheus_openclaw_bridge.md").exists()


def test_kairos_builds_closed_loop_training_queue(monkeypatch, tmp_path):
    state_root = tmp_path / "state"
    artifacts_root = tmp_path / "artifacts"
    vault = tmp_path / "vault"
    monkeypatch.setenv("OTTO_STATE_ROOT", str(state_root))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(artifacts_root))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(vault))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))

    write_json(
        artifacts_root / "summaries" / "gold_summary.json",
        {"top_folders": [{"folder": "Projects", "risk_score": 42.0, "missing_frontmatter": 1, "duplicate_titles": 2}]},
    )
    write_json(
        state_root / "handoff" / "latest.json",
        {
            "profile_cognitive_risks": [
                "Commitments can be forgotten unless recalled from history and surfaced proactively."
            ]
        },
    )
    monkeypatch.setattr(
        "otto.orchestration.kairos.KairosGoldEngine.score_signals",
        lambda self: KairosGoldResult(
            ts=now_iso(),
            kairos_score=6.2,
            gold_promoted_count=0,
            silver_count=0,
            noise_count=1,
            scored_signals=[],
            contradictions=[],
            dynamic_thresholds={},
            promoted_paths=[],
        ),
    )
    monkeypatch.setattr("otto.orchestration.kairos.run_brain_predictions", lambda: None)
    monkeypatch.setattr("otto.orchestration.kairos.MetaGovObserver.observe", lambda self: [])
    monkeypatch.setattr(
        "otto.orchestration.kairos.build_research_plan",
        lambda *, topic_text, priority="medium": {
            "ts": now_iso(),
            "topic": topic_text,
            "topic_class": "systems",
            "priority": priority,
            "approved": True,
            "budget_reason": "fallback",
            "planned_cycles": 1,
            "source_tiers": [],
            "needs_freshness_check": False,
            "effect_size_required": False,
            "search_query": topic_text,
            "hypothesis": topic_text,
            "plan_only": True,
            "fetch_executed": False,
        },
    )

    result = run_kairos_once()
    handoff = json.loads((state_root / "handoff" / "latest.json").read_text(encoding="utf-8"))
    mentor_state = json.loads((state_root / "kairos" / "mentor_latest.json").read_text(encoding="utf-8"))
    probes_dir = vault / ".Otto-Realm" / "Training" / "probes"

    assert result["cycle_id"]
    assert mentor_state["feedback_loop_ready"] is True
    assert handoff["mentor_feedback_loop_ready"] is True
    assert handoff["mentor_active_probes"]
    assert handoff["mentor_weakness_registry"]
    assert probes_dir.exists()
    assert list(probes_dir.glob("*.md"))


def test_kairos_ingests_done_training_and_does_not_reissue_same_task(monkeypatch, tmp_path):
    state_root = tmp_path / "state"
    artifacts_root = tmp_path / "artifacts"
    vault = tmp_path / "vault"
    done_dir = vault / ".Otto-Realm" / "Training" / "done"
    done_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OTTO_STATE_ROOT", str(state_root))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(artifacts_root))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_VAULT_PATH", str(vault))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))

    write_json(
        artifacts_root / "summaries" / "gold_summary.json",
        {"top_folders": [{"folder": "Projects", "risk_score": 42.0, "missing_frontmatter": 1, "duplicate_titles": 2}]},
    )
    write_json(
        state_root / "handoff" / "latest.json",
        {
            "profile_cognitive_risks": [
                "Commitments can be forgotten unless recalled from history and surfaced proactively."
            ]
        },
    )
    done_dir.joinpath("2026-04-25-continuity-recall-drill.md").write_text(
        "\n".join(
            [
                "---",
                "task_id: mentor-continuity-recall-drill",
                "title: continuity recall drill",
                "weakness: Commitments can be forgotten unless recalled from history and surfaced proactively.",
                "status: done",
                "created_at: 2026-04-25T00:00:00+07:00",
                "resolved_at: 2026-04-25T01:00:00+07:00",
                "completion_signal: Move this note after review.",
                "---",
                "# Training Task: continuity recall drill",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "otto.orchestration.kairos.KairosGoldEngine.score_signals",
        lambda self: KairosGoldResult(
            ts=now_iso(),
            kairos_score=6.2,
            gold_promoted_count=0,
            silver_count=0,
            noise_count=1,
            scored_signals=[],
            contradictions=[],
            dynamic_thresholds={},
            promoted_paths=[],
        ),
    )
    monkeypatch.setattr("otto.orchestration.kairos.run_brain_predictions", lambda: None)
    monkeypatch.setattr("otto.orchestration.kairos.MetaGovObserver.observe", lambda self: [])
    monkeypatch.setattr(
        "otto.orchestration.kairos.build_research_plan",
        lambda *, topic_text, priority="medium": {
            "ts": now_iso(),
            "topic": topic_text,
            "topic_class": "systems",
            "priority": priority,
            "approved": True,
            "budget_reason": "fallback",
            "planned_cycles": 1,
            "source_tiers": [],
            "needs_freshness_check": False,
            "effect_size_required": False,
            "search_query": topic_text,
            "hypothesis": topic_text,
            "plan_only": True,
            "fetch_executed": False,
        },
    )

    run_kairos_once()
    handoff = json.loads((state_root / "handoff" / "latest.json").read_text(encoding="utf-8"))
    mentor_state = json.loads((state_root / "kairos" / "mentor_latest.json").read_text(encoding="utf-8"))
    pending_dir = vault / ".Otto-Realm" / "Training" / "pending"
    probes_dir = vault / ".Otto-Realm" / "Training" / "probes"

    assert handoff["mentor_completed_count"] == 1
    assert mentor_state["completed_tasks"][0]["task_id"] == "mentor-continuity-recall-drill"
    assert not any(item["task_id"] == "mentor-continuity-recall-drill" for item in mentor_state["pending_tasks"])
    assert not list(pending_dir.glob("*continuity-recall-drill*.md"))
    assert mentor_state["active_probes"]
    assert list(probes_dir.glob("*.md"))
