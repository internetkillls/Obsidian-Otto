from __future__ import annotations

from pathlib import Path
from typing import Any

from ..creative.inspo import load_visual_inspo_policy
from ..creative.songforge import build_song_skeleton, load_songforge_policy
from ..creative.vocal_chop import load_vocal_chop_policy
from ..governance_utils import ensure_json, state_root
from ..memento.policy import load_memento_policy
from ..memento.scheduler_bridge import build_due_queue
from ..research.paper_onboarding import create_onboarding_pack, load_paper_onboarding_policy
from ..skills.blocker_map import skill_review


DEFAULT_CREATIVE_HEARTBEAT_POLICY: dict[str, Any] = {
    "version": 1,
    "runtime": "wsl_shadow",
    "mode": "proactive_review_gated",
    "safety": {
        "auto_publish": False,
        "auto_enable_telegram": False,
        "auto_download_youtube": False,
        "auto_write_public": False,
        "auto_qmd_index_raw": False,
    },
    "cadence": {
        "song_skeleton": {"every_hours": 4, "lab_mode_every_hours": 2, "max_per_day": 6},
        "paper_onboarding": {"every_hours_min": 4, "every_hours_max": 6, "max_per_day": 4},
        "blocker_experiment": {"every_hours": 24, "min_per_day": 1},
        "memento_due": {"every_hours": 8},
        "visual_inspo": {"trigger": "on_song_or_prose_candidate"},
    },
    "review_gates": {
        "song_skeleton_to_gold": "manual_promote",
        "paper_onboarding_to_gold": "manual_review",
        "memento_block_to_quiz": "reviewed_or_gold",
        "visual_inspo_to_vault": "reference_only_or_reviewed",
    },
}


DEFAULT_OTTO_SOUL_V2: dict[str, Any] = {
    "version": 2,
    "name": "Otto Creative Partner",
    "role": "partner_mentor_producer_research_companion",
    "not_roles": ["clinician", "diagnostician", "auto_publisher", "copyright_bypasser"],
    "core_mission": [
        "turn raw ideas into meaningful human artifacts",
        "help Joshua finish music, prose, research, and skill loops",
        "make memory durable through review, recall, and application",
        "convert suffering and meaning into form without over-explaining it",
    ],
    "daily_outputs": ["blocker experiment", "song skeleton", "paper onboarding pack", "memento quiz", "visual inspo query when relevant"],
    "style": {
        "creative": "phenomenological, precise, non-generic",
        "research": "onboarding before critique",
        "music": "chord-first, humane MIDI, singable lyrics",
        "mentor": "bounded experiment, concrete done signal",
    },
    "hard_boundaries": [
        "do not auto-publish",
        "do not index raw ideas into QMD",
        "do not rip YouTube audio",
        "do not write unreviewed profile/council claims to Vault",
        "do not treat AuDHD/BD as inferred diagnosis",
        "do not turn all memory into gold",
    ],
}


def creative_heartbeat_policy_path() -> Path:
    return state_root() / "schedules" / "creative_heartbeat_policy.json"


def heartbeat_manifest_path() -> Path:
    return state_root() / "openclaw" / "heartbeat" / "otto_heartbeat_manifest.json"


def soul_v2_path() -> Path:
    return state_root() / "openclaw" / "soul" / "otto_soul_v2.json"


def load_creative_heartbeat_policy() -> dict[str, Any]:
    return ensure_json(creative_heartbeat_policy_path(), DEFAULT_CREATIVE_HEARTBEAT_POLICY)


def load_otto_soul_v2() -> dict[str, Any]:
    return ensure_json(soul_v2_path(), DEFAULT_OTTO_SOUL_V2)


def write_heartbeat_manifest() -> dict[str, Any]:
    manifest = {
        "version": 1,
        "tools": [
            {"name": "otto.heartbeat", "command": "python3 -m otto.cli creative-heartbeat --dry-run", "risk": "candidate_generation"},
            {"name": "otto.song_skeleton_next", "command": "python3 -m otto.cli song-skeleton --dry-run", "risk": "candidate_generation"},
            {"name": "otto.paper_onboarding_next", "command": "python3 -m otto.cli paper-onboarding --dry-run", "risk": "web_research_candidate"},
            {"name": "otto.memento_due", "command": "python3 -m otto.cli memento-due", "risk": "read_write_private_state"},
            {"name": "otto.blocker_experiment_next", "command": "python3 -m otto.cli blocker-experiment --dry-run", "risk": "candidate_generation"},
            {"name": "otto.visual_inspo_query", "command": "python3 -m otto.cli visual-inspo-query --dry-run", "risk": "web_query_candidate"},
            {"name": "otto.feedback_ingest", "command": "python3 -m otto.cli feedback-ingest", "risk": "private_state_write"},
        ],
    }
    return ensure_json(heartbeat_manifest_path(), manifest)


def run_creative_heartbeat(*, dry_run: bool = True) -> dict[str, Any]:
    policy = load_creative_heartbeat_policy()
    load_songforge_policy()
    load_paper_onboarding_policy()
    load_memento_policy()
    load_visual_inspo_policy()
    vocal_policy = load_vocal_chop_policy()
    load_otto_soul_v2()
    manifest = write_heartbeat_manifest()
    song = build_song_skeleton("# Cinta Fana\n@ Penderitaan dan cinta tak kenal waktu.", dry_run=True)
    pack = create_onboarding_pack("HCI value-sensitive design and interface constraints", dry_run=True)
    blocker = skill_review(dry_run=True)
    memento = build_due_queue()
    return {
        "ok": True,
        "state": "AF2_MUSIC_RESEARCH_MEMENTO_HEARTBEAT_READY",
        "dry_run": dry_run,
        "song_skeleton": song["skeleton"],
        "paper_onboarding": pack["pack"],
        "blocker_experiment": blocker["tasks"][:1],
        "memento_due": memento,
        "heartbeat_manifest": manifest,
        "safety": policy["safety"],
        "youtube_download_blocked": vocal_policy["vocal_chop_policy"]["youtube_download_allowed"] is False,
        "auto_publish_blocked": policy["safety"]["auto_publish"] is False,
    }
