from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from otto.app.status import build_status, render_status_summary
from otto.orchestration.dream import run_dream_once
from otto.orchestration.kairos import _write_root_memory_packet, run_kairos_once
from otto.pipeline import run_pipeline
from otto.retrieval.memory import retrieve
from otto.state import now_iso
from otto.tooling.normalize import build_silver


def test_pipeline(scratch_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    sample_vault = repo / "data" / "sample" / "vault"
    monkeypatch.setenv("OTTO_VAULT_PATH", str(sample_vault))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(scratch_path / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(scratch_path / "chroma_store"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(scratch_path / "artifacts"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(scratch_path / "state"))
    monkeypatch.setenv("OTTO_BRONZE_ROOT", str(scratch_path / "bronze"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(scratch_path / "logs"))

    result = run_pipeline()
    assert result["checkpoint"]["bronze_notes"] >= 1
    assert Path(result["checkpoint"]["silver_db"]).exists()
    assert str(scratch_path) in result["checkpoint"]["silver_db"]

    status = build_status()
    assert "top_folders" in status
    assert status["checkpoint"]["training_ready"] in {True, False}
    assert "runtime" in status
    assert "sqlite" in status
    assert "vector" in status
    assert "next_actions" in status
    assert isinstance(status["issues"], list)
    assert status["sqlite"]["exists"] is True
    assert status["sqlite"]["note_count"] >= 1

    retrieval = retrieve("policy", mode="fast")
    assert retrieval["enough_evidence"] is True
    assert len(retrieval["note_hits"]) >= 1

    kairos = run_kairos_once()
    dream = run_dream_once()
    assert "model_hint" in kairos
    assert "model_hint" in dream
    startup_memory = sample_vault / "MEMORY.md"
    assert startup_memory.exists()
    startup_text = startup_memory.read_text(encoding="utf-8")
    assert "Session-Start Memory Packet" in startup_text
    assert "Use this packet as the canonical current-state human memory for the first reply." in startup_text


def test_build_status_prefers_handoff_next_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))
    (tmp_path / "vault").mkdir(parents=True, exist_ok=True)

    artifacts_root = tmp_path / "artifacts"
    state_root = tmp_path / "state"
    artifacts_root.joinpath("summaries").mkdir(parents=True, exist_ok=True)
    state_root.joinpath("handoff").mkdir(parents=True, exist_ok=True)
    state_root.joinpath("run_journal").mkdir(parents=True, exist_ok=True)

    (artifacts_root / "summaries" / "gold_summary.json").write_text(
        json.dumps(
            {
                "next_actions": [
                    "fix frontmatter in the top risky folder",
                    "rerun scoped pipeline for any folder above risk score 10",
                ]
            }
        ),
        encoding="utf-8",
    )
    (state_root / "handoff" / "latest.json").write_text(
        json.dumps(
            {
                "goal": "Advance graph-demotion cleanup via ALLO-only follow-up on ALLOCATION-FAMILY",
                "graph_demotion_review_path": str(state_root / "run_journal" / "graph_demotion_review_latest.json"),
                "next_actions": [
                    "Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for ALLOCATION-FAMILY, then apply the next ALLO-only batch."
                ],
            }
        ),
        encoding="utf-8",
    )
    (state_root / "run_journal" / "graph_demotion_review_latest.json").write_text(
        json.dumps(
            {
                "updated_at": now_iso(),
                "reviewed_note_count": 12,
                "quality_verdict": "ready",
                "graph_readability_verdict": "improved_allocation_signal",
                "recommended_next_apply_mode": "ALLO-only",
                "primary_hotspot_family": "ALLOCATION-FAMILY",
                "recommended_next_action": "Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for ALLOCATION-FAMILY, then apply the next ALLO-only batch.",
            }
        ),
        encoding="utf-8",
    )

    status = build_status()
    assert status["controller"]["source"] == "handoff"
    assert status["goal"] == "Advance graph-demotion cleanup via ALLO-only follow-up on ALLOCATION-FAMILY"
    assert status["next_actions"][0].startswith("Use the reviewed graph-demotion batch")


def test_write_root_memory_packet_moves_archive_out_of_bootstrap(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "MEMORY.md").write_text(
        "# Long-Term Memory\n\n"
        "## Promoted From Short-Term Memory (2026-04-27)\n\n"
        "- # 2026-04-22 - Discussed Web Design Studio (UMKM Package) project as BQ-based pricing.\n",
        encoding="utf-8",
    )

    _write_root_memory_packet(
        SimpleNamespace(vault_path=vault),
        {
            "goal": "Keep support grounded in Josh's current execution state",
            "next_actions": [
                "Reduce ambiguity before adding system complexity",
                "Surface one main next step first",
            ],
            "profile_support_style": [
                "Use recall and synthesis proactively instead of waiting for chat prompts.",
                "Prefer one main action over parallel task floods.",
            ],
            "profile_cognitive_risks": [
                "Commitments can be forgotten unless recalled from history and surfaced proactively.",
            ],
            "profile_recovery_levers": [
                "Short, concrete prompts with one next step reduce friction.",
            ],
            "profile_commitments_to_recall": [
                {
                    "cue": "Website client work",
                    "kind": "client",
                    "horizon": "7d",
                }
            ],
            "profile_opportunities_to_surface": [
                {
                    "cue": "Freelance website delivery",
                    "kind": "client",
                    "horizon": "7d",
                    "historical": False,
                }
            ],
            "mentor_active_probes": [
                {
                    "title": "commitment continuity probe",
                    "weakness": "Commitments can be forgotten unless recalled from history and surfaced proactively.",
                }
            ],
        },
        {"ts": "2026-04-27T19:03:10+07:00"},
    )

    startup_text = (vault / "MEMORY.md").read_text(encoding="utf-8")
    archive_text = (vault / "memory" / "root-memory-archive.md").read_text(encoding="utf-8")

    assert "Session-Start Memory Packet" in startup_text
    assert "Priority Decision Lens" in startup_text
    assert "Likely Near-Term Human Priorities" in startup_text
    assert "Freelance website delivery" in startup_text
    assert "Current Otto Runtime Goal" not in startup_text
    assert "Recent Durable Recalls" in startup_text
    assert "Discussed Web Design Studio" in startup_text
    assert "root-memory-archive.md" in startup_text
    assert "Long-Term Memory" in archive_text
    assert "Discussed Web Design Studio" in archive_text


def test_build_status_recovers_graph_controller_from_fresh_review(tmp_path, monkeypatch):
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))
    (tmp_path / "vault").mkdir(parents=True, exist_ok=True)

    artifacts_root = tmp_path / "artifacts"
    state_root = tmp_path / "state"
    artifacts_root.joinpath("summaries").mkdir(parents=True, exist_ok=True)
    state_root.joinpath("handoff").mkdir(parents=True, exist_ok=True)
    state_root.joinpath("run_journal").mkdir(parents=True, exist_ok=True)

    sqlite_path = tmp_path / "otto_silver.db"
    conn = sqlite3.connect(sqlite_path)
    conn.execute("CREATE TABLE notes (path TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    (artifacts_root / "summaries" / "gold_summary.json").write_text(
        json.dumps({"next_actions": ["fix frontmatter in the top risky folder"]}),
        encoding="utf-8",
    )
    (state_root / "handoff" / "latest.json").write_text(
        json.dumps(
            {
                "goal": "Maintain a stable Obsidian-Otto retrieval core",
                "next_actions": ["fix frontmatter in the top risky folder"],
            }
        ),
        encoding="utf-8",
    )
    (state_root / "run_journal" / "graph_demotion_review_latest.json").write_text(
        json.dumps(
            {
                "updated_at": now_iso(),
                "reviewed_note_count": 12,
                "quality_verdict": "ready",
                "graph_readability_verdict": "improved_allocation_signal",
                "recommended_next_apply_mode": "ALLO-only",
                "primary_hotspot_family": "ALLOCATION-FAMILY",
                "recommended_next_action": "Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for ALLOCATION-FAMILY, then apply the next ALLO-only batch.",
            }
        ),
        encoding="utf-8",
    )

    status = build_status()
    assert status["controller"]["source"] == "graph_review"
    assert status["goal"] == "Advance graph-demotion cleanup via ALLO-only follow-up on ALLOCATION-FAMILY"
    assert status["next_actions"][0].startswith("Use the reviewed graph-demotion batch")


