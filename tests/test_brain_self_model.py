from __future__ import annotations

import pytest
from pathlib import Path

from otto.brain.self_model import OttoSelfModel, SirAgathonProfile


class TestSirAgathonProfile:
    def test_profile_default_values(self):
        p = SirAgathonProfile()
        assert p.preferred_response_length is None
        assert p.working_hours == {}
        assert p.vault_strengths == []
        assert p.vault_weaknesses == []
        assert p.observed_patterns == []

    def test_profile_can_add_pattern(self):
        p = SirAgathonProfile()
        p.add_pattern("terse_responses", "Sir Agathon prefers short sentences", confidence=0.9)
        assert len(p.observed_patterns) == 1
        assert p.observed_patterns[0]["pattern"] == "terse_responses"
        assert p.observed_patterns[0]["confidence"] == 0.9

    def test_profile_to_markdown(self):
        p = SirAgathonProfile()
        p.preferred_response_length = "terse"
        p.working_hours = {"start": "09:00", "end": "17:00"}
        p.add_pattern("short_sentences", "Sir Agathon uses short sentences", confidence=0.9)
        md = p.profile_to_markdown()
        assert "# Otto Self-Model" in md
        assert "short_sentences" in md


class TestOttoSelfModel:
    def test_self_model_initializes_with_profile(self, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", "")
        sm = OttoSelfModel.__new__(OttoSelfModel)
        sm.vault_path = None
        sm.profile = SirAgathonProfile()
        assert sm.profile is not None
        assert isinstance(sm.profile, SirAgathonProfile)

    def test_build_from_vault_scan_results(self):
        sm = OttoSelfModel.__new__(OttoSelfModel)
        sm.profile = SirAgathonProfile()
        sm.vault_path = None
        mock_scan = {
            "note_count": 5,
            "notes": [
                {"path": "10-Personal/goal.md", "tags": ["goal"], "wikilinks": ["30-Projects/app"], "body_excerpt": ""},
                {"path": "10-Personal/habit.md", "tags": ["habit"], "wikilinks": [], "body_excerpt": ""},
            ]
        }
        result = sm.build_from_scan(mock_scan)
        assert "profile_snapshot" in result
        assert "strengths" in result
        assert "weaknesses" in result

    def test_write_profile_to_vault(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        sm = OttoSelfModel(vault_path=tmp_vault)
        sm.profile.preferred_response_length = "terse"
        sm.profile.working_hours = {"start": "09:00", "end": "17:00"}
        path = sm.write_profile_to_vault()
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "terse" in text.lower()

    def test_profile_markdown_format(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        sm = OttoSelfModel(vault_path=tmp_vault)
        sm.profile.add_pattern("short_sentences", "Sir Agathon uses short sentences", confidence=0.9)
        md = sm.profile.profile_to_markdown()
        assert "# Otto Self-Model" in md
        assert "short_sentences" in md
