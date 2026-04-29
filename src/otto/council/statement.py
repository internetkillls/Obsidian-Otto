from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, state_root
from ..state import now_iso


def council_statements_path() -> Path:
    return state_root() / "council" / "council_statements.jsonl"


def build_council_statement_candidate(trigger: dict[str, Any]) -> dict[str, Any]:
    statement = {
        "statement_id": make_id("council"),
        "state": "SYNTHESIS_CANDIDATE",
        "trigger": trigger,
        "functional_frame": {
            "code": "capacity_limit",
            "summary": "The pattern is framed as functional support need, not diagnosis.",
            "clinical_boundary": "not_diagnostic",
        },
        "lens_outputs": {
            "evidence_auditor": {"evidence_strength": "medium", "missing_evidence": [], "confidence": 0.62},
            "neurodivergent_support": {
                "support_need": "external re-entry anchor",
                "environment_or_prompt_change": "show last checkpoint before new task",
                "risk_of_overaccommodation": "too much scaffolding may delay action",
            },
            "mood_energy_stabilizer": {
                "activation_risk": "scope expansion",
                "stop_rule": "one bounded commit",
                "cooldown_or_boundary": "pause before new integration",
            },
            "mentor": {
                "probe": "What exactly gets lost when re-entering this thread?",
                "training_task": "Write one resume anchor before stopping work.",
                "completion_signal": "A handoff note exists.",
            },
            "contrarian": {
                "weakness_point": "Architecture can become avoidance if it does not close into daily action.",
                "counterargument": "More bridge work may avoid actual use.",
                "test": "Can Otto choose one action tomorrow morning?",
            },
            "morpheus_meaning": {
                "meaning": "The system is a continuity prosthesis.",
                "image_or_metaphor": "a lantern at the mouth of every tunnel",
                "expressive_form": "daily handoff ritual",
            },
            "execution_partner": {
                "next_action": "Implement daily-loop dry-run.",
                "scope": "one bounded commit",
                "expected_outcome": "daily_handoff.json and action_queue.jsonl generated with no side effects",
            },
        },
        "synthesis": {
            "weakness_point": "Architecture can become avoidance if it does not close into daily action.",
            "support_need": "bounded handoff and re-entry anchor",
            "stop_rule": "no social/profile automation before daily-loop dry-run",
            "mentor_probe_or_task": "write one resume anchor before ending each session",
            "smallest_next_action": "Implement daily-loop dry-run",
            "confidence": 0.74,
            "review_required": True,
        },
        "allowed_outputs_before_review": ["review_queue"],
        "blocked_outputs_before_review": ["vault", "qmd", "openclaw_context"],
        "created_at": now_iso(),
    }
    append_jsonl(council_statements_path(), statement)
    return statement
