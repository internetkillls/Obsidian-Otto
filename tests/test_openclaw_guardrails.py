from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from otto.openclaw_guardrails import (
    APPROVED_MEMORY_DREAMING_EXPR,
    CANONICAL_CRON_TZ,
    sanitize_generated_dreaming_artifacts,
    sync_openclaw_cron_contract,
)


def test_sync_openclaw_cron_contract_normalizes_live_jobs(tmp_path):
    jobs_path = tmp_path / "jobs.json"
    contract_path = tmp_path / "cron_contract_v1.json"
    jobs_path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "id": "a",
                        "name": "otto_a_signal",
                        "description": "[managed-by=otto.loop] signal",
                        "enabled": True,
                        "schedule": {"kind": "cron", "expr": "0 9 * * *"},
                    },
                    {
                        "id": "b",
                        "name": "Memory Dreaming Promotion",
                        "description": "[managed-by=memory-core.short-term-promotion] dream",
                        "enabled": True,
                        "schedule": {"kind": "cron", "expr": "0 3 * * *"},
                    },
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = sync_openclaw_cron_contract(jobs_path=jobs_path, contract_path=contract_path, apply_fixes=True)

    assert result["ok"] is True
    assert result["sync_performed"] is True
    live_jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    otto_job = live_jobs["jobs"][0]
    dream_job = live_jobs["jobs"][1]
    assert otto_job["schedule"]["tz"] == CANONICAL_CRON_TZ
    assert dream_job["schedule"]["tz"] == CANONICAL_CRON_TZ
    assert dream_job["schedule"]["expr"] == APPROVED_MEMORY_DREAMING_EXPR

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["validation"]["drift_free"] is True
    assert len(contract["jobs"]) == 2


def test_sync_openclaw_cron_contract_flags_drift_without_fix(tmp_path):
    jobs_path = tmp_path / "jobs.json"
    contract_path = tmp_path / "cron_contract_v1.json"
    jobs_path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "id": "b",
                        "name": "Memory Dreaming Promotion",
                        "description": "[managed-by=memory-core.short-term-promotion] dream",
                        "enabled": True,
                        "schedule": {"kind": "cron", "expr": "0 3 * * *"},
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = sync_openclaw_cron_contract(jobs_path=jobs_path, contract_path=contract_path, apply_fixes=False)

    assert result["ok"] is True
    assert result["sync_performed"] is False
    assert any("timezone should be" in issue for issue in result["current_issues"])
    assert any(APPROVED_MEMORY_DREAMING_EXPR in issue for issue in result["current_issues"])


def test_sanitize_generated_dreaming_artifacts_strips_bleed(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    state_root = tmp_path / "state"
    paths = SimpleNamespace(vault_path=vault, state_root=state_root)
    monkeypatch.setattr("otto.openclaw_guardrails.load_paths", lambda: paths)

    rem_dir = vault / "memory" / "dreaming" / "rem"
    light_dir = vault / "memory" / "dreaming" / "light"
    deep_dir = vault / "memory" / "dreaming" / "deep"
    rem_dir.mkdir(parents=True, exist_ok=True)
    light_dir.mkdir(parents=True, exist_ok=True)
    deep_dir.mkdir(parents=True, exist_ok=True)

    (rem_dir / "2026-04-25.md").write_text(
        """# REM Sleep

### Reflections
- Theme: `user` kept surfacing across 985 memories.
  - evidence: memory/.dreams/session-corpus/2026-04-21.txt:1-1
- Theme: `assistant` kept surfacing across 773 memories.
  - evidence: memory/.dreams/session-corpus/2026-04-21.txt:2-2

### Possible Lasting Truths
- No strong candidate truths surfaced.
""",
        encoding="utf-8",
    )
    (light_dir / "2026-04-25.md").write_text(
        """# Light Sleep

- Candidate: User: System (untrusted): Exec completed
  - evidence: memory/.dreams/session-corpus/2026-04-21.txt:10-10
- Candidate: Assistant: HEARTBEAT_OK
  - evidence: memory/.dreams/session-corpus/2026-04-21.txt:11-11
""",
        encoding="utf-8",
    )
    (deep_dir / "2026-04-25.md").write_text("# Deep Sleep\n", encoding="utf-8")
    (vault / "memory" / "2026-04-25.md").write_text(
        """# 2026-04-25
<!-- openclaw:dreaming:rem:start -->
old bleed
<!-- openclaw:dreaming:rem:end -->
""",
        encoding="utf-8",
    )

    result = sanitize_generated_dreaming_artifacts(vault_path=vault)

    assert result["ok"] is True
    assert result["report_change_count"] == 3
    assert result["daily_note_change_count"] == 1

    rem_text = (rem_dir / "2026-04-25.md").read_text(encoding="utf-8")
    light_text = (light_dir / "2026-04-25.md").read_text(encoding="utf-8")
    deep_text = (deep_dir / "2026-04-25.md").read_text(encoding="utf-8")
    daily_text = (vault / "memory" / "2026-04-25.md").read_text(encoding="utf-8")

    assert "type: dream-report" in rem_text
    assert "artifact_lane: memory-dreaming" in rem_text
    assert "memory/.dreams/session-corpus" not in rem_text
    assert "System (untrusted)" not in light_text
    assert "HEARTBEAT_OK" not in light_text
    assert "No candidate memories survived Otto sanitation." in light_text
    assert "Promoted 0 candidate(s) into MEMORY.md." in deep_text
    assert "openclaw:dreaming" not in daily_text
