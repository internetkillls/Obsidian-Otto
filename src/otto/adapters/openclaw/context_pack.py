from __future__ import annotations

from pathlib import Path
from typing import Any

from ...adapters.qmd.manifest import qmd_manifest_health
from ...artifacts.artifact_router import artifact_routes_path
from ...autonomy.autonomous_scheduler import next_due_autonomous_jobs
from ...autonomy.generation_policy import autonomous_policy_health
from ...autonomy.note_vector import load_note_vectors
from ...autonomy.steering_vector import steering_vector_health
from ...creative.songforge import song_skeletons_path
from ...governance_utils import count_jsonl, read_jsonl
from ...memory.gold import gold_counts
from ...memory.promotion import candidate_claims_path
from ...memory.review_queue import review_counts
from ...memory.source_registry import validate_source_registry
from ...openclaw_support import build_qmd_index_health
from ...orchestration.runtime_owner import build_runtime_owner, build_single_owner_lock
from ...profile.profile_policy import profile_policy_health
from ...sanity.repair_plan import sanity_summary
from ...state import now_iso, read_json, write_json
from ...soul.health import build_soul_health
from ...orchestration.telegram_router import next_due_jobs
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
    soul = build_soul_health()
    soul_root_audit = soul.get("root_audit") or {}
    readiness = read_json(context_pack_path().parents[1] / "schedules" / "heartbeat_readiness.json", default={}) or {}
    due_jobs = next_due_jobs()
    autonomy_due_jobs = next_due_autonomous_jobs()
    autonomy_policy = autonomous_policy_health()
    note_vectors = load_note_vectors()
    steering_health = steering_vector_health()
    song_rows = read_jsonl(song_skeletons_path())
    auto_song_rows = read_jsonl(context_pack_path().parents[1] / "creative" / "songforge" / "autonomous_song_candidates.jsonl")
    auto_paper_rows = read_jsonl(context_pack_path().parents[1] / "research" / "autonomous_paper_candidates.jsonl")
    paper_rows = read_jsonl(context_pack_path().parents[1] / "research" / "onboarding_packs.jsonl")
    blocker_rows = read_jsonl(context_pack_path().parents[1] / "skills" / "training_tasks.jsonl")
    memento_rows = read_jsonl(context_pack_path().parents[1] / "memento" / "quiz_queue.jsonl")
    last_song = song_rows[-1] if song_rows else {}
    last_paper = paper_rows[-1] if paper_rows else {}
    last_blocker = blocker_rows[-1] if blocker_rows else {}
    qmd_chunks = None
    if isinstance(qmd_index, dict):
        qmd_chunks = qmd_index.get("indexed_chunks") or None

    state = "CP6_CREATIVE_ACTION_AWARE" if qmd_index.get("ok") and manifest.get("ok") else "CP1_STATIC_GENERATED"
    telegram_state = "unsafe_or_unknown"
    if bool(single_owner.get("ubuntu_shadow_telegram_disabled")) or bool(single_owner.get("telegram_single_owner")):
        telegram_state = "disabled"
    if bool(single_owner.get("ok")) and (owner.get("runtime_state") or "").startswith("S4"):
        telegram_state = "single_owner_ok"
    return {
        "version": CONTEXT_PACK_VERSION,
        "state": state,
        "generated_at": now_iso(),
        "task": task,
        "runtime": {
            "state": owner.get("runtime_state"),
            "qmd": "green" if qmd_index.get("ok") else "red",
            "openclaw_shadow": "gateway_ready" if gateway_probe.get("ok") else "memory_ready",
            "telegram": telegram_state,
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
        "creative_heartbeat_summary": {
            "state": "AF2_MUSIC_RESEARCH_MEMENTO_HEARTBEAT_READY",
            "heartbeat_readiness_state": readiness.get("state"),
            "heartbeat_readiness_ok": bool(readiness.get("ok")),
            "next_due_jobs": due_jobs.get("due_jobs", []),
            "song_skeleton_candidates": song_count,
            "last_song_skeleton_candidate": {
                "id": last_song.get("song_skeleton_id"),
                "created_at": last_song.get("created_at"),
                "review_required": last_song.get("review_required"),
            },
            "last_paper_onboarding_candidate": {
                "id": last_paper.get("pack_id"),
                "created_at": last_paper.get("created_at"),
                "review_required": last_paper.get("review_required"),
            },
            "blocker_experiment_status": {
                "last_training_task_id": last_blocker.get("training_task_id"),
                "created_at": last_blocker.get("created_at"),
            },
            "memento_due_count": len(memento_rows),
            "artifact_routes": route_count,
            "review_gated": True,
            "auto_publish": False,
            "auto_qmd_index_raw": False,
            "auto_vault_write_unreviewed": False,
            "auto_download_youtube": False,
            "soul_identity_heartbeat_health": {
                "soul_ok": bool(soul.get("ok")),
                "profile_snapshot": "present" if soul["checks"].get("profile_snapshot_exists") else "missing",
                "heartbeats": "present" if soul["checks"].get("heartbeats_dir_exists") else "missing",
            },
            "do_not_do_yet": [
                "auto_publish",
                "raw_qmd_indexing",
                "unreviewed_vault_write",
                "youtube_download_or_rip",
                "diagnostic_psychometric_claims",
            ],
        },
        "autonomy": {
            "state": "AUTO2_VECTOR_STEERED_CREATIVE_AUTONOMY_READY" if autonomy_policy.get("ok") else "AUTO2_BLOCKED",
            "policy_ok": bool(autonomy_policy.get("ok")),
            "steering_vector_loaded": bool(steering_health.get("ok")),
            "note_vectors_count": len(note_vectors),
            "next_due_jobs": autonomy_due_jobs.get("due", []),
            "last_autonomous_song_candidate": auto_song_rows[-1] if auto_song_rows else None,
            "last_autonomous_paper_candidate": auto_paper_rows[-1] if auto_paper_rows else None,
            "review_required": True,
            "qmd_index_allowed": False,
            "vault_writeback_allowed": False,
            "auto_publish": False,
        },
        "soul": {
            "state": soul.get("state"),
            "manifest_path": str(context_pack_path().parents[1] / "soul" / "soul_manifest.json"),
            "profile_snapshot": "present" if soul["checks"].get("profile_snapshot_exists") else "missing",
            "heartbeats": "present" if soul["checks"].get("heartbeats_dir_exists") else "missing",
            "brain": "present" if soul["checks"].get("brain_dir_exists") else "missing",
            "qmd_soul_retrievable": bool((soul.get("qmd_soul_audit") or {}).get("ok")),
            "qmd_retrievable": bool((soul.get("qmd_soul_audit") or {}).get("ok")),
            "wrong_root_warning": {
                "legacy_wrong_root_exists": bool(soul_root_audit.get("legacy_wrong_root_exists")),
                "legacy_wrong_root": soul_root_audit.get("legacy_wrong_root"),
                "wrong_root_candidates": soul_root_audit.get("wrong_root_candidates", []),
                "non_destructive": True,
            },
            "identity_boundary": "summary_only_no_raw_vault_dump",
            "heartbeat_contract": {
                "router_policy": "heartbeat tools route first; no generic no_action loop",
                "review_gate": "all generated creative/research outputs remain candidates until review",
                "source_scope": "canonical .Otto-Realm + control plane identity only",
            },
            "heartbeat_retrieval_order": [
                "tasks/active",
                "state/handoff/latest.json",
                "state/checkpoints/pipeline.json",
                "artifacts/summaries/gold_summary.json",
                "artifacts/reports/kairos_daily_strategy.md",
                "artifacts/reports/dream_summary.md",
                "artifacts/reports/otto_profile.md",
                ".Otto-Realm scoped canonical paths",
            ],
            "health_ok": bool(soul.get("ok")),
            "warnings": soul.get("warnings", []),
            "failures": soul.get("failures", []),
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
