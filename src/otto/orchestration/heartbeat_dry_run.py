from __future__ import annotations

from typing import Any

from ..creative.inspo import build_visual_inspo_query
from ..creative.songforge import build_song_skeleton
from ..memento.scheduler_bridge import build_due_queue
from ..research.paper_onboarding import create_onboarding_pack
from ..skills.blocker_map import skill_review
from .creative_heartbeat import run_creative_heartbeat


def run_heartbeat_dry_run_all() -> dict[str, Any]:
    song = build_song_skeleton("# Cinta Fana\n@ Penderitaan dan cinta tak kenal waktu.", dry_run=True)
    paper = create_onboarding_pack("HCI value-sensitive design and interface constraints", dry_run=True)
    memento = build_due_queue()
    blocker = skill_review(dry_run=True)
    visual = build_visual_inspo_query(song["skeleton"]["song_skeleton_id"])
    heartbeat = run_creative_heartbeat(dry_run=True)
    checks = {
        "song_skeleton": bool(song.get("ok") and song.get("skeleton")),
        "paper_onboarding": bool(paper.get("ok") and paper.get("pack")),
        "memento_due": bool(memento.get("ok") and "quiz_count" in memento),
        "blocker_experiment": bool(blocker.get("ok") and blocker.get("tasks")),
        "visual_inspo_query": bool(visual.get("ok") and visual.get("visual_query")),
        "creative_heartbeat": bool(heartbeat.get("ok")),
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "song_skeleton": song,
        "paper_onboarding": paper,
        "memento_due": memento,
        "blocker_experiment": blocker,
        "visual_inspo_query": visual,
        "creative_heartbeat": heartbeat,
    }

