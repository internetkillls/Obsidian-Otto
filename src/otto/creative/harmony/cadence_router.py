from __future__ import annotations


def choose_cadence_route(tension: dict[str, float]) -> str:
    if tension.get("chromatic_pressure", 0.0) > 0.5:
        return "wounded_return"
    return "soft_open_loop"
