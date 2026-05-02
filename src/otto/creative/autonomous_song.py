from __future__ import annotations

from pathlib import Path
from typing import Any

from ..autonomy.seed_selector import select_seed
from ..governance_utils import append_jsonl, make_id, state_root
from ..state import now_iso, write_json
from .songforge import build_song_skeleton


def autonomous_song_candidates_path() -> Path:
    return state_root() / "creative" / "songforge" / "autonomous_song_candidates.jsonl"


def _seed_text(seed: dict[str, Any]) -> str:
    anchors = [str(item) for item in seed.get("anchors", [])[:3]] or ["Continuity Prosthesis"]
    atoms = [str(item) for item in seed.get("existential_atoms", [])[:2]] or ["I build systems because returning to myself is hard."]
    return "\n".join([*(f"# {anchor}" for anchor in anchors), *(f"@ {atom}" for atom in atoms)])


def build_autonomous_song_candidate(*, dry_run: bool = True, seed: dict[str, Any] | None = None) -> dict[str, Any]:
    selected = {"ok": True, "seed": seed} if seed else select_seed("song", write=not dry_run)
    if not selected.get("ok"):
        return {"ok": False, "dry_run": dry_run, "no_output_reason": selected.get("no_output_reason", "no_song_seed_available")}
    seed = selected["seed"]
    skeleton_result = build_song_skeleton(_seed_text(seed), dry_run=True)
    skeleton = skeleton_result["skeleton"]
    rhythm_routes = list(skeleton_result["rhythms"])
    while rhythm_routes and len(rhythm_routes) < 4:
        rhythm_routes.append({**rhythm_routes[-1], "variant_id": f"{rhythm_routes[-1].get('variant_id', 'route')}_auto_fill_{len(rhythm_routes) + 1}"})
    candidate = {
        "song_candidate_id": make_id("autosong"),
        "state": "SONG_SKELETON_CANDIDATE",
        "source": "autonomous_note_vector",
        "derived_seed": {
            "context_anchors": seed.get("anchors", [])[:3],
            "existential_atoms": seed.get("existential_atoms", []),
            "evidence_refs": seed.get("evidence_refs", []),
        },
        "song_rules_applied": {
            "chord_first": True,
            "one_atom_max_one_chord_cycle": True,
            "existential_censorship": True,
        },
        "suffering_vector": seed.get("suffering_vector", {}),
        "chord_cycle": skeleton_result["cycle"],
        "rhythm_routes": rhythm_routes,
        "lyric_translation": skeleton_result["lyric"],
        "midi_spec": skeleton_result["midi_spec"],
        "visual_inspo_query": skeleton.get("visual_inspo_query"),
        "review_required": True,
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "auto_publish": False,
        "created_at": now_iso(),
    }
    if not dry_run:
        append_jsonl(autonomous_song_candidates_path(), candidate)
        write_json(state_root() / "creative" / "songforge" / "autonomous_song_last.json", candidate)
    return {"ok": True, "dry_run": dry_run, "candidate": candidate, "seed": seed}
