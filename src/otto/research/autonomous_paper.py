from __future__ import annotations

from pathlib import Path
from typing import Any

from ..autonomy.seed_selector import select_seed
from ..governance_utils import append_jsonl, make_id, state_root
from ..state import now_iso, write_json


def autonomous_paper_candidates_path() -> Path:
    return state_root() / "research" / "autonomous_paper_candidates.jsonl"


def _topic(seed: dict[str, Any]) -> str:
    anchors = [str(item) for item in seed.get("anchors", []) if item]
    if any(item in anchors for item in ["interface", "constraint"]):
        return "interface constraint as moral infrastructure"
    return f"{(anchors[0] if anchors else 'memory')} as creative and research infrastructure"


def build_autonomous_paper_candidate(*, dry_run: bool = True, seed: dict[str, Any] | None = None) -> dict[str, Any]:
    selected = {"ok": True, "seed": seed} if seed else select_seed("paper", write=not dry_run)
    if not selected.get("ok"):
        return {"ok": False, "dry_run": dry_run, "no_output_reason": selected.get("no_output_reason", "no_paper_seed_available")}
    seed = selected["seed"]
    topic = _topic(seed)
    candidate = {
        "paper_candidate_id": make_id("autopaper"),
        "state": "PAPER_ONBOARDING_CANDIDATE",
        "source": "autonomous_note_vector",
        "topic": topic,
        "onboarding_mode": True,
        "human_entry": {
            "who_are_these_people": "A research community around design, infrastructure, method, and human action.",
            "what_problem_are_they_living_inside": "How systems shape what people can notice, choose, remember, and become.",
            "what_is_obvious_to_them_but_not_to_me": "Interfaces are governance surfaces, not only presentation layers.",
            "what_jargon_should_i_survive_first": ["affordance", "constraint", "sociotechnical system", "infrastructure", "value-sensitive design"],
            "what_should_i_read_first": ["one university press book", "one top journal review", "one canonical debate"],
            "how_this_connects_to_my_work": "Use the seed as onboarding before critique, then connect it to Crack Research and Reversing Simon later.",
        },
        "source_scout_queries": [
            f"{topic} university press book",
            f"{topic} top journal review article",
            "Herbert Simon bounded rationality design interface critique",
        ],
        "derived_seed": {
            "anchors": seed.get("anchors", []),
            "existential_atoms": seed.get("existential_atoms", []),
            "evidence_refs": seed.get("evidence_refs", []),
        },
        "review_required": True,
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "auto_publish": False,
        "created_at": now_iso(),
    }
    if not dry_run:
        append_jsonl(autonomous_paper_candidates_path(), candidate)
        write_json(state_root() / "research" / "autonomous_paper_last.json", candidate)
    return {"ok": True, "dry_run": dry_run, "candidate": candidate, "seed": seed}

