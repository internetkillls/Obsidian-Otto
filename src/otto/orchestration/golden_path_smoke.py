from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.openclaw.context_pack import build_openclaw_context_pack
from ..governance_utils import state_root
from ..state import now_iso, write_json
from .telegram_router import heartbeat_router_test


def golden_path_results_path() -> Path:
    return state_root() / "ops" / "golden_path_results.json"


def run_golden_path_smoke(*, write: bool = True) -> dict[str, Any]:
    paper = heartbeat_router_test("paper now")
    song = heartbeat_router_test("bikin lagu dari # Cinta Fana @ Penderitaan dan cinta tak kenal waktu")
    weakness = heartbeat_router_test("cari weakness point saya")
    memento = heartbeat_router_test("memento")
    heartbeat = heartbeat_router_test("heartbeat now")
    context_pack = build_openclaw_context_pack(task="ops-golden-path")

    checks = {
        "telegram_paper_route": paper.get("routed_to") == "paper-onboarding --force-candidate",
        "telegram_song_route": song.get("routed_to") == "song-skeleton --dry-run",
        "telegram_weakness_route": weakness.get("routed_to") == "blocker-experiment --dry-run",
        "telegram_weakness_non_diagnostic": "support_context_only_non_diagnostic_for_audhd_bd" in (weakness.get("warnings") or []),
        "memento_route": memento.get("routed_to") == "memento-due",
        "memento_output_contract": bool(memento.get("actual_outputs")) or bool(memento.get("no_output_reason")),
        "heartbeat_route": heartbeat.get("routed_to") == "creative-heartbeat --dry-run --explain",
        "context_pack_has_soul": bool(context_pack.get("soul")),
        "context_pack_has_creative_summary": bool(context_pack.get("creative_heartbeat_summary")),
        "context_pack_no_raw_candidate_dump": not bool(context_pack.get("raw_candidates")),
    }

    ok = all(checks.values())
    result = {
        "ok": ok,
        "checked_at": now_iso(),
        "state": "OPS1_GOLDEN_PATH_TESTS_READY" if ok else "OPS1_GOLDEN_PATH_BLOCKED",
        "checks": checks,
        "routes": {
            "paper": paper,
            "song": song,
            "weakness": weakness,
            "memento": memento,
            "heartbeat": heartbeat,
        },
    }
    if write:
        write_json(golden_path_results_path(), result)
    return result


def run_telegram_e2e_smoke(*, write: bool = True) -> dict[str, Any]:
    return run_golden_path_smoke(write=write)
