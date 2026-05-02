from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, make_id, state_root
from ..state import now_iso
from .song_syntax import parse_song_seed


def raw_song_seeds_path() -> Path:
    return state_root() / "creative" / "songforge" / "raw_song_seeds.jsonl"


def parsed_song_atoms_path() -> Path:
    return state_root() / "creative" / "songforge" / "parsed_song_atoms.jsonl"


def persist_song_seed(text: str, *, dry_run: bool = False) -> dict[str, Any]:
    parsed = parse_song_seed(text)
    seed = {
        "song_seed_id": make_id("songseed"),
        "state": "RAW_SONG_SEED",
        "raw_text": text,
        "context_anchors": parsed.context_anchors,
        "existential_atoms": parsed.existential_atoms,
        "privacy": "private",
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "created_at": now_iso(),
    }
    atoms = []
    for atom in parsed.existential_atoms:
        atom_item = {
            "atom_id": make_id("atom"),
            "song_seed_id": seed["song_seed_id"],
            "state": "EXISTENTIAL_ATOM_PARSED",
            "raw_meaning": atom,
            "translation_rule": "phenomenological_not_explicit",
            "max_chord_cycles": 1,
            "candidate_images": [
                "jam mati di dapur",
                "bau baju yang belum pergi",
                "pagi tumbuh di jendela",
            ],
        }
        atoms.append(atom_item)
    if not dry_run:
        append_jsonl(raw_song_seeds_path(), seed)
        for atom in atoms:
            append_jsonl(parsed_song_atoms_path(), atom)
    return {"ok": True, "dry_run": dry_run, "seed": seed, "atoms": atoms}
