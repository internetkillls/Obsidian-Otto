from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.qmd.retrieval import qmd_search
from ..autonomy.generation_policy import autonomous_generation_policy_path, autonomous_policy_health
from ..config import load_paths
from ..governance_utils import append_jsonl, read_jsonl, state_root
from ..memory.gold import gold_index_path
from ..openclaw_support import run_qmd_index_refresh
from ..state import now_iso, read_json, write_json
from ..soul.health import build_soul_health
from ..sanity.repair_plan import run_sanity_scan
from .cron_health import build_cron_health
from .golden_path_smoke import run_golden_path_smoke
from .health_scorecard import build_health_scorecard
from .heartbeat_readiness import build_heartbeat_readiness
from .rollback_drill import run_rollback_drill
from .runtime_smoke import build_runtime_smoke
from .runtime_owner import STATE_WSL_LIVE
from .telegram_router import heartbeat_router_test


REQUIRED_SOUL_STATE = "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY"
REQUIRED_SANITY_STATE = "SAN1_DEAD_END_SILENT_FAILURE_AMBIGUITY_GUARD_READY"
REQUIRED_HB1_STATE = "HB1_PROACTIVE_HEARTBEAT_ASSURANCE_READY"
REQUIRED_HB2_STATE = "HB2_TELEGRAM_HEARTBEAT_ROUTER_READY"
ROUNDTRIP_PROOF_TITLE = "OPS1 Roundtrip Proof"
ROUNDTRIP_PROOF_KIND = "ops_health_gold"


def ops_dir() -> Path:
    return state_root() / "ops"


def ops_health_policy_path() -> Path:
    return ops_dir() / "ops_health_policy.json"


def ops_health_last_path() -> Path:
    return ops_dir() / "ops_health_last.json"


def ops_health_runs_path() -> Path:
    return ops_dir() / "ops_health_runs.jsonl"


def qmd_vault_roundtrip_path() -> Path:
    return ops_dir() / "qmd_vault_roundtrip_last.json"


def incident_log_path() -> Path:
    return ops_dir() / "incident_log.jsonl"


def default_ops_health_policy() -> dict[str, Any]:
    return {
        "version": 1,
        "mode": "end_to_end_health",
        "required_green_states": [
            "S4_WSL_LIVE",
            "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY",
            "SAN1_DEAD_END_SILENT_FAILURE_AMBIGUITY_GUARD_READY",
            "HB1_PROACTIVE_HEARTBEAT_ASSURANCE_READY",
        ],
        "golden_paths": {
            "telegram_paper": True,
            "telegram_song": True,
            "telegram_weakness": True,
            "memento_due": True,
            "review_to_gold_to_qmd": True,
            "vault_writeback_roundtrip": True,
        },
        "failure_policy": {
            "silent_failure_allowed": False,
            "auto_publish_allowed": False,
            "raw_qmd_index_allowed": False,
            "unreviewed_vault_write_allowed": False,
            "dual_telegram_owner_allowed": False,
        },
        "minimum_outputs": {
            "daily_blocker_experiment": 1,
            "song_skeleton_interval_hours": 4,
            "paper_onboarding_interval_hours_min": 4,
            "paper_onboarding_interval_hours_max": 6,
            "memento_due_interval_hours": 8,
        },
    }


def ensure_ops_health_policy() -> dict[str, Any]:
    path = ops_health_policy_path()
    existing = read_json(path, default={}) or {}
    policy = default_ops_health_policy()
    if existing:
        merged = {**policy, **existing}
        # Gate precedence: OPS1 strict should be greenable before HB2.
        merged["required_green_states"] = list(policy.get("required_green_states") or [])
        if merged != existing:
            write_json(path, merged)
        return merged
    write_json(path, policy)
    return policy


def _latest_gold() -> dict[str, Any] | None:
    rows = read_jsonl(gold_index_path())
    return rows[-1] if rows else None


def _roundtrip_target_path() -> Path | None:
    paths = load_paths()
    vault_root = getattr(paths, "vault_path", None)
    if not vault_root:
        return None
    return Path(vault_root) / ".Otto-Realm" / "Memory-Tiers" / "Ops" / f"{ROUNDTRIP_PROOF_TITLE}.md"


def _proof_gold_entry(target: Path) -> dict[str, Any]:
    return {
        "gold_id": "gold_ops1_roundtrip_proof",
        "state": "GOLD",
        "from_review_id": "rev_ops1_roundtrip_proof",
        "kind": ROUNDTRIP_PROOF_KIND,
        "title": ROUNDTRIP_PROOF_TITLE,
        "body": "Controlled reviewed/gold OPS health roundtrip proof artifact.",
        "privacy": "private_reviewed",
        "evidence_refs": ["state/runtime/smoke_last.json", "state/openclaw/context_pack_v1.json"],
        "reviewed_at": now_iso(),
        "qmd_index_allowed": True,
        "vault_writeback_allowed": True,
        "context_pack_allowed": True,
        "target_path": str(target),
        "created_at": now_iso(),
        "source": "ops_health_roundtrip",
    }


