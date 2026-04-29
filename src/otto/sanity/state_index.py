from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_paths, repo_root
from ..governance_utils import read_jsonl, state_root
from ..state import now_iso, read_json, write_json
from .invariants import record_id, record_kind


PRIMARY_ID_FIELDS: dict[str, str] = {
    "candidate_memory": "candidate_id",
    "review_items": "review_id",
    "reviewed_items": "review_id",
    "rejected_items": "review_id",
    "gold_memory": "gold_id",
    "writeback_candidates": "writeback_id",
    "raw_records": "raw_id",
    "bronze_records": "bronze_id",
    "silver_events": "event_id",
    "idea_inbox": "idea_id",
    "artifact_routes": "route_id",
    "production_briefs": "brief_id",
    "release_candidates": "release_id",
    "song_seeds": "song_seed_id",
    "song_atoms": "atom_id",
    "song_skeletons": "song_skeleton_id",
    "song_feedback": "feedback_id",
    "paper_onboarding": "pack_id",
    "memento_blocks": "block_id",
    "memento_quizzes": "quiz_id",
    "action_queue": "action_id",
    "outcomes": "outcome_id",
    "reflections": "reflection_id",
    "council_statements": "statement_id",
    "selected_action": "action_id",
}

KNOWN_JSONL: dict[str, str] = {
    "candidate_memory": "memory/candidate_claims.jsonl",
    "review_items": "memory/review_queue.jsonl",
    "reviewed_items": "memory/reviewed.jsonl",
    "rejected_items": "memory/rejected.jsonl",
    "gold_memory": "memory/gold_index.jsonl",
    "writeback_candidates": "exports/obsidian/writeback_candidates.jsonl",
    "raw_records": "ingest/raw_index.jsonl",
    "bronze_records": "memory/bronze_index.jsonl",
    "silver_events": "memory/silver_events.jsonl",
    "idea_inbox": "artifacts/idea_inbox.jsonl",
    "artifact_routes": "artifacts/artifact_routes.jsonl",
    "production_briefs": "artifacts/production_briefs.jsonl",
    "release_candidates": "artifacts/release_candidates.jsonl",
    "song_seeds": "creative/songforge/raw_song_seeds.jsonl",
    "song_atoms": "creative/songforge/parsed_song_atoms.jsonl",
    "song_skeletons": "creative/songforge/song_skeletons.jsonl",
    "song_feedback": "creative/songforge/feedback.jsonl",
    "paper_onboarding": "research/onboarding_packs.jsonl",
    "memento_blocks": "memento/blocks.jsonl",
    "memento_quizzes": "memento/quiz_queue.jsonl",
    "action_queue": "human/action_queue.jsonl",
    "outcomes": "human/outcome_log.jsonl",
    "reflections": "human/reflection_log.jsonl",
    "council_statements": "council/council_statements.jsonl",
}

KNOWN_JSON: dict[str, str] = {
    "selected_action": "human/selected_action.json",
    "daily_loop_last": "runtime/daily_loop_last.json",
    "runtime_owner": "runtime/owner.json",
    "single_owner_lock": "runtime/single_owner_lock.json",
    "runtime_smoke": "runtime/smoke_last.json",
    "creative_heartbeat_policy": "schedules/creative_heartbeat_policy.json",
    "production_cron_policy": "schedules/production_cron_policy.json",
    "context_pack": "openclaw/context_pack_v1.json",
    "openclaw_tool_manifest": "openclaw/tool_manifest.json",
    "openclaw_gateway_probe": "openclaw/gateway_probe.json",
    "openclaw_cron_contract": "openclaw/cron_contract_v1.json",
    "openclaw_loop_state": "openclaw/loop_state.json",
    "openclaw_sync_status": "openclaw/sync_status.json",
    "openclaw_qmd_refresh_status": "openclaw/qmd_refresh_status.json",
    "openclaw_heartbeat_manifest": "openclaw/heartbeat/otto_heartbeat_manifest.json",
    "openclaw_soul_v2": "openclaw/soul/otto_soul_v2.json",
    "qmd_manifest": "qmd/qmd_manifest.json",
    "source_registry": "memory/source_registry.json",
}

