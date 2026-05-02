from __future__ import annotations


def build_task_shape(gold: dict[str, object]) -> tuple[str, dict[str, object]]:
    kind = str(gold.get("kind") or "")
    if kind == "research_onboarding_principle":
        return (
            "research_onboarding_style",
            {
                "expected_structure": [
                    "who_are_these_people",
                    "what_problem_are_they_living_inside",
                    "jargon_to_survive",
                    "how_this_connects_to_user",
                ]
            },
        )
    return (
        "artifact_routing",
        {
            "expected_structure": [
                "core_signal",
                "artifact_route",
                "why_it_matters",
                "next_action",
            ]
        },
    )
