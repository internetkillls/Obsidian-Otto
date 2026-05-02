from __future__ import annotations


def humanize_spec() -> dict[str, float | int]:
    return {
        "timing_ms_min": 8,
        "timing_ms_max": 34,
        "velocity_base": 82,
        "velocity_variance": 14,
        "downbeat_accent_gain": 1.18,
        "ghost_note_probability": 0.08,
    }
