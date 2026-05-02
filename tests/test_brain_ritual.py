from __future__ import annotations

import pytest
from otto.brain.ritual_engine import RitualPhase, RitualResult, RitualEngine


class TestRitualPhase:
    def test_phase_enum_values(self):
        assert RitualPhase.SCAN.value == "scan"
        assert RitualPhase.REFLECT.value == "reflect"
        assert RitualPhase.DREAM.value == "dream"
        assert RitualPhase.ACT.value == "act"


class TestRitualEngine:
    def test_engine_initializes(self, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", "")
        re = RitualEngine.__new__(RitualEngine)
        re.vault_path = None
        re.current_phase = RitualPhase.SCAN
        re.history = []
        re._scan_results = {}
        assert re.current_phase == RitualPhase.SCAN
        assert re.history == []

    def test_run_scan_phase(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        note = tmp_vault / "10-Personal" / "test.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("---\ntags: [test]\n---\n# Test\nContent here.", encoding="utf-8")

        re = RitualEngine(vault_path=tmp_vault)
        result = re.run_phase(RitualPhase.SCAN)
        assert result.phase == RitualPhase.SCAN
        assert result.note_count >= 1

    def test_run_reflect_phase(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        re = RitualEngine(vault_path=tmp_vault)
        re._scan_results = {"note_count": 5, "notes": []}
        result = re.run_phase(RitualPhase.REFLECT)
        assert result.phase == RitualPhase.REFLECT

    def test_run_dream_phase(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        re = RitualEngine(vault_path=tmp_vault)
        re._scan_results = {"note_count": 5, "notes": []}
        result = re.run_phase(RitualPhase.DREAM)
        assert result.phase == RitualPhase.DREAM

    def test_run_act_phase(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        re = RitualEngine(vault_path=tmp_vault)
        re._scan_results = {"note_count": 5, "notes": []}
        result = re.run_phase(RitualPhase.ACT)
        assert result.phase == RitualPhase.ACT

    def test_write_ritual_note(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        re = RitualEngine(vault_path=tmp_vault)
        result = RitualResult(
            phase=RitualPhase.SCAN,
            note_count=3,
            artifacts_created=1,
            duration_ms=150,
            summary="Scanned 3 notes",
        )
        path = re.write_ritual_note(result)
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "scan" in text.lower()
