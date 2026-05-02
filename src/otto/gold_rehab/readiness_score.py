from __future__ import annotations

import json
from typing import Any


def build_note_readiness(note: dict[str, Any]) -> dict[str, Any]:
    text = str(note.get("body_excerpt") or "")
    tags = json.loads(note.get("tags_json") or "[]")
    has_frontmatter = bool(note.get("has_frontmatter"))
    metadata = 0.75 if has_frontmatter else 0.32
    semantic = min(0.2 + len(text.split()) / 40.0 + len(tags) * 0.05, 0.95)
    evidence = 0.74 if text else 0.35
    artifact = min(0.2 + 0.2 * sum(token in text.lower() for token in ["research", "essay", "song", "note", "idea"]), 0.95)
    research = min(0.2 + 0.2 * sum(token in text.lower() for token in ["research", "school", "method", "framework"]), 0.95)
    personal = min(0.2 + 0.2 * sum(token in text.lower() for token in ["workflow", "process", "habit", "support", "anchor"]), 0.95)
    duplicate = 0.18
    sensitivity = min(0.1 + 0.2 * sum(token in text.lower() for token in ["adhd", "audhd", "bd", "bipolar", "weakness", "profile"]), 0.95)
    gold = round((semantic + evidence + artifact + research + personal + (1.0 - duplicate)) / 6.0, 4)
    note_class = "mechanically_incomplete_but_semantically_valuable" if not has_frontmatter and semantic >= 0.6 else "metadata_complete_low_signal"
    if sensitivity >= 0.45:
        note_class = "sensitive_needs_review"
    if gold >= 0.7 and sensitivity < 0.45:
        note_class = "candidate_gold_after_enrichment"
    return {
        "note_id": note.get("path"),
        "path": f"vault:{note.get('path')}",
        "scores": {
            "metadata_completeness": round(metadata, 4),
            "semantic_density": round(semantic, 4),
            "evidence_resolvability": round(evidence, 4),
            "artifact_affinity": round(artifact, 4),
            "research_affinity": round(research, 4),
            "personal_algorithm_value": round(personal, 4),
            "duplicate_risk": round(duplicate, 4),
            "sensitivity_risk": round(sensitivity, 4),
            "gold_readiness": gold,
        },
        "class": note_class,
        "next_state": "G1_MECHANICALLY_REPAIRED" if not has_frontmatter else "G2_SEMANTICALLY_NORMALIZED",
        "recommended_actions": [
            "append_missing_frontmatter" if not has_frontmatter else "preserve_human_frontmatter",
            "infer_tags_as_suggestions",
            "extract_candidate_claims",
            "enqueue_batch_review" if sensitivity >= 0.45 else "allow_safe_append",
        ],
    }
