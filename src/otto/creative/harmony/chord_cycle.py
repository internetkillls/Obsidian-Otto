from __future__ import annotations

from typing import Any

from ...governance_utils import make_id


def generate_chord_cycle(atom_id: str, *, cadence: str = "wounded_return") -> dict[str, Any]:
    return {
        "chord_cycle_id": make_id("cycle"),
        "state": "CHORD_CYCLE_CANDIDATE",
        "for_atom_id": atom_id,
        "key_center": "D",
        "mode": "dorian",
        "tempo": 82,
        "meter": "4/4",
        "bars": 4,
        "max_chord_cycles_for_atom": 1,
        "chords": [
            {"symbol": "Dm9", "role": "i", "duration_beats": 4, "tension": 0.42},
            {"symbol": "G13", "role": "IV13", "duration_beats": 4, "tension": 0.68},
            {"symbol": "Cmaj7", "role": "bVIImaj7", "duration_beats": 4, "tension": 0.50},
            {"symbol": "A7b9", "role": "V/i", "duration_beats": 4, "tension": 0.81},
        ],
        "cadence": cadence,
        "voice_leading_target": "smooth_with_one_sting",
    }
