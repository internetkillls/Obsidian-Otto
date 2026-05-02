from __future__ import annotations

import json
from types import SimpleNamespace

from otto.orchestration.cron_control import build_cron_status, clear_essay_control, steer_essay_control


def _state_paths(tmp_path):
    return SimpleNamespace(state_root=tmp_path / "state")


def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr("otto.orchestration.cron_control.load_paths", lambda: _state_paths(tmp_path))


def test_cron_steer_writes_paper_topics_focus(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    result = steer_essay_control(
        mode="paper_topics",
        topic="open access journals",
        days=2,
        reason="focus test",
        source="chat",
    )

    control = result["essay_control"]
    control_path = tmp_path / "state" / "handoff" / "essay_control.json"

    assert result["ok"] is True
    assert control["mode"] == "paper_topics"
    assert control["focus_topic"] == "open access journals"
    assert control["focus_scope"] == "paper topics"
    assert control["paper_now_force"] is False
    assert control["focus_until"]
    assert control_path.exists()


def test_cron_clear_resets_focus(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    steer_essay_control(mode="paper_topics", topic="open access journals", days=2, reason="focus test", source="chat")
    result = clear_essay_control(reason="reset test", source="chat")

    control = result["essay_control"]
    assert result["ok"] is True
    assert result["mode"] == "normal"
    assert control["mode"] == "normal"
    assert control["focus_topic"] == ""
    assert control["paper_now_force"] is False


def test_build_cron_status_reports_jobs_and_focus(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    jobs_path = tmp_path / ".openclaw" / "cron" / "jobs.json"
    contract_path = tmp_path / "state" / "openclaw" / "cron_contract_v1.json"
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    jobs_path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "name": "otto_daily_essay_lab",
                        "enabled": True,
                        "description": "[managed-by=otto.essay] hourly essay lab",
                        "schedule": {"kind": "cron", "expr": "0 * * * *", "tz": "Asia/Bangkok"},
                        "payload": {"kind": "systemEvent"},
                    },
                    {
                        "name": "external_job",
                        "enabled": False,
                        "description": "not managed",
                        "schedule": {"kind": "cron", "expr": "*/5 * * * *", "tz": "UTC"},
                        "payload": {"kind": "systemEvent"},
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    contract_path.write_text(
        json.dumps({"validation": {"drift_free": True, "current_issues": []}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr("otto.orchestration.cron_control.live_openclaw_jobs_path", lambda: jobs_path)
    monkeypatch.setattr("otto.orchestration.cron_control.openclaw_cron_contract_path", lambda: contract_path)

    steer_essay_control(mode="paper_topics", topic="open access journals", days=2, reason="focus test", source="chat")
    status = build_cron_status()

    assert status["job_count"] == 2
    assert status["enabled_job_count"] == 1
    assert status["managed_job_count"] == 1
    assert status["focus_active"] is True
    assert status["steering"]["mode"] == "paper_topics"
    assert status["steering"]["topic"] == "open access journals"
    assert status["contract_drift_free"] is True
