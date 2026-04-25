from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..state import now_iso


@dataclass
class Prediction:
    prediction: str
    confidence: float
    trigger: str
    horizon_days: int
    ts: str = field(default_factory=now_iso)

    def to_markdown(self) -> str:
        return f"""# Prediction

- **What:** {self.prediction}
- **Confidence:** {self.confidence:.0%}
- **Horizon:** {self.horizon_days} day(s)
- **Trigger:** {self.trigger}
- **Created:** {self.ts}

---

*This is Otto's anticipation — not a promise. Confidence below 0.6 means low certainty.*
"""


class PredictiveScaffold:
    PREDICTIONS_PATH = ".Otto-Realm/Predictions"

    def __init__(self, vault_path: Path | None = None):
        paths = load_paths()
        self.vault_path = vault_path or paths.vault_path
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        self.predictions: list[Prediction] = []

    def add_prediction(
        self,
        prediction: str,
        confidence: float,
        trigger: str,
        horizon_days: int,
    ) -> Prediction:
        p = Prediction(
            prediction=prediction,
            confidence=max(0.0, min(1.0, confidence)),
            trigger=trigger,
            horizon_days=horizon_days,
        )
        self.predictions.append(p)
        return p

    def generate_from_profile(self, profile: dict[str, Any]) -> list[Prediction]:
        self.predictions.clear()
        weaknesses = profile.get("vault_weaknesses", [])
        strengths = profile.get("vault_strengths", [])
        patterns = profile.get("observed_patterns", [])
        cognitive_risks = profile.get("cognitive_risks", [])
        recovery_levers = profile.get("recovery_levers", [])
        commitments = profile.get("continuity_commitments", [])
        opportunities = profile.get("opportunity_map", [])
        support_style = profile.get("support_style", [])
        mentor_pending_tasks = profile.get("mentor_pending_tasks", [])
        continuity_prompts = profile.get("continuity_prompts", []) or profile.get("sm2_hooks", [])
        suffering_signals = profile.get("suffering_signals", [])

        if any("orphan" in w.lower() for w in weaknesses):
            self.add_prediction(
                prediction="Next vault action: linking orphan notes to MOC anchors",
                confidence=0.75,
                trigger="High orphan ratio detected in last scan",
                horizon_days=3,
            )

        if any("frontmatter" in w.lower() for w in weaknesses):
            self.add_prediction(
                prediction="Next focus: normalizing frontmatter on tagged notes",
                confidence=0.7,
                trigger="Missing frontmatter detected",
                horizon_days=5,
            )

        pattern_names = [p.get("pattern", "") for p in patterns]
        if "terse_responses" in pattern_names:
            self.add_prediction(
                prediction="Sir Agathon will appreciate terse, actionable responses",
                confidence=0.85,
                trigger="Terse response pattern confirmed across sessions",
                horizon_days=1,
            )

        if any("wikilink" in s.lower() for s in strengths):
            self.add_prediction(
                prediction="Sir Agathon values connected knowledge — keep linking dense",
                confidence=0.8,
                trigger="Strong wikilink discipline observed",
                horizon_days=7,
            )

        if commitments:
            top = commitments[0]
            self.add_prediction(
                prediction=f"Recall commitment proactively: revisit '{top['cue']}' before it slips again",
                confidence=min(0.9, top.get("confidence", 0.7)),
                trigger=f"Commitment signal found in {top['path']}",
                horizon_days=2,
            )

        if opportunities:
            top = opportunities[0]
            self.add_prediction(
                prediction=f"Surface opportunity from history: '{top['cue']}' may still be actionable",
                confidence=min(0.9, top.get("confidence", 0.7)),
                trigger=f"Opportunity signal found in {top['path']}",
                horizon_days=7 if top.get("horizon") != "1y+" else 30,
            )

        if cognitive_risks:
            self.add_prediction(
                prediction="Use one-question check-ins and continuity recall instead of waiting for long chat turns",
                confidence=0.82,
                trigger=cognitive_risks[0],
                horizon_days=1,
            )

        if recovery_levers:
            self.add_prediction(
                prediction=f"Best recovery move is probably: {recovery_levers[0]}",
                confidence=0.78,
                trigger="Recovery pattern inferred from vault evidence",
                horizon_days=1,
            )

        if support_style:
            self.add_prediction(
                prediction=f"Interaction should bias toward this support style: {support_style[0]}",
                confidence=0.8,
                trigger="Support-style pattern stabilized",
                horizon_days=3,
            )

        if mentor_pending_tasks:
            top_task = mentor_pending_tasks[0]
            self.add_prediction(
                prediction=f"Review active mentor task: {top_task['title']}",
                confidence=0.9,
                trigger=f"Closed-loop training queue active ({top_task['task_id']})",
                horizon_days=2,
            )

        if continuity_prompts and not mentor_pending_tasks:
            self.add_prediction(
                prediction=f"Ask continuity prompt: {continuity_prompts[0]['question']}",
                confidence=min(0.88, continuity_prompts[0].get("confidence", 0.7)),
                trigger=f"Continuity prompt prepared from {continuity_prompts[0]['path']}",
                horizon_days=3,
            )

        if suffering_signals:
            self.add_prediction(
                prediction="A stalled pressure should be reframed as either generative suffering or drag to remove",
                confidence=0.74,
                trigger=suffering_signals[0],
                horizon_days=5,
            )

        return self.predictions

    def write_predictions_to_vault(self) -> Path:
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        pred_dir = self.vault_path / self.PREDICTIONS_PATH
        pred_dir.mkdir(parents=True, exist_ok=True)

        today = now_iso()[:10]
        filename = f"{today}_predictions.md"
        path = pred_dir / filename

        lines = [
            f"# Otto Predictions — {today}",
            "",
            f"Generated: {now_iso()}",
            "",
            f"Total predictions: {len(self.predictions)}",
            "",
            "## Active Predictions",
            "",
        ]
        for i, p in enumerate(self.predictions, 1):
            lines.append(f"### {i}. {p.prediction}")
            lines.append(f"- Confidence: {p.confidence:.0%}")
            lines.append(f"- Horizon: {p.horizon_days} day(s)")
            lines.append(f"- Trigger: {p.trigger}")
            lines.append(f"- Created: {p.ts}")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return path