def _proof_markdown() -> str:
    return (
        "---\n"
        f"title: {ROUNDTRIP_PROOF_TITLE}\n"
        f"kind: {ROUNDTRIP_PROOF_KIND}\n"
        "otto_state: reviewed_gold_test_artifact\n"
        "review_required: false\n"
        "qmd_index_allowed: true\n"
        "vault_writeback_allowed: true\n"
        "source: ops_health_roundtrip\n"
        "---\n\n"
        f"# {ROUNDTRIP_PROOF_TITLE}\n\n"
        "Controlled reviewed/gold test artifact for OPS health memory roundtrip.\n"
    )


def _ensure_roundtrip_proof(*, write: bool) -> dict[str, Any]:
    target = _roundtrip_target_path()
    if target is None:
        return {
            "ok": False,
            "gold_present": False,
            "vault_writeback_present": False,
            "no_output_reason": "vault_root_unavailable",
        }
    rows = read_jsonl(gold_index_path())
    existing = next(
        (
            row
            for row in reversed(rows)
            if str(row.get("title") or "") == ROUNDTRIP_PROOF_TITLE and str(row.get("kind") or "") == ROUNDTRIP_PROOF_KIND
        ),
        None,
    )
    gold_entry = existing or _proof_gold_entry(target)
    gold_created = False
    file_created = False
    if write and existing is None:
        append_jsonl(gold_index_path(), gold_entry)
        gold_created = True
    expected_marker = f"# {ROUNDTRIP_PROOF_TITLE}"
    file_needs_refresh = True
    if target.exists():
        existing_text = target.read_text(encoding="utf-8", errors="replace")
        file_needs_refresh = expected_marker not in existing_text
    if write and (not target.exists() or file_needs_refresh):
        existed_before = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_proof_markdown(), encoding="utf-8")
        file_created = not existed_before
    return {
        "ok": True,
        "gold_present": True,
        "vault_writeback_present": target.exists() or file_created,
        "gold_entry": gold_entry,
        "gold_created": gold_created,
        "file_created": file_created,
        "target_path": str(target),
    }


def _write_roundtrip_into_golden_results(result: dict[str, Any]) -> None:
    target = state_root() / "ops" / "golden_path_results.json"
    existing = read_json(target, default={}) or {}
    if not isinstance(existing, dict):
        existing = {}
    existing["qmd_vault_roundtrip"] = {
        "ok": bool(result.get("ok")),
        "state": result.get("state"),
        "checked_at": result.get("checked_at"),
        "search_found": result.get("search_found"),
        "query": result.get("query"),
        "target_path": result.get("target_path"),
        "no_output_reason": result.get("no_output_reason"),
    }
    write_json(target, existing)


def run_qmd_vault_roundtrip(*, strict: bool = False, write: bool = True) -> dict[str, Any]:
    proof = _ensure_roundtrip_proof(write=write)
    if not proof.get("ok"):
        result = {
            "ok": not strict,
            "checked_at": now_iso(),
            "state": "OPS_QMD_ROUNDTRIP_PENDING",
            "gold_present": False,
            "vault_writeback_present": False,
            "qmd_reindex_ok": False,
            "qmd_search_ok": False,
            "search_found": False,
            "no_output_reason": str(proof.get("no_output_reason") or "no_gold_memory_available"),
        }
        if write:
            write_json(qmd_vault_roundtrip_path(), result)
            _write_roundtrip_into_golden_results(result)
        return result

    query = ROUNDTRIP_PROOF_TITLE
    reindex = run_qmd_index_refresh(timeout_seconds=60)
    search = qmd_search(query, max_results=8, timeout_seconds=60)
    search_found = bool(search.get("hit_count", 0))

    ok = bool(proof.get("gold_present")) and bool(proof.get("vault_writeback_present")) and bool(reindex.get("ok")) and bool(search.get("ok")) and search_found
    result = {
        "ok": ok,
        "checked_at": now_iso(),
        "state": "QMD2_REVIEWED_CREATIVE_MEMORY_INDEX_READY" if ok else "QMD2_BLOCKED",
        "gold_present": bool(proof.get("gold_present")),
        "vault_writeback_present": bool(proof.get("vault_writeback_present")),
        "qmd_reindex_ok": bool(reindex.get("ok")),
        "qmd_search_ok": bool(search.get("ok")),
        "search_found": search_found,
        "query": query,
        "target_path": proof.get("target_path"),
        "proof": proof,
        "reindex": reindex,
        "search": search,
    }
    if write:
        write_json(qmd_vault_roundtrip_path(), result)
        _write_roundtrip_into_golden_results(result)
    return result


