from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..corridor import ensure_jsonl_row
from ..governance_utils import state_root
from .risk_classifier import classify_risk


def semantic_enrichment_candidates_path() -> Path:
    return state_root() / "gold_rehab" / "semantic_enrichment_candidates.jsonl"


def build_semantic_enrichment_candidate(note: dict[str, Any], readiness: dict[str, Any], *, persist: bool = True) -> dict[str, Any]:
    tags = json.loads(note.get("tags_json") or "[]")
    body = str(note.get("body_excerpt") or "")
    suggested_tags = [{"tag": tag, "confidence": 0.7} for tag in tags[:5]]
    if not suggested_tags:
        for token in ["interface", "constraint", "research", "workflow", "support"]:
            if token in body.lower():
                suggested_tags.append({"tag": token, "confidence": 0.66})
    payload = {
        "path": note.get("path"),
        "title": note.get("title"),
        "risk": classify_risk(note_class=str(readiness.get("class") or ""), text=body),
        "otto": {
            "state": readiness.get("next_state"),
            "enriched_by": "otto",
            "enrichment_version": 1,
            "enrichment_generated_at": __import__("otto.state", fromlist=["now_iso"]).now_iso(),
            "source_checksum": note.get("sha1"),
            "review_status": "auto_applied_low_risk",
            "qmd_index_allowed": False,
            "vault_writeback_allowed": False,
            "provenance": {"method": "gold_rehab_safe_append"},
        },
        "otto_suggestions": {
            "suggested_kind": [{"value": "research_note", "confidence": 0.74}],
            "suggested_tags": suggested_tags,
            "suggested_entities": [token for token in ["interface", "scarcity", "mechanism"] if token in body.lower()],
        },
        "markdown_block": (
            "<!-- OTTO:ENRICHMENT v1 risk={risk} review=auto_applied_low_risk -->\n"
            "## Otto Enrichment\n\n"
            "**Summary candidate:** {summary}\n\n"
            "**Detected kind:** research_note  \n"
            "**Suggested tags:** {tags}  \n"
            "**Gold ladder:** {next_state} candidate\n\n"
            "**Review note:** Low-risk semantic enrichment. No profile/diagnostic claim added.\n"
            "<!-- /OTTO:ENRICHMENT -->"
        ).format(
            risk=classify_risk(note_class=str(readiness.get("class") or ""), text=body),
            summary=(body.split(".")[0] or "This note has semantic value.").strip(),
            tags=" ".join(f"#{item['tag']}" for item in suggested_tags[:4]),
            next_state=readiness.get("next_state"),
        ),
        "readiness": readiness,
    }
    if persist:
        ensure_jsonl_row(semantic_enrichment_candidates_path(), payload)
    return payload
