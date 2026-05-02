from __future__ import annotations

from pathlib import Path
from typing import Any

from ..creative.autonomous_song import build_autonomous_song_candidate
from ..governance_utils import append_jsonl, state_root
from ..research.autonomous_paper import build_autonomous_paper_candidate
from ..state import now_iso, read_json, write_json
from . import AUTO2_STATE
from .autonomous_scheduler import next_due_autonomous_jobs
from .generation_policy import autonomous_policy_health, load_autonomous_generation_policy
from .note_vector import build_note_vector
from .steering_vector import steering_vector_health, write_steering_vector


def autonomous_generation_runs_path() -> Path:
    return state_root() / "autonomy" / "autonomous_generation_runs.jsonl"


def autonomous_generation_last_path() -> Path:
    return state_root() / "autonomy" / "autonomous_generation_last.json"


def generate_autonomous_candidate(kind: str, *, dry_run: bool = True) -> dict[str, Any]:
    if kind == "song":
        result = build_autonomous_song_candidate(dry_run=dry_run)
    elif kind == "paper":
        result = build_autonomous_paper_candidate(dry_run=dry_run)
    else:
        return {"ok": False, "kind": kind, "dry_run": dry_run, "no_output_reason": "unsupported_autonomous_kind"}
    payload = {
        "ok": bool(result.get("ok")),
        "state": AUTO2_STATE if result.get("ok") else "AUTO2_BLOCKED",
        "kind": kind,
        "dry_run": dry_run,
        "created_at": now_iso(),
        "review_required": True,
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "auto_publish": False,
        "result": result,
    }
    if not payload["ok"]:
        payload["no_output_reason"] = result.get("no_output_reason", "autonomous_generation_failed")
    if not dry_run:
        append_jsonl(autonomous_generation_runs_path(), payload)
        last = read_json(autonomous_generation_last_path(), default={}) or {}
        by_kind = last.get("by_kind") if isinstance(last, dict) else {}
        if not isinstance(by_kind, dict):
            by_kind = {}
        by_kind[kind] = payload
        write_json(autonomous_generation_last_path(), {"updated_at": now_iso(), "by_kind": by_kind, "last": payload})
    return payload


def run_autonomous_heartbeat(*, dry_run: bool = True) -> dict[str, Any]:
    policy = load_autonomous_generation_policy()
    steering = write_steering_vector()
    note = build_note_vector(write=not dry_run)
    due = next_due_autonomous_jobs()
    outputs: list[dict[str, Any]] = []
    for job in due.get("due", []):
        kind = str(job.get("kind") or "")
        if kind in {"song", "paper"}:
            outputs.append(generate_autonomous_candidate(kind, dry_run=dry_run))
    failed_reasons = [str(item.get("no_output_reason")) for item in outputs if not item.get("ok") and item.get("no_output_reason")]
    no_output_reason = None if any(item.get("ok") for item in outputs) else (
        ";".join(failed_reasons) if failed_reasons else "no_autonomous_jobs_due_or_no_seed_available"
    )
    ok = all(bool(item.get("ok")) for item in outputs) if outputs else True
    if failed_reasons and not any(item.get("ok") for item in outputs):
        ok = True
    result = {
        "ok": ok,
        "state": AUTO2_STATE if ok else "AUTO2_BLOCKED",
        "dry_run": dry_run,
        "policy": policy,
        "policy_health": autonomous_policy_health(),
        "steering_vector_health": steering_vector_health(steering.get("steering_vector")),
        "note_vector": note,
        "next_due_jobs": due,
        "outputs": outputs,
        "no_output_reason": no_output_reason,
        "review_required": True,
        "qmd_index_allowed": False,
        "vault_writeback_allowed": False,
        "auto_publish": False,
        "created_at": now_iso(),
    }
    if not dry_run:
        append_jsonl(autonomous_generation_runs_path(), result)
        write_json(autonomous_generation_last_path(), {"updated_at": now_iso(), "last": result})
    return result