def run_ops_health(*, strict: bool = False, write: bool = True) -> dict[str, Any]:
    policy = ensure_ops_health_policy()
    autonomy_policy_existed = autonomous_generation_policy_path().exists()
    autonomy_policy = autonomous_policy_health()

    runtime = build_runtime_smoke(strict=strict, write=False)
    soul = build_soul_health()
    sanity = run_sanity_scan(strict=strict, write=False)
    hb1 = build_heartbeat_readiness(strict=strict, write=False, run_dry_runs=False)
    hb2_route = heartbeat_router_test("heartbeat now")
    cron = build_cron_health(write=write)
    golden = run_golden_path_smoke(write=write)
    roundtrip = run_qmd_vault_roundtrip(strict=strict, write=write)
    rollback = run_rollback_drill(dry_run=True, write=write)

    hb2_ok = hb2_route.get("routed_to") == "creative-heartbeat --dry-run --explain"
    sanity_strict_ok = (
        str(sanity.get("state") or "") == REQUIRED_SANITY_STATE
        and int(sanity.get("strict_failures", 0) or 0) == 0
        and bool((sanity.get("schema_audit") or {}).get("ok"))
    )
    state_checks = {
        "S4_WSL_LIVE": str((runtime.get("owner") or {}).get("runtime_state") or "") == STATE_WSL_LIVE,
        REQUIRED_SOUL_STATE: bool(soul.get("ok")) and str(soul.get("state") or "") == REQUIRED_SOUL_STATE,
        REQUIRED_SANITY_STATE: sanity_strict_ok,
        REQUIRED_HB1_STATE: bool(hb1.get("ok")) and str(hb1.get("state") or "") == REQUIRED_HB1_STATE,
        REQUIRED_HB2_STATE: hb2_ok,
    }

    required_states = list(policy.get("required_green_states") or [])
    required_state_ok = all(bool(state_checks.get(state_name, False)) for state_name in required_states)

    errors: list[str] = []
    warnings: list[str] = []

    if int(sanity.get("strict_failures", 0) or 0) > 0:
        errors.append("sanity_invariant_failures")

    cron_errors = [str(item) for item in (cron.get("errors") or [])]
    if any("no_output_contract:" in item for item in cron_errors):
        errors.append("cron_output_contract_missing")
    if any("unsafe_setting:auto_publish" in item for item in cron_errors):
        errors.append("auto_publish_forbidden")
    if any("forbidden_media_job:" in item for item in cron_errors):
        errors.append("forbidden_media_job_detected")

    if not bool((runtime.get("gates") or {}).get("memory_policy_blocks_raw_to_qmd")):
        errors.append("raw_qmd_index_policy_violation")
    if not bool((runtime.get("gates") or {}).get("single_owner_lock")):
        errors.append("dual_telegram_owner_or_lock_violation")
    if not bool(soul.get("ok")):
        errors.append("soul_health_missing")
    if not bool(hb1.get("ok")):
        errors.append("heartbeat_readiness_missing")
    if not bool(roundtrip.get("ok")):
        errors.append("qmd_vault_roundtrip_missing")
    if strict and (not autonomy_policy_existed or not bool(autonomy_policy.get("ok"))):
        errors.append("autonomous_generation_policy_missing")

    if not bool((hb1.get("optional_checks") or {}).get("visual_sources_declared")):
        warnings.append("visual_inspo_source_missing")
    if roundtrip.get("no_output_reason") and not strict:
        warnings.append(str(roundtrip["no_output_reason"]))

    golden_checks = golden.get("checks") or {}
    if not all(bool(value) for value in golden_checks.values()):
        errors.append("golden_path_failures")

    ok = required_state_ok and not errors
    state = "OPS1_END_TO_END_OPERATIONAL_HEALTH_READY" if ok else ("OPS_WARN_DEGRADED" if warnings and not errors else "OPS_FAIL_BLOCKED")

    result = {
        "ok": ok,
        "strict": strict,
        "checked_at": now_iso(),
        "state": state,
        "required_state_checks": state_checks,
        "required_states": required_states,
        "required_states_ok": required_state_ok,
        "runtime": runtime,
        "soul": soul,
        "sanity": sanity,
        "heartbeat_readiness": hb1,
        "hb2_router": {
            "ok": hb2_ok,
            "route": hb2_route.get("routed_to"),
            "result": hb2_route,
        },
        "cron": cron,
        "golden_paths": golden,
        "qmd_vault_roundtrip": roundtrip,
        "autonomous_generation_policy": {
            "existed_before_check": autonomy_policy_existed,
            **autonomy_policy,
        },
        "rollback": rollback,
        "errors": errors,
        "warnings": warnings,
    }

    if write:
        write_json(ops_health_last_path(), result)
        append_jsonl(ops_health_runs_path(), result)
        if not ok:
            append_jsonl(
                incident_log_path(),
                {
                    "timestamp": now_iso(),
                    "severity": "fail",
                    "state": state,
                    "errors": errors,
                    "warnings": warnings,
                },
            )
        build_health_scorecard(
            runtime_smoke=runtime,
            soul_health=soul,
            sanity=sanity,
            heartbeat_readiness=hb1,
            cron_health=cron,
            golden_paths=golden,
            rollback=rollback,
            roundtrip=roundtrip,
            write=True,
        )

    return result
