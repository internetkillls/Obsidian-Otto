from __future__ import annotations


def derive_tension_targets(vector: dict[str, float]) -> dict[str, float]:
    return {
        "tonic_gravity": 0.64,
        "modal_borrowing": min(0.9, 0.35 + vector.get("longing", 0.0) * 0.4),
        "secondary_dominant_pull": 0.58,
        "chromatic_pressure": min(0.95, 0.25 + vector.get("resentment", 0.0) * 0.5),
        "extension_density": 0.72,
        "voice_leading_smoothness": 0.81,
        "cadence_closure": 0.44,
        "tonnetz_distance": 0.37,
    }
