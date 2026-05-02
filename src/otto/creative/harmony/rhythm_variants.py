from __future__ import annotations


def generate_rhythm_variants() -> list[dict[str, str]]:
    names = ["sustain_pulse", "eighth_push", "syncopated_chop", "broken_triplet", "arp_up", "arp_down"]
    return [{"pattern": name, "feel": "humanized"} for name in names]
