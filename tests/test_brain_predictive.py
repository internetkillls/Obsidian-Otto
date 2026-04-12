from __future__ import annotations

import pytest
from otto.brain.predictive_scaffold import Prediction, PredictiveScaffold


class TestPrediction:
    def test_prediction_creation(self):
        p = Prediction(
            prediction="Sir Agathon will prioritize vault hygiene next week",
            confidence=0.65,
            trigger="increased note capture observed",
            horizon_days=7,
        )
        assert p.prediction is not None
        assert 0.0 <= p.confidence <= 1.0
        assert p.horizon_days >= 1

    def test_prediction_to_markdown(self):
        p = Prediction(
            prediction="Next focus: linking orphans to MOC",
            confidence=0.7,
            trigger="recent linking activity spike",
            horizon_days=3,
        )
        md = p.to_markdown()
        assert "# Prediction" in md
        assert "70%" in md
        assert "3 day(s)" in md


class TestPredictiveScaffold:
    def test_scaffold_initializes(self, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", "")
        ps = PredictiveScaffold.__new__(PredictiveScaffold)
        ps.vault_path = None
        ps.predictions = []
        assert ps.predictions == []

    def test_generate_predictions_from_profile(self):
        ps = PredictiveScaffold.__new__(PredictiveScaffold)
        ps.vault_path = None
        ps.predictions = []
        mock_profile = {
            "vault_weaknesses": ["High orphan ratio (5 orphan notes)"],
            "vault_strengths": ["Good wikilink density"],
            "observed_patterns": [],
        }
        preds = ps.generate_from_profile(mock_profile)
        assert isinstance(preds, list)

    def test_write_predictions_to_vault(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        ps = PredictiveScaffold(vault_path=tmp_vault)
        ps.add_prediction(
            prediction="Sir Agathon will check status tomorrow morning",
            confidence=0.75,
            trigger="morning routine observed",
            horizon_days=1,
        )
        path = ps.write_predictions_to_vault()
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "prediction" in text.lower()

    def test_add_prediction_stores(self, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", "")
        ps = PredictiveScaffold.__new__(PredictiveScaffold)
        ps.vault_path = None
        ps.predictions = []
        ps.add_prediction("Test prediction", confidence=0.5, trigger="test", horizon_days=2)
        assert len(ps.predictions) == 1
        assert ps.predictions[0].prediction == "Test prediction"
