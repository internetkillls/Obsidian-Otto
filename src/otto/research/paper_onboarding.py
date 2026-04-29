from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, ensure_json, make_id, state_root
from ..state import now_iso


DEFAULT_PAPER_ONBOARDING_POLICY: dict[str, Any] = {
    "version": 1,
    "paper_onboarding_policy": {
        "cadence_hours_min": 4,
        "cadence_hours_max": 6,
        "mode_default": "onboarding_before_critique",
        "source_priority": [
            "university_press_books",
            "top_journal_articles",
            "field_handbooks",
            "canonical_debates",
            "recent_review_articles",
            "lectures_or_syllabi_from_universities",
        ],
        "onboarding_pack_must_include": [
            "who_are_these_people",
            "what_problem_are_they_living_inside",
            "what_counts_as_status_or_credibility",
            "what_jargon_should_i_survive_first",
            "what_historical_wound_or_argument_started_this",
            "what_is_trivial_to_them_but_not_to_me",
            "what_should_i_read_first",
            "how_this_connects_to_my_work",
        ],
        "critical_mode_style": "crack_research_reversing_simon",
        "auto_vault_write": False,
        "auto_qmd_index": False,
        "review_required_before_gold": True,
    },
}


def paper_onboarding_policy_path() -> Path:
    return state_root() / "research" / "paper_onboarding_policy.json"


def onboarding_packs_path() -> Path:
    return state_root() / "research" / "onboarding_packs.jsonl"


def load_paper_onboarding_policy() -> dict[str, Any]:
    return ensure_json(paper_onboarding_policy_path(), DEFAULT_PAPER_ONBOARDING_POLICY)


def create_onboarding_pack(topic: str, *, dry_run: bool = True) -> dict[str, Any]:
    policy = load_paper_onboarding_policy()["paper_onboarding_policy"]
    pack = {
        "pack_id": make_id("paper_onboard"),
        "state": "ONBOARDING_PACK_CANDIDATE",
        "topic": topic,
        "mode": policy["mode_default"],
        "human_entry": {
            "who_are_they": "A research community organized around a shared problem.",
            "what_problem_are_they_living_inside": "How interface, constraint, and mechanism shape human action.",
            "what_counts_as_status_or_credibility": "Canonical debates, careful definitions, and reproducible probes.",
            "what_jargon_should_i_survive_first": ["interface", "constraint", "mechanism", "retroduction"],
            "what_historical_wound_or_argument_started_this": "A gap between public interface and hidden mechanism.",
            "what_is_trivial_to_them_but_not_to_me": "Their background assumptions about method and evidence.",
            "what_should_i_read_first": ["one university press book", "one review article", "one recent debate"],
            "how_this_connects_to_my_work": "Use onboarding before critique, then crack open interface-mechanism deltas.",
        },
        "sources_needed": ["university press book", "top journal review", "recent debate"],
        "next_question": "Where does interface become moral infrastructure?",
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "review_required": True,
        "created_at": now_iso(),
    }
    if not dry_run:
        append_jsonl(onboarding_packs_path(), pack)
    return {"ok": True, "dry_run": dry_run, "pack": pack}
