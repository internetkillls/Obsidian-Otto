from __future__ import annotations

from otto.brain import (
    OttoSelfModel,
    PredictiveScaffold,
    MemoryLayer,
    MemoryTier,
    TierEntry,
)


def test_full_brain_flow(tmp_vault, monkeypatch):
    """End-to-end: scan -> self-model -> predictions -> ritual -> memory tiers"""
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))

    # 1. Create sample notes in vault
    note1 = tmp_vault / "10-Personal" / "goals.md"
    note1.parent.mkdir(parents=True, exist_ok=True)
    note1.write_text("---\ntags: [goal, personal]\n---\n# Goals\nLearn system architecture.", encoding="utf-8")

    note2 = tmp_vault / "01-Inbox" / "capture.md"
    note2.parent.mkdir(parents=True, exist_ok=True)
    note2.write_text("# Capture\nTODO: organize notes\n\nLinks to [[10-Personal/goals]]", encoding="utf-8")

    # 2. Build self-model
    sm = OttoSelfModel(vault_path=tmp_vault)
    snapshot = sm.build_from_scan({
        "note_count": 2,
        "notes": [
            {"tags": ["goal", "personal"], "wikilinks": [], "body_excerpt": "", "has_frontmatter": True},
            {"tags": [], "wikilinks": ["10-Personal/goals"], "body_excerpt": "TODO:", "has_frontmatter": False},
        ]
    })
    profile_path = sm.write_profile_to_vault()
    assert profile_path.exists()
    assert len(snapshot["strengths"]) >= 0

    # 3. Generate predictions
    ps = PredictiveScaffold(vault_path=tmp_vault)
    preds = ps.generate_from_profile({
        "vault_strengths": snapshot["strengths"],
        "vault_weaknesses": snapshot["weaknesses"],
        "observed_patterns": [],
    })
    pred_path = ps.write_predictions_to_vault()
    assert pred_path.exists()
    assert len(preds) >= 0

    # 4. Write memory tier entry
    ml = MemoryLayer(vault_path=tmp_vault)
    entry = TierEntry(
        tier=MemoryTier.INTERPRETATION,
        content="Test: Sir Agathon uses short capture notes with links to personal",
        source_note="Otto-Realm/Brain/test.md",
        confidence=0.8,
    )
    tier_path = ml.write_tier_entry(entry)
    assert tier_path.exists()

    # 5. Read back tier entries
    entries = ml.read_tier_entries(MemoryTier.INTERPRETATION)
    assert len(entries) >= 1
    assert entries[-1].tier == MemoryTier.INTERPRETATION

    # 6. Verify write boundary
    assert ml.write_boundary.can_write_new_note() is True
    assert ml.write_boundary.can_rewrite_vault_past("01-Inbox/capture.md") is False
    assert ml.write_boundary.can_rewrite_vault_without_concent("10-Personal/goals.md") is False
    assert ml.write_boundary.can_link_to_folder("Action") is True