def test_build_status_separates_controller_and_infra_issues(tmp_path, monkeypatch):
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))
    (tmp_path / "vault").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "summaries").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "handoff").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "checkpoints").mkdir(parents=True, exist_ok=True)

    sqlite_path = tmp_path / "otto_silver.db"
    conn = sqlite3.connect(sqlite_path)
    conn.execute("CREATE TABLE notes (path TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    (tmp_path / "artifacts" / "summaries" / "gold_summary.json").write_text(
        json.dumps({"next_actions": ["gold fallback action"]}),
        encoding="utf-8",
    )
    (tmp_path / "state" / "handoff" / "latest.json").write_text(
        json.dumps({"next_actions": ["controller action"]}),
        encoding="utf-8",
    )
    (tmp_path / "state" / "checkpoints" / "pipeline.json").write_text(
        json.dumps({"silver_db": str(tmp_path / "different.db")}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "otto.app.status.build_infra_result",
        lambda: SimpleNamespace(
            to_dict=lambda: {
                "docker_available": True,
                "daemon_running": False,
                "running_services_known": False,
                "configured_services": ["chromadb"],
                "running_services": [],
                "docker_probe_status": "access-denied",
                "docker_probe_error": "Access is denied.",
                "postgres_reachable": True,
                "mcp_reachable": False,
                "next_safe_action": "status",
            }
        ),
    )
    monkeypatch.setattr("otto.app.status.build_openclaw_health", lambda: {"config_drift_free": False, "hf_fallback_ready": True, "capabilities": {}})
    monkeypatch.setattr("otto.app.status.probe_openclaw_gateway", lambda timeout_seconds=1.5: {"ok": False, "reason": "gateway-http-unhealthy"})

    status = build_status()
    assert "openclaw live config has drift relative to repo config" in status["controller_issues"]
    assert "checkpoint silver_db points at a different database than the live sqlite path" in status["controller_issues"]
    assert "Docker probe from Python is denied; chromadb runtime state cannot be verified" in status["infra_issues"]
    assert "OpenClaw gateway HTTP probe is unhealthy" in status["infra_issues"]

    summary = render_status_summary(status)
    assert "Controller Issues" in summary
    assert "Infra Issues" in summary
    assert "Docker probe: access-denied" in summary


def test_render_status_summary_prefers_fresh_gateway_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))
    (tmp_path / "vault").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "summaries").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "handoff").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "checkpoints").mkdir(parents=True, exist_ok=True)

    sqlite_path = tmp_path / "otto_silver.db"
    conn = sqlite3.connect(sqlite_path)
    conn.execute("CREATE TABLE notes (path TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        "otto.app.status.build_infra_result",
        lambda: SimpleNamespace(
            to_dict=lambda: {
                "docker_available": True,
                "daemon_running": True,
                "running_services_known": True,
                "configured_services": [],
                "running_services": [],
                "docker_probe_status": "ok",
                "postgres_reachable": True,
                "mcp_reachable": True,
                "next_safe_action": "status",
            }
        ),
    )
    monkeypatch.setattr("otto.app.status.build_openclaw_health", lambda: {"config_drift_free": True, "hf_fallback_ready": True, "capabilities": {}})
    monkeypatch.setattr(
        "otto.app.status.probe_openclaw_gateway",
        lambda timeout_seconds=1.5: {
            "ok": True,
            "status": "healthy",
            "reason": "gateway-http-healthy",
            "checked_at": "2026-04-25T12:00:00+07:00",
            "last_failure_at": "2026-04-25T11:59:00+07:00",
        },
    )

    summary = render_status_summary(build_status())
    assert "OpenClaw gateway: healthy - gateway-http-healthy" in summary
    assert "OpenClaw last failed probe: 2026-04-25T11:59:00+07:00" in summary


