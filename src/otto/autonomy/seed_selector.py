from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, read_jsonl, state_root
from ..state import now_iso, write_json
from .note_vector import load_note_vectors
from .steering_vector import load_steering_vector


SUPPORTED_KINDS = {"song", "paper", "blocker", "memento"}


def candidate_seeds_path() -> Path:
    return state_root() / "autonomy" / "candidate_seeds.jsonl"


def selected_seeds_path() -> Path:
    return state_root() / "autonomy" / "selected_seeds.jsonl"


def _score(vector: dict[str, Any], kind: str, steering: dict[str, Any]) -> dict[str, float]:
    affinity = vector.get("artifact_affinity") or {}
    suffering = vector.get("suffering_vector") or {}
    kind_key = {"song": "song", "paper": "paper_onboarding", "blocker": "skill_drill", "memento": "memento"}[kind]
    evidence_strength = min(1.0, len(vector.get("evidence_refs") or []) / 4.0)
    artifact_fit = float(affinity.get(kind_key, 0.5))
    suffering_intensity = sum(float(suffering.get(key, 0.0)) for key in suffering) / max(1, len(suffering))
    steering_alignment = 0.93 if kind in {"song", "paper"} else 0.82
    meaning_density = min(1.0, 0.48 + 0.06 * len(vector.get("anchors") or []))
    unfinishedness = 0.72
    novelty = 0.64
    total = (
        meaning_density * 0.2
        + suffering_intensity * 0.15
        + artifact_fit * 0.25
        + unfinishedness * 0.1
        + steering_alignment * 0.2
        + novelty * 0.05
        + evidence_strength * 0.05
    )
    return {
        "meaning_density": round(meaning_density, 3),
        "suffering_vector_intensity": round(suffering_intensity, 3),
        "artifact_fit": round(artifact_fit, 3),
        "unfinishedness": round(unfinishedness, 3),
        "steering_alignment": round(steering_alignment, 3),
        "novelty": round(novelty, 3),
        "evidence_strength": round(evidence_strength, 3),
        "total": round(total, 3),
    }


def candidate_seeds(kind: str) -> list[dict[str, Any]]:
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"unsupported seed kind: {kind}")
    steering = load_steering_vector()
    seeds: list[dict[str, Any]] = []
    for index, vector in enumerate(load_note_vectors()):
        score = _score(vector, kind, steering)
        seeds.append(
            {
                "seed_id": f"seed_{kind}_{index + 1}",
                "kind": kind,
                "source": vector.get("source"),
                "source_vector_id": vector.get("vector_id"),
                "source_refs": vector.get("source_refs", []),
                "evidence_refs": vector.get("evidence_refs", []),
                "anchors": vector.get("anchors", []),
                "existential_atoms": vector.get("existential_atoms", []),
                "suffering_vector": vector.get("suffering_vector", {}),
                "score": score,
                "selected_for": f"autonomous_{kind}",
                "reason": "Highest steering-aligned reviewed/private note vector for this artifact kind.",
                "review_required": True,
                "qmd_index_allowed": False,
                "vault_writeback_allowed": False,
                "created_at": now_iso(),
            }
        )
    return sorted(seeds, key=lambda item: float((item.get("score") or {}).get("total", 0.0)), reverse=True)


def select_seed(kind: str, *, write: bool = False) -> dict[str, Any]:
    seeds = candidate_seeds(kind)
    if not seeds:
        return {"ok": False, "kind": kind, "no_output_reason": "no_note_vectors_available"}
    selected = seeds[0]
    if write:
        for seed in seeds:
            append_jsonl(candidate_seeds_path(), seed)
        append_jsonl(selected_seeds_path(), selected)
        write_json(state_root() / "autonomy" / "selected_seed_last.json", selected)
    return {"ok": True, "kind": kind, "seed": selected, "candidate_count": len(seeds)}

