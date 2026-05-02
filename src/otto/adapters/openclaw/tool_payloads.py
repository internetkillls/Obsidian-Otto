from __future__ import annotations

from pathlib import Path
from typing import Any

from ...config import load_paths
from ...state import now_iso, write_json


TOOL_MANIFEST_VERSION = 1


def tool_manifest_path() -> Path:
    return load_paths().state_root / "openclaw" / "tool_manifest.json"


def build_openclaw_tool_manifest() -> dict[str, Any]:
    tools = [
        {
            "name": "otto.qmd_health",
            "description": "Return QMD source, manifest, and index health.",
            "command": "PYTHONPATH=src python3 -m otto.cli qmd-index-health",
            "risk": "read_only",
        },
        {
            "name": "otto.qmd_manifest",
            "description": "Return the Otto-managed QMD manifest.",
            "command": "PYTHONPATH=src python3 -m otto.cli qmd-manifest",
            "risk": "read_only",
        },
        {
            "name": "otto.context_pack",
            "description": "Return the current Otto context pack for OpenClaw.",
            "command": "PYTHONPATH=src python3 -m otto.cli openclaw-context-pack",
            "risk": "read_only",
        },
        {
            "name": "otto.source_registry",
            "description": "Return canonical source registry policy and path health.",
            "command": "PYTHONPATH=src python3 -m otto.cli source-registry",
            "risk": "read_only",
        },
        {
            "name": "otto.runtime_status",
            "description": "Return runtime smoke gate state.",
            "command": "PYTHONPATH=src python3 -m otto.cli runtime-smoke",
            "risk": "read_only",
        },
        {
            "name": "otto.heartbeat",
            "description": "Plan one review-gated creative heartbeat without publication.",
            "command": "PYTHONPATH=src python3 -m otto.cli creative-heartbeat --dry-run",
            "risk": "candidate_generation",
        },
        {
            "name": "otto.autonomous_heartbeat",
            "description": "Run vector-steered autonomous song/paper candidate selection in review-gated dry-run mode.",
            "command": "PYTHONPATH=src python3 -m otto.cli autonomous-heartbeat --dry-run",
            "risk": "candidate_generation",
        },
        {
            "name": "otto.seed_select",
            "description": "Select a reviewed/private seed for autonomous generation.",
            "command": "PYTHONPATH=src python3 -m otto.cli seed-select --kind song",
            "risk": "read_write_private_state",
        },
        {
            "name": "otto.song_skeleton_next",
            "description": "Generate one review-gated SongForge skeleton candidate.",
            "command": "PYTHONPATH=src python3 -m otto.cli song-skeleton --dry-run",
            "risk": "candidate_generation",
        },
        {
            "name": "otto.paper_onboarding_next",
            "description": "Generate one research onboarding pack candidate.",
            "command": "PYTHONPATH=src python3 -m otto.cli paper-onboarding --dry-run",
            "risk": "web_research_candidate",
        },
        {
            "name": "otto.memento_due",
            "description": "Build the Memento due queue from quizworthy reviewed or Gold blocks.",
            "command": "PYTHONPATH=src python3 -m otto.cli memento-due",
            "risk": "read_write_private_state",
        },
        {
            "name": "otto.blocker_experiment_next",
            "description": "Generate one bounded blocker experiment candidate.",
            "command": "PYTHONPATH=src python3 -m otto.cli blocker-experiment --dry-run",
            "risk": "candidate_generation",
        },
        {
            "name": "otto.visual_inspo_query",
            "description": "Generate a visual inspiration query/reference pointer.",
            "command": "PYTHONPATH=src python3 -m otto.cli visual-inspo-query --dry-run",
            "risk": "web_query_candidate",
        },
        {
            "name": "otto.feedback_ingest",
            "description": "Ingest private creative feedback into state-only learning priors.",
            "command": "PYTHONPATH=src python3 -m otto.cli feedback-ingest --dry-run",
            "risk": "read_write_private_state",
        },
        {
            "name": "otto.heartbeat_readiness",
            "description": "Run strict readiness checks for heartbeat tools, bridge health, and safety gates.",
            "command": "PYTHONPATH=src python3 -m otto.cli heartbeat-readiness --strict",
            "risk": "read_only",
        },
    ]
    return {
        "version": TOOL_MANIFEST_VERSION,
        "state": "OCB1_TOOL_MANIFEST_GENERATED",
        "generated_at": now_iso(),
        "tools": tools,
    }


def write_openclaw_tool_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest = build_openclaw_tool_manifest()
    target = path or tool_manifest_path()
    write_json(target, manifest)
    return {"ok": True, "path": str(target), "manifest": manifest}