def test_run_pipeline_preserves_fresh_graph_controller_handoff(tmp_path, monkeypatch):
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto_silver.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_BRONZE_ROOT", str(tmp_path / "bronze"))
    monkeypatch.setenv("OTTO_LOGS_ROOT", str(tmp_path / "logs"))
    (tmp_path / "vault").mkdir(parents=True, exist_ok=True)

    state_root = tmp_path / "state"
    state_root.joinpath("handoff").mkdir(parents=True, exist_ok=True)
    state_root.joinpath("run_journal").mkdir(parents=True, exist_ok=True)
    graph_review_path = state_root / "run_journal" / "graph_demotion_review_latest.json"
    graph_review_path.write_text(
        json.dumps(
            {
                "updated_at": now_iso(),
                "reviewed_note_count": 12,
                "quality_verdict": "ready",
                "graph_readability_verdict": "improved_allocation_signal",
                "recommended_next_apply_mode": "ALLO-only",
                "primary_hotspot_family": "ALLOCATION-FAMILY",
                "recommended_next_action": "Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for ALLOCATION-FAMILY, then apply the next ALLO-only batch.",
            }
        ),
        encoding="utf-8",
    )
    (state_root / "handoff" / "latest.json").write_text(
        json.dumps(
            {
                "goal": "Advance graph-demotion cleanup via ALLO-only follow-up on ALLOCATION-FAMILY",
                "graph_demotion_review_path": str(graph_review_path),
                "graph_demotion_next_apply_mode": "ALLO-only",
                "graph_demotion_hotspot_family": "ALLOCATION-FAMILY",
                "graph_demotion_next_action": "Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for ALLOCATION-FAMILY, then apply the next ALLO-only batch.",
                "next_actions": [
                    "Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for ALLOCATION-FAMILY, then apply the next ALLO-only batch.",
                    "Escalate to urgent review before the next heartbeat cycle",
                ],
                "artifacts": ["existing-graph-artifact.json"],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "otto.pipeline.scan_vault",
        lambda scope=None: {"note_count": 5, "attachments": [], "notes": []},
    )
    monkeypatch.setattr(
        "otto.pipeline.build_silver",
        lambda bronze: {"db_path": str(tmp_path / "otto_silver.db"), "note_count": 5},
    )
    monkeypatch.setattr(
        "otto.pipeline.build_gold",
        lambda: {
            "top_folders": [{"folder": "00-Meta\\scarcity"}],
            "training_readiness": {"ready": True},
            "next_actions": ["fix frontmatter in the top risky folder"],
        },
    )

    run_pipeline()
    handoff = json.loads((state_root / "handoff" / "latest.json").read_text(encoding="utf-8"))

    assert handoff["goal"] == "Advance graph-demotion cleanup via ALLO-only follow-up on ALLOCATION-FAMILY"
    assert handoff["graph_demotion_review_path"] == str(graph_review_path)
    assert handoff["next_actions"][0].startswith("Use the reviewed graph-demotion batch")
    assert "Escalate to urgent review before the next heartbeat cycle" in handoff["next_actions"]
    assert "fix frontmatter in the top risky folder" in handoff["next_actions"]
    assert "existing-graph-artifact.json" in handoff["artifacts"]


def test_promised_files_exist():
    repo = Path(__file__).resolve().parents[1]
    required = [
        repo / "initial.bat",
        repo / "tui.bat",
        repo / "status.bat",
        repo / "sanity-check.bat",
        repo / "AGENTS.md",
        repo / ".codex" / "config.toml",
        repo / ".agents" / "skills" / "memory-fast" / "SKILL.md",
        repo / "docs" / "openclud-injection-map.md",
    ]
    for path in required:
        assert path.exists(), f"missing: {path}"


def test_build_silver_rebuilds_legacy_sqlite(scratch_path, monkeypatch):
    sqlite_path = scratch_path / "legacy_otto.db"
    conn = sqlite3.connect(sqlite_path)
    conn.execute(
        """
        CREATE TABLE notes (
            path TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            sha1 TEXT NOT NULL,
            mtime REAL NOT NULL,
            has_frontmatter INTEGER NOT NULL,
            frontmatter_text TEXT,
            body_excerpt TEXT,
            tags_json TEXT,
            wikilinks_json TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("OTTO_SQLITE_PATH", str(sqlite_path))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(scratch_path / "artifacts"))
    bronze_payload = {
        "notes": [
            {
                "path": "Projects/Policy Study.md",
                "title": "Policy Study",
                "size": 12,
                "sha1": "abc123",
                "mtime": 1.0,
                "has_frontmatter": True,
                "frontmatter_text": "type: project",
                "body_excerpt": "Policy research and study notes.",
                "tags": ["policy"],
                "wikilinks": ["[[Inbox/Daily Note]]"],
                "scarcity": [],
                "necessity": None,
                "artificial": None,
                "orientation": None,
                "allocation": None,
                "cluster_membership": [],
                "aliases": ["policy memo"],
            }
        ],
        "attachments": [],
    }

    summary = build_silver(bronze_payload)
    assert summary["note_count"] == 1

    conn = sqlite3.connect(sqlite_path)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(notes)").fetchall()]
    aliases_json = conn.execute("SELECT aliases_json FROM notes WHERE path = ?", ("Projects/Policy Study.md",)).fetchone()[0]
    conn.close()
    assert "size" in columns
    assert "aliases_json" in columns
    assert aliases_json == json.dumps(["policy memo"], ensure_ascii=False)
