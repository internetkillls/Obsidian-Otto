from __future__ import annotations

import json

from otto.orchestration.mentor import MentoringEngine


def _configure_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setenv("OTTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OTTO_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("OTTO_SQLITE_PATH", str(tmp_path / "otto.db"))
    monkeypatch.setenv("OTTO_CHROMA_PATH", str(tmp_path / "chroma"))


def test_mentor_creates_probe_before_task(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    engine = MentoringEngine()

    result = engine.run(
        profile={
            "profile_cognitive_risks": [
                "Commitments can be forgotten unless recalled from history and surfaced proactively."
            ]
        }
    )

    assert result.active_probes
    assert not result.pending_tasks
    probe_path = tmp_path / "vault" / ".Otto-Realm" / "Training" / "probes"
    assert list(probe_path.glob("*.md"))


def test_mentor_classifies_answered_probe_and_creates_task(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    engine = MentoringEngine()
    probe_dir = tmp_path / "vault" / ".Otto-Realm" / "Training" / "probes"
    probe_dir.mkdir(parents=True, exist_ok=True)
    probe_dir.joinpath("2026-04-25-context-switching-probe.md").write_text(
        "\n".join(
            [
                "---",
                "probe_id: probe-context-switching-2026-04-25",
                "weakness_key: context-switching",
                "weakness: Context switching stays expensive; continuity must be carried by the system.",
                "title: re-entry probe",
                "status: answered",
                "created_at: 2026-04-25T00:00:00+07:00",
                "answered_at: 2026-04-25T00:30:00+07:00",
                "gap_type: unknown",
                "---",
                "# Probe: re-entry probe",
                "",
                "## Explain In Your Own Words",
                "A re-entry anchor is the one line that lets me resume work without rebuilding context from scratch.",
                "",
                "## Application / Example",
                "",
                "## Stuck Point / Uncertainty",
                "I still do not know which anchor format is best.",
            ]
        ),
        encoding="utf-8",
    )

    result = engine.run(
        profile={
            "profile_cognitive_risks": [
                "Context switching stays expensive; continuity must be carried by the system."
            ]
        }
    )

    assert not result.active_probes
    assert result.pending_tasks
    assert result.pending_tasks[0].gap_type == "application_gap"
    assert result.weakness_registry["context-switching"]["latest_gap_type"] == "application_gap"


def test_mentor_resolved_task_is_not_reissued_from_same_probe(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    engine = MentoringEngine()
    training_root = tmp_path / "vault" / ".Otto-Realm" / "Training"
    probe_dir = training_root / "probes"
    done_dir = training_root / "done"
    probe_dir.mkdir(parents=True, exist_ok=True)
    done_dir.mkdir(parents=True, exist_ok=True)

    probe_dir.joinpath("2026-04-25-context-switching-probe.md").write_text(
        "\n".join(
            [
                "---",
                "probe_id: probe-context-switching-2026-04-25",
                "weakness_key: context-switching",
                "weakness: Context switching stays expensive; continuity must be carried by the system.",
                "title: re-entry probe",
                "status: answered",
                "created_at: 2026-04-25T00:00:00+07:00",
                "answered_at: 2026-04-25T00:30:00+07:00",
                "gap_type: application_gap",
                "---",
                "# Probe: re-entry probe",
                "",
                "## Explain In Your Own Words",
                "A re-entry anchor is the one line that lets me resume work without rebuilding context from scratch.",
                "",
                "## Application / Example",
                "",
                "## Stuck Point / Uncertainty",
                "I still do not know which anchor format is best.",
            ]
        ),
        encoding="utf-8",
    )
    done_dir.joinpath("2026-04-25-context-switching-task.md").write_text(
        "\n".join(
            [
                "---",
                "task_id: mentor-probe-context-switching-2026-04-25-re-entry-anchor-drill",
                "weakness_key: context-switching",
                "weakness: Context switching stays expensive; continuity must be carried by the system.",
                "title: re-entry anchor drill",
                "status: done",
                "created_at: 2026-04-25T01:00:00+07:00",
                "resolved_at: 2026-04-25T02:00:00+07:00",
                "gap_type: application_gap",
                "probe_id: probe-context-switching-2026-04-25",
                "completion_signal: Move this note after review.",
                "---",
                "# Training Task: re-entry anchor drill",
            ]
        ),
        encoding="utf-8",
    )

    result = engine.run(
        profile={
            "profile_cognitive_risks": [
                "Context switching stays expensive; continuity must be carried by the system."
            ]
        }
    )

    assert not any(item.probe_id == "probe-context-switching-2026-04-25" for item in result.pending_tasks)
    assert result.active_probes
    assert result.active_probes[0].probe_id != "probe-context-switching-2026-04-25"


def test_mentor_state_snapshot_exposes_registry(monkeypatch, tmp_path):
    _configure_env(monkeypatch, tmp_path)
    engine = MentoringEngine()
    engine.run(
        profile={
            "profile_cognitive_risks": [
                "Long-running loops need visible stop conditions and externalized next actions."
            ]
        }
    )

    snapshot = json.loads((tmp_path / "state" / "kairos" / "mentor_latest.json").read_text(encoding="utf-8"))

    assert "active_probes" in snapshot
    assert "weakness_registry" in snapshot
    assert snapshot["feedback_loop_ready"] is True
