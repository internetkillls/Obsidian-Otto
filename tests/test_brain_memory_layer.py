from __future__ import annotations

import pytest
from pathlib import Path

from otto.brain.memory_layer import MemoryTier, WriteBoundary, TierEntry


class TestMemoryTier:
    def test_tier_enum_values(self):
        assert MemoryTier.FACT.value == "otto-fact"
        assert MemoryTier.INTERPRETATION.value == "otto-interpretation"
        assert MemoryTier.SPECULATION.value == "otto-speculation"


class TestWriteBoundary:
    def test_can_write_new_note_allowed(self):
        wb = WriteBoundary()
        assert wb.can_write_new_note() is True

    def test_can_rewrite_vault_past_denied(self):
        wb = WriteBoundary()
        assert wb.can_rewrite_vault_past(target="01-Inbox/test.md") is False

    def test_can_rewrite_vault_without_concent_denied(self):
        wb = WriteBoundary()
        assert wb.can_rewrite_vault_without_concent(target="10-Personal/diary.md") is False

    def test_can_link_to_action_allowed(self):
        wb = WriteBoundary()
        assert wb.can_link_to_folder("Action") is True

    def test_can_link_to_project_allowed(self):
        wb = WriteBoundary()
        assert wb.can_link_to_folder("30-Projects") is True

    def test_future_ref_link_allowed(self):
        wb = WriteBoundary()
        assert wb.can_write_future_ref_links() is True


class TestTierEntry:
    def test_tier_entry_creation(self):
        entry = TierEntry(
            tier=MemoryTier.FACT,
            content="Sir Agathon prefers short responses",
            source_note="Otto-Realm/Brain/preference_model.md",
            confidence=0.9,
        )
        assert entry.tier == MemoryTier.FACT
        assert entry.confidence == 0.9
        assert "short responses" in entry.content


class TestMemoryLayer:
    def test_resolve_tier_path_fact(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        from otto.brain.memory_layer import MemoryLayer
        ml = MemoryLayer(vault_path=tmp_vault)
        result = ml.resolve_tier_path(MemoryTier.FACT)
        assert "01-Facts" in str(result)

    def test_resolve_tier_path_interpretation(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        from otto.brain.memory_layer import MemoryLayer
        ml = MemoryLayer(vault_path=tmp_vault)
        result = ml.resolve_tier_path(MemoryTier.INTERPRETATION)
        assert "02-Interpretations" in str(result)

    def test_resolve_tier_path_speculation(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        from otto.brain.memory_layer import MemoryLayer
        ml = MemoryLayer(vault_path=tmp_vault)
        result = ml.resolve_tier_path(MemoryTier.SPECULATION)
        assert "03-Speculations" in str(result)

    def test_write_tier_entry_creates_file(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        from otto.brain.memory_layer import MemoryLayer
        ml = MemoryLayer(vault_path=tmp_vault)
        entry = TierEntry(
            tier=MemoryTier.FACT,
            content="Sir Agathon prefers terse responses",
            source_note="Otto-Realm/Brain/preference.md",
            confidence=0.95,
        )
        path = ml.write_tier_entry(entry)
        assert path.exists()
        assert path.suffix == ".md"

    def test_write_tier_entry_content_has_tags(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        from otto.brain.memory_layer import MemoryLayer
        ml = MemoryLayer(vault_path=tmp_vault)
        entry = TierEntry(
            tier=MemoryTier.SPECULATION,
            content="Otto predicts Sir Agathon will prioritize vault hygiene",
            source_note="Otto-Realm/Predictions/vault_hygiene.md",
            confidence=0.6,
        )
        path = ml.write_tier_entry(entry)
        text = path.read_text(encoding="utf-8")
        assert "otto-speculation" in text
        assert "confidence: 0.6" in text

    def test_read_tier_entries_empty_when_no_files(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        from otto.brain.memory_layer import MemoryLayer
        ml = MemoryLayer(vault_path=tmp_vault)
        entries = ml.read_tier_entries(MemoryTier.FACT)
        assert entries == []

    def test_read_tier_entries_returns_written_entry(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        from otto.brain.memory_layer import MemoryLayer
        ml = MemoryLayer(vault_path=tmp_vault)
        entry = TierEntry(
            tier=MemoryTier.INTERPRETATION,
            content="Sir Agathon seems to value directness",
            source_note="Otto-Realm/Brain/style.md",
            confidence=0.8,
        )
        ml.write_tier_entry(entry)
        entries = ml.read_tier_entries(MemoryTier.INTERPRETATION)
        assert len(entries) >= 1
        assert entries[-1].tier == MemoryTier.INTERPRETATION
