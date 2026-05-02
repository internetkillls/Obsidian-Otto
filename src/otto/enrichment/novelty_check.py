from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path

from ..governance_utils import read_jsonl, state_root


def _candidate_path() -> Path:
    return state_root() / "enrichment" / "candidate_insights.jsonl"


def novelty_report(claim: str) -> dict[str, float]:
    scores = []
    for row in read_jsonl(_candidate_path()):
        existing = str(row.get("claim") or "")
        if existing and existing != claim:
            scores.append(SequenceMatcher(a=claim, b=existing).ratio())
    duplicate_score = max(scores) if scores else 0.0
    return {"duplicate_score": round(duplicate_score, 4)}
