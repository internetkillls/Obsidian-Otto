from __future__ import annotations

from pathlib import Path
from typing import Any

from ...adapters.qmd.manifest import qmd_manifest_health
from ...artifacts.artifact_router import artifact_routes_path
from ...creative.songforge import song_skeletons_path
from ...governance_utils import count_jsonl
from ...memory.gold import gold_counts
from ...memory.promotion import candidate_claims_path
from ...memory.review_queue import review_counts
from ...memory.source_registry import validate_source_registry
from ...openclaw_support import build_qmd_index_health
from ...orchestration.runtime_owner import build_runtime_owner, build_single_owner_lock
from ...profile.profile_policy import profile_policy_health
from ...sanity.repair_plan import sanity_summary
from ...state import now_iso, read_json, write_json
from .tool_payloads import build_openclaw_tool_manifest


CONTEXT_PACK_VERSION = 1


def context_pack_path() -> Path:
    from ...config import load_paths

    return load_paths().state_root / "openclaw" / "context_pack_v1.json"


def build_openclaw_context_pack(*, task: str | None = None) -> dict[str, Any]:
    owner = build_runtime_owner()
    qmd_index = build_qmd_index_health()
    manifest = qmd_manifest_health()
    registry = validate_source_registry()
    single_owner = build_single_owner_lock()
    gateway_probe = read_json(context_pack_path().parent / "gateway_probe.json", default={}) or {}
    tool_manifest = build_openclaw_tool_manifest()
    review = review_counts()
    gold = gold_counts()
    profile = profile_policy_health()
    daily_handoff = read_json(context_pack_path().parents[1] / "human" / "daily_handoff.json", default={}) or {}
    reflection_count = count_jsonl(context_pack_path().parents[1] / "human" / "reflection_log.jsonl")
    route_count = count_jsonl(artifact_routes_path())
    song_count = count_jsonl(song_skeletons_path())
    sanity = sanity_summary()
    qmd_chunks = None
    if isinstance(qmd_index, dict):
        qmd_chunks = qmd_index.get("indexed_chunks") or None

    state = "CP6_CREATIVE_ACTION_AWARE" if qmd_index.get("ok") and manifest.get("ok") else "CP1_STATIC_GENERATED"
    return {
        "version": CONTEXT_PACK_VERSION,
        "state": state,
        "generated_at": now_iso(),
        "task": task,
        "runtime": {
            "state": owner.get("runtime_state"),
            "qmd": "green" if qmd_index.get("ok") else "red",
            "openclaw_shadow": "gateway_ready" if gateway_probe.get("ok") else "memory_ready",
            "telegram": "single_owner_ok" if single_owner.get("telegram_single_owner") else "unsafe_or_unknown",
        },
        "memory": {
            "source_registry_ok": bool(registry.get("ok")),
            "qmd_manifest_ok": bool(manifest.get("ok")),
            "qmd_index_ok": bool(qmd_index.get("ok")),
            "qmd_source_count": qmd_index.get("source_count"),
            "qmd_chunks": qmd_chunks,
        },
        "memory_spine": {
            "raw_count": count_jsonl(context_pack_path().parents[1] / "ingest" / "raw_index.jsonl"),
            "silver_event_count": count_jsonl(context_pack_path().parents[1] / "memory" / "silver_events.jsonl"),
            "candidate_count": count_jsonl(candidate_claims_path()),
            "review_required_count": review["pending_review_count"],
            "gold_count": gold["gold_count"],
        },
        "memory_review": {
            **review,
            "gold_count": gold["gold_count"],
        },
        "profile_council": {
            "profile_policy": profile["profile_policy"],
            "diagnostic_inference_allowed": False,
            "unreviewed_profile_claims_exposed": False,
            "council_policy": "green",
        },
        "human_loop": {
            "state": "HL2_OUTCOME_REFLECTION_LOOP_READY" if reflection_count else "HL1_DAILY_HANDOFF_READY",
            "daily_handoff_available": bool(daily_handoff),
            "suggested_action_count": 1 if daily_handoff.get("smallest_meaningful_next_action") else 0,
            "selected_action": None,
            "latest_outcome": None,
            "reflection_candidate_count": reflection_count,
            "pending_reflection_review_count": reflection_count,
        },
        "partner_mode": {
            "role": "partner_mentor",
            "not_roles": ["clinician", "diagnostician"],
            "support_context_enabled": True,
            "diagnostic_inference_allowed": False,
        },
        "creative_forge": {
            "state": "AF2_MUSIC_RESEARCH_MEMENTO_HEARTBEAT_READY",
            "artifact_route_count": route_count,
            "song_skeleton_candidate_count": song_count,
            "raw_idea_content_in_context": False,
        },
        "sanity": sanity,
        "recommended_next_action": {
            "title": "Run creative-human heartbeat dry-run",
            "scope": "one bounded candidate generation pass",
            "done_signal": "song skeleton, paper onboarding, memento due, and blocker experiment are candidates only",
        },
        "do_not_do_yet": [
            "Instagram production ingest",
            "dual Telegram ownership",
            "prediction model training",
            "Vault write of unreviewed profile/council claims",
            "Auto-publication",
        ],
        "do_not_use": [
            "quarantined records",
            "unreviewed profile/council claims",
            "candidate items with unresolved ambiguity",
        ],
        "safety": {
            "single_owner_ok": bool(single_owner.get("ok")),
            "raw_social_to_qmd_allowed": False,
            "raw_social_to_vault_allowed": False,
            "candidate_content_in_context": False,
            "gold_content_in_context": True,
            "raw_content_in_context": False,
        },
        "constraints": [
            "Do not allow Windows and Ubuntu to both own Telegram.",
            "Do not write raw social data to QMD.",
            "Do not write raw social data to Obsidian.",
            "Profile claims must be evidence-linked and reviewed before durable memory.",
            "OpenClaw shadow tools are read-only until canary approval.",
        ],
        "available_tools": [tool["name"] for tool in tool_manifest["tools"]],
        "gateway_probe": {
            "ok": bool(gateway_probe.get("ok")),
            "port": gateway_probe.get("port"),
            "reason": gateway_probe.get("reason"),
        },
    }


def write_openclaw_context_pack(path: Path | None = None, *, task: str | None = None) -> dict[str, Any]:
    pack = build_openclaw_context_pack(task=task)
    target = path or context_pack_path()
    write_json(target, pack)
    return {"ok": True, "path": str(target), "context_pack": pack}
