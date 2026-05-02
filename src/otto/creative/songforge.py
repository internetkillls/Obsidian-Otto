from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, ensure_json, find_jsonl, make_id, public_result, state_root
from ..state import now_iso
from .harmony.cadence_router import choose_cadence_route
from .harmony.chord_cycle import generate_chord_cycle
from .harmony.chord_tension import derive_tension_targets
from .harmony.humanize import humanize_spec
from .harmony.rhythm_variants import generate_rhythm_variants
from .harmony.suffering_vector import derive_suffering_vector
from .song_seed import parsed_song_atoms_path, persist_song_seed


DEFAULT_SONGFORGE_POLICY: dict[str, Any] = {
    "version": 1,
    "mode": "candidate_generation",
    "song_seed": {
        "context_anchor_min": 1,
        "context_anchor_max": 3,
        "existential_atom_prefix": "@",
        "context_anchor_prefix": "#",
        "one_atom_max_chord_cycles": 1,
    },
    "generation_order": [
        "parse_seed",
        "derive_suffering_vector",
        "choose_chord_cycle",
        "choose_rhythm_routes",
        "derive_syllable_budget",
        "translate_lyrics",
        "render_midi_spec",
        "render_candidate_pack",
    ],
    "rhythm_variants_min": 4,
    "existential_censorship": {
        "mode": "phenomenological_translation",
        "do_not_state_meaning_directly": True,
        "turn_meaning_into": ["scene", "object", "gesture", "weather", "body sensation", "time residue", "domestic trace"],
        "avoid": ["generic self-help", "clinical phrasing", "over-explaining", "AI vocabulary", "philosophical thesis as lyric"],
    },
    "humanize": humanize_spec(),
    "safety": {
        "auto_publish": False,
        "auto_vault_write": False,
        "auto_qmd_index": False,
        "review_required_before_gold": True,
    },
}


def songforge_policy_path() -> Path:
    return state_root() / "creative" / "songforge" / "songforge_policy.json"


def load_songforge_policy() -> dict[str, Any]:
    return ensure_json(songforge_policy_path(), DEFAULT_SONGFORGE_POLICY)


def chord_cycles_path() -> Path:
    return state_root() / "creative" / "songforge" / "chord_cycles.jsonl"


def rhythm_routes_path() -> Path:
    return state_root() / "creative" / "songforge" / "rhythm_routes.jsonl"


def lyric_translations_path() -> Path:
    return state_root() / "creative" / "songforge" / "lyric_translations.jsonl"


def midi_specs_path() -> Path:
    return state_root() / "creative" / "songforge" / "midi_specs.jsonl"


def song_skeletons_path() -> Path:
    return state_root() / "creative" / "songforge" / "song_skeletons.jsonl"


def feedback_path() -> Path:
    return state_root() / "creative" / "songforge" / "feedback.jsonl"


def translate_atom(atom: dict[str, Any], cycle: dict[str, Any]) -> dict[str, Any]:
    return {
        "lyric_id": make_id("lyr"),
        "state": "LYRIC_TRANSLATION_CANDIDATE",
        "for_atom_id": atom["atom_id"],
        "for_chord_cycle_id": cycle["chord_cycle_id"],
        "syllable_budget": {
            "max_syllables": 28,
            "subdivision_options": ["1/8", "1/16", "triplet"],
            "human_speech_safe": True,
        },
        "phenomenological_images": atom.get("candidate_images", []),
        "lines": ["Jam mati di dapur, tapi kau tetap pagi", "wangiku tersangkut di lengan bajumu"],
        "direct_meaning_hidden": True,
        "review_required": True,
    }