REPO_CONFIG_FILES: dict[str, str] = {
    "native_openclaw_config": ".openclaw/openclaw.json",
    "openclaw_shadow_config": "state/openclaw/ubuntu-shadow/openclaw.json",
    "routing_config": "config/routing.yaml",
    "kernelization_config": "config/kernelization.yaml",
    "paths_config": "config/paths.yaml",
    "retrieval_config": "config/retrieval.yaml",
    "heartbeat_telemetry_config": "config/heartbeat_telemetry.yaml",
}


def state_index_path() -> Path:
    return state_root() / "sanity" / "state_index.json"


def _file_rel(path: Path) -> str:
    try:
        return f"state/{path.relative_to(state_root()).as_posix()}"
    except ValueError:
        try:
            return path.relative_to(repo_root()).as_posix()
        except ValueError:
            return str(path)


def primary_record_id(record_type: str, record: dict[str, Any]) -> str | None:
    field = PRIMARY_ID_FIELDS.get(record_type)
    if field:
        value = record.get(field)
        if value:
            return str(value)
    return record_id(record)


def iter_indexed_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    root = state_root()
    for record_type, rel in KNOWN_JSONL.items():
        path = root / rel
        for row_number, item in enumerate(read_jsonl(path), start=1):
            records.append(
                {
                    "record_type": record_type,
                    "file": _file_rel(path),
                    "row": row_number,
                    "id": primary_record_id(record_type, item),
                    "kind": record_kind(item, fallback=record_type),
                    "state": item.get("state"),
                    "record": item,
                }
            )
    for record_type, rel in KNOWN_JSON.items():
        path = root / rel
        item = read_json(path, default=None)
        if isinstance(item, dict) and item:
            records.append(
                {
                    "record_type": record_type,
                    "file": _file_rel(path),
                    "row": None,
                    "id": primary_record_id(record_type, item),
                    "kind": record_kind(item, fallback=record_type),
                    "state": item.get("state"),
                    "record": item,
                }
            )
    repo = repo_root()
    for record_type, rel in REPO_CONFIG_FILES.items():
        path = repo / rel
        if path.exists():
            stat = path.stat()
            records.append(
                {
                    "record_type": record_type,
                    "file": _file_rel(path),
                    "row": None,
                    "id": record_type,
                    "kind": "config_file",
                    "state": "CONFIG_PRESENT",
                    "record": {
                        "id": record_type,
                        "state": "CONFIG_PRESENT",
                        "kind": "config_file",
                        "path": _file_rel(path),
                        "size_bytes": stat.st_size,
                        "modified_at": now_iso(),
                    },
                }
            )
    return records


def build_state_index(*, write: bool = True) -> dict[str, Any]:
    records = iter_indexed_records()
    grouped: dict[str, dict[str, Any]] = {}
    for item in records:
        bucket = grouped.setdefault(item["record_type"], {"count": 0, "files": set()})
        bucket["count"] += 1
        bucket["files"].add(item["file"])
    serializable = {
        name: {"count": value["count"], "files": sorted(value["files"])}
        for name, value in sorted(grouped.items())
    }
    owner = read_json(state_root() / "runtime" / "single_owner_lock.json", default={}) or {}
    runtime_owner = read_json(state_root() / "runtime" / "owner.json", default={}) or {}
    index = {
        "version": 1,
        "generated_at": now_iso(),
        "records": serializable,
        "owners": {
            "telegram": (owner.get("telegram_enabled_owners") or ["windows_openclaw"])[0]
            if isinstance(owner.get("telegram_enabled_owners"), list)
            else "windows_openclaw",
            "telegram_enabled_owners": owner.get("telegram_enabled_owners", []),
            "windows_openclaw": (runtime_owner.get("windows_openclaw") or {}).get("role"),
            "ubuntu_openclaw": (runtime_owner.get("ubuntu_openclaw") or {}).get("role"),
            "gateway_shadow": "ubuntu_openclaw",
            "qmd": (runtime_owner.get("qmd") or {}).get("owner") or "ubuntu_wsl",
        },
        "record_total": len(records),
    }
    if write:
        write_json(state_index_path(), index)
    return index


def records_by_id() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in iter_indexed_records():
        if item.get("id"):
            grouped.setdefault(str(item["id"]), []).append(item)
    return grouped
