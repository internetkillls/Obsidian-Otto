from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..governance_utils import append_jsonl, read_jsonl, state_root
from ..state import now_iso, read_json, write_json


ANCHOR_WORDS = [
    "continuity",
    "memory",
    "archive",
    "return",
    "thread",
    "interface",
    "constraint",
    "suffering",
    "love",
    "music",
    "paper",
    "research",
    "blocker",
    "memento",
    "architecture",
    "survival",
]


def note_vectors_path() -> Path:
    return state_root() / "autonomy" / "note_vectors.jsonl"


def _read_text(path: Path, *, limit: int = 4000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def _collect_sources() -> list[dict[str, str]]:
    paths = load_paths()
    repo = paths.repo_root
    vault = paths.vault_path
    sources: list[dict[str, str]] = []
    for rel in [
        "state/handoff/latest.json",
        "artifacts/reports/dream_summary.md",
        "artifacts/reports/kairos_daily_strategy.md",
        "artifacts/reports/otto_profile.md",
    ]:
        path = repo / rel
        text = _read_text(path)
        if text:
            sources.append({"ref": rel, "text": text})
    if vault:
        brain = vault / ".Otto-Realm" / "Brain"
        if brain.exists():
            for path in sorted(brain.glob("*.md"))[:6]:
                text = _read_text(path, limit=1600)
                if text:
                    sources.append({"ref": f"vault:.Otto-Realm/Brain/{path.name}", "text": text})
        heartbeats = vault / ".Otto-Realm" / "Heartbeats"
        if heartbeats.exists():
            for path in sorted(heartbeats.glob("*.md"))[-3:]:
                text = _read_text(path, limit=1200)
                if text:
                    sources.append({"ref": f"vault:.Otto-Realm/Heartbeats/{path.name}", "text": text})
    return sources


def _anchorize(text: str) -> list[str]:
    lowered = text.lower()
    anchors = [word for word in ANCHOR_WORDS if word in lowered]
    titleish = re.findall(r"(?m)^#\s+(.{4,80})$", text)
    anchors.extend(item.strip() for item in titleish[:4])
    clean = []
    for item in anchors:
        normalized = re.sub(r"\s+", " ", item).strip(" .:-")
        if normalized and normalized not in clean:
            clean.append(normalized)
    return clean[:8] or ["continuity", "meaning", "returning to the thread"]


def _existential_atoms(anchors: list[str]) -> list[str]:
    primary = anchors[0] if anchors else "memory"
    secondary = anchors[1] if len(anchors) > 1 else "return"
    return [
        f"I keep returning to {primary} because the thread matters.",
        f"{secondary.capitalize()} becomes useful only when it can call me back.",
    ]


def build_note_vector(*, write: bool = False) -> dict[str, Any]:
    sources = _collect_sources()
    text = "\n".join(item["text"] for item in sources)
    anchors = _anchorize(text)
    vector = {
        "vector_id": f"nmv_{now_iso().replace(':', '').replace('-', '')[:15]}",
        "source": "reviewed_private_sources",
        "source_refs": [item["ref"] for item in sources],
        "evidence_refs": [item["ref"] for item in sources],
        "anchors": anchors,
        "existential_atoms": _existential_atoms(anchors),
        "suffering_vector": {
            "longing": 0.76 if "return" in anchors or "thread" in anchors else 0.58,
            "fatigue": 0.62 if "blocker" in anchors else 0.42,
            "tenderness": 0.72 if "love" in anchors or "memory" in anchors else 0.55,
            "revolt": 0.44,
            "hope": 0.61,
        },
        "artifact_affinity": {
            "song": 0.86 if any(item in anchors for item in ["love", "music", "memory"]) else 0.72,
            "paper_onboarding": 0.82 if any(item in anchors for item in ["research", "interface", "constraint"]) else 0.58,
            "prose": 0.76,
            "skill_drill": 0.66 if "blocker" in anchors else 0.48,
            "memento": 0.7 if "memento" in anchors or "memory" in anchors else 0.54,
        },
        "qmd_index_allowed": False,
        "raw_notes_dumped": False,
        "review_required": True,
        "created_at": now_iso(),
    }
    if write:
        append_jsonl(note_vectors_path(), vector)
        write_json(state_root() / "autonomy" / "note_vectors_last.json", vector)
    return {"ok": bool(vector["evidence_refs"]), "note_vector": vector, "source_count": len(sources)}


def load_note_vectors() -> list[dict[str, Any]]:
    rows = read_jsonl(note_vectors_path())
    if rows:
        return rows
    built = build_note_vector(write=False)
    vector = built.get("note_vector")
    if isinstance(vector, dict) and not vector.get("evidence_refs"):
        return []
    return [vector] if isinstance(vector, dict) else []