def build_midi_spec(cycle: dict[str, Any]) -> dict[str, Any]:
    human = humanize_spec()
    return {
        "midi_spec_id": make_id("midi"),
        "state": "MIDI_SPEC_READY",
        "chord_cycle_id": cycle["chord_cycle_id"],
        "tempo": cycle["tempo"],
        "meter": cycle["meter"],
        "tracks": [
            {
                "name": "initial_piano_chords",
                "pattern": "broken_triplet",
                "velocity_base": human["velocity_base"],
                "velocity_variance": human["velocity_variance"],
                "humanize_ms": 22,
            },
            {"name": "bass_shadow", "pattern": "sustain_pulse", "velocity_base": 68},
        ],
        "humanize": human,
        "export": {"midi_file_allowed": True, "review_required": True},
    }


def build_song_skeleton(seed_text: str, *, dry_run: bool = True) -> dict[str, Any]:
    load_songforge_policy()
    parsed = persist_song_seed(seed_text, dry_run=dry_run)
    atom = parsed["atoms"][0]
    vector = derive_suffering_vector(atom["raw_meaning"])
    tension = derive_tension_targets(vector)
    cycle = generate_chord_cycle(atom["atom_id"], cadence=choose_cadence_route(tension))
    rhythms = generate_rhythm_variants()
    lyric = translate_atom(atom, cycle)
    midi = build_midi_spec(cycle)
    skeleton = {
        "song_skeleton_id": make_id("songskel"),
        "state": "SONG_SKELETON_CANDIDATE",
        "song_seed_id": parsed["seed"]["song_seed_id"],
        "context_anchors": parsed["seed"]["context_anchors"],
        "atom_count": len(parsed["atoms"]),
        "one_atom_max_chord_cycles": 1,
        "suffering_vector": vector,
        "chord_cycle_id": cycle["chord_cycle_id"],
        "rhythm_variant_count": len(rhythms),
        "lyric_id": lyric["lyric_id"],
        "midi_spec_id": midi["midi_spec_id"],
        "visual_inspo_query": "contemporary art domestic trace grief clothing absence e-flux",
        "vocal_chop_query": {"query": "licensed airy vocal one-shot intimate texture", "clearance_required": True},
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "review_required": True,
        "created_at": now_iso(),
    }
    if not dry_run:
        append_jsonl(chord_cycles_path(), cycle)
        for rhythm in rhythms:
            append_jsonl(rhythm_routes_path(), {**rhythm, "song_skeleton_id": skeleton["song_skeleton_id"]})
        append_jsonl(lyric_translations_path(), lyric)
        append_jsonl(midi_specs_path(), midi)
        append_jsonl(song_skeletons_path(), skeleton)
    return public_result(True, dry_run=dry_run, seed=parsed["seed"], atoms=parsed["atoms"], cycle=cycle, rhythms=rhythms, lyric=lyric, midi_spec=midi, skeleton=skeleton)


def chord_cycle_for_atom(atom_id: str) -> dict[str, Any]:
    atom = find_jsonl(parsed_song_atoms_path(), "atom_id", atom_id) or {"atom_id": atom_id, "raw_meaning": ""}
    vector = derive_suffering_vector(atom.get("raw_meaning", ""))
    cycle = generate_chord_cycle(atom_id, cadence=choose_cadence_route(derive_tension_targets(vector)))
    append_jsonl(chord_cycles_path(), cycle)
    return cycle


def record_song_feedback(song_id: str, decision: str, *, notes: str = "") -> dict[str, Any]:
    feedback = {
        "feedback_id": make_id("songfb"),
        "song_skeleton_id": song_id,
        "decision": decision,
        "signals": {
            "chord_worked": decision in {"promote_for_work", "needs_lyrics", "needs_vocal_chop"},
            "lyrics_worked": decision == "promote_for_work",
            "piano_motif_worked": True,
            "vocal_chop_needed": decision == "needs_vocal_chop",
            "suffering_vector_fit": 0.78,
        },
        "notes": notes,
        "updates": {"increase_weight": ["wounded_return"], "decrease_weight": ["explicit_existential_phrase"]},
        "created_at": now_iso(),
    }
    append_jsonl(feedback_path(), feedback)
    return {"ok": True, "feedback": feedback}
