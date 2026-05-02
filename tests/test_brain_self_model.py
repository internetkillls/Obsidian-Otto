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
        p.cognitive_risks = ["Context switching stays expensive; continuity must be carried by the system."]
        p.recovery_levers = ["Short, concrete prompts with one next step reduce friction."]
        p.continuity_commitments = [{"cue": "Portfolio one-pager", "path": "10-Personal/goal.md", "kind": "goal", "confidence": 0.8}]
        md = p.profile_to_markdown()
        assert "# Otto Self-Model" in md
        assert "short_sentences" in md
        assert "Continuity Commitments" in md
        assert "Portfolio one-pager" in md


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
                {
                    "path": "10-Personal/goal.md",
                    "tags": ["goal"],
                    "wikilinks": ["30-Projects/app"],
                    "body_excerpt": "Need to finish portfolio one-pager this week for client proposal.",
                    "frontmatter_text": "type: goal",
                },
                {
                    "path": "30-Projects/service-offer.md",
                    "tags": ["business"],
                    "wikilinks": [],
                    "body_excerpt": "Monetizable opportunity: package service offer for revenue next year.",
                    "frontmatter_text": "type: project",
                },
            ]
        }
        result = sm.build_from_scan(mock_scan)
        assert "profile_snapshot" in result
        assert "strengths" in result
        assert "weaknesses" in result
        assert result["continuity_commitments"]
        assert result["opportunity_map"]
        assert result["continuity_prompts"]
        assert "sm2_hooks" not in result

    def test_build_from_scan_prioritizes_personal_vault_sources_over_narrow_scan(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        personal = tmp_vault / "10-Personal" / "commitment.md"
        personal.parent.mkdir(parents=True, exist_ok=True)
        personal.write_text(
            "---\ntags: [goal, personal]\n---\n# Commitment\nSaya perlu follow up portfolio one-pager minggu ini.",
            encoding="utf-8",
        )

        monolog = tmp_vault / "!My" / "Backboard" / "reentry.md"
        monolog.parent.mkdir(parents=True, exist_ok=True)
        monolog.write_text(
            "# Re-entry\nI want a small system that remembers my commitments and asks one short question.",
            encoding="utf-8",
        )

        archived = tmp_vault / "90-Archive" / "old-opportunity.md"
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_text(
            "# Old Opportunity\nThis old client service package opportunity from 2 years ago may still be monetizable.",
            encoding="utf-8",
        )

        noisy = tmp_vault / ".Otto-Realm" / "Reports" / "echo.md"
        noisy.parent.mkdir(parents=True, exist_ok=True)
        noisy.write_text(
            "# Echo\nNeed to follow up the generated report again.",
            encoding="utf-8",
        )

        sm = OttoSelfModel(vault_path=tmp_vault)
        result = sm.build_from_scan({
            "note_count": 1,
            "notes": [
                {
                    "path": "00-Meta/scarcity/LACK-generated.md",
                    "tags": ["scarcity"],
                    "wikilinks": [],
                    "body_excerpt": "Need to follow up generic scarcity issue.",
                    "frontmatter_text": "",
                    "has_frontmatter": False,
                }
            ],
        })

        top_commitment_paths = [item["path"] for item in result["continuity_commitments"][:3]]
        top_opportunity_paths = [item["path"] for item in result["opportunity_map"][:3]]
        assert "10-Personal/commitment.md" in top_commitment_paths
        assert "90-Archive/old-opportunity.md" in top_opportunity_paths
        assert all(not path.startswith(".Otto-Realm/Reports") for path in top_commitment_paths + top_opportunity_paths)

    def test_build_from_scan_emits_weakness_taxonomy_from_mentor_registry(self):
        sm = OttoSelfModel.__new__(OttoSelfModel)
        sm.profile = SirAgathonProfile()
        sm.vault_path = None
        result = sm.build_from_scan(
            {
                "note_count": 1,
                "notes": [
                    {
                        "path": "10-Personal/goal.md",
                        "tags": ["goal"],
                        "wikilinks": [],
                        "body_excerpt": "Need a proof routine.",
                        "frontmatter_text": "type: goal",
                    }
                ],
            },
            mentor_weakness_registry={
                "proof_construction": {
                    "latest_gap_type": "theory_gap",
                    "probe_history": [{"id": "a"}, {"id": "b"}],
                },
                "execution_discipline": {
                    "latest_gap_type": "application_gap",
                    "probe_history": [{"id": "c"}],
                },
                "resolved_loop": {
                    "latest_gap_type": "resolved",
                    "probe_history": [{"id": "z"}],
                },
            },
        )
        taxonomy = result["weakness_taxonomy"]
        keys = [item["weakness_key"] for item in taxonomy]
        assert "proof_construction" in keys
        assert "execution_discipline" in keys
        assert "resolved_loop" not in keys
        proof_entry = next(item for item in taxonomy if item["weakness_key"] == "proof_construction")
        assert proof_entry["gap_type"] == "theory_gap"
        assert proof_entry["recurrence_count"] == 2

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
        sm.profile.sm2_hooks = [{"question": "Apa status target ini?", "path": "10-Personal/goal.md", "confidence": 0.7}]
        md = sm.profile.profile_to_markdown()
        assert "# Otto Self-Model" in md
        assert "short_sentences" in md
        assert "Continuity Prompts" in md

    def test_legacy_sm2_property_maps_to_continuity_prompts(self):
        sm = OttoSelfModel.__new__(OttoSelfModel)
        sm.profile = SirAgathonProfile()
        sm.profile.sm2_hooks = [{"question": "Apa status target ini?", "path": "10-Personal/goal.md", "confidence": 0.7}]
        assert sm.profile.continuity_prompts
        assert sm.profile.sm2_hooks == sm.profile.continuity_prompts
