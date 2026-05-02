from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters.qmd.manifest import build_qmd_manifest, qmd_manifest_health
from ..governance_utils import state_root
from ..openclaw_support import build_qmd_index_health
from ..state import now_iso, write_json
from .manifest import build_soul_manifest, soul_manifest_path
from .paths import build_root_audit, to_host_path


def soul_health_path() -> Path:
    return state_root() / "soul" / "soul_health.json"


def _find_entry(entries: list[dict[str, Any]], rel: str) -> dict[str, Any] | None:
    for entry in entries:
        if str(entry.get("relative_path")) == rel:
            return entry
    return None


def build_qmd_soul_audit() -> dict[str, Any]:
    manifest = build_qmd_manifest()
    health = qmd_manifest_health(manifest)
    index_health = build_qmd_index_health()
    ids = {str(item.get("id")) for item in manifest.get("sources", []) if isinstance(item, dict)}
    checks = {
        "profile_snapshot_source_present": "otto_realm_identity" in ids,
        "heartbeats_source_present": "otto_realm_identity" in ids,
        "soul_or_identity_source_present": "otto_control_plane_identity" in ids,
        "kairos_daily_strategy_source_present": "otto_control_plane_identity" in ids,
        "dream_summary_source_present": "otto_control_plane_identity" in ids,
        "qmd_manifest_ok": bool(health.get("ok")),
        "qmd_index_ok": bool(index_health.get("ok")),
    }
    return {
        "ok": all(checks.values()),
        "checked_at": now_iso(),
        "checks": checks,
        "manifest_source_count": manifest.get("source_count"),
        "qmd_index_source_count": index_health.get("source_count"),
    }


def build_soul_health() -> dict[str, Any]:
    manifest = build_soul_manifest()
    repo_root_wsl = str((manifest.get("repo_root") or {}).get("wsl") or "")
    vault_root_wsl = str((manifest.get("vault_root") or {}).get("wsl") or "")
    soul_root_wsl = str((manifest.get("soul_root") or {}).get("wsl") or "")
    control_plane = manifest.get("control_plane") or []
    vault_identity = manifest.get("vault_identity") or []
    root_docs = manifest.get("root_control_docs") or []
    root_audit = manifest.get("root_audit") or build_root_audit()

    profile_snapshot = _find_entry(vault_identity, ".Otto-Realm/Profile Snapshot.md")
    heartbeats_dir = _find_entry(vault_identity, ".Otto-Realm/Heartbeats")
    brain_dir = _find_entry(vault_identity, ".Otto-Realm/Brain")

    failures: list[str] = []
    warnings: list[str] = []

    if not profile_snapshot or not profile_snapshot.get("exists"):
        failures.append("profile_snapshot_missing")
    if not heartbeats_dir or not heartbeats_dir.get("exists"):
        failures.append("heartbeats_dir_missing")
    if not brain_dir or not brain_dir.get("exists"):
        warnings.append("brain_dir_missing")

    for doc in root_docs:
        if not doc.get("exists"):
            warnings.append(f"optional_root_doc_missing:{doc.get('relative_path')}")

    qmd_audit = build_qmd_soul_audit()
    if not qmd_audit.get("ok"):
        warnings.append("qmd_soul_audit_not_green")
    if bool(root_audit.get("legacy_wrong_root_exists")):
        warnings.append("legacy_wrong_root_detected")

    checks = {
        "soul_manifest_exists": soul_manifest_path().exists(),
        "repo_root_wsl_exists": bool(repo_root_wsl and to_host_path(repo_root_wsl).exists()),
        "vault_root_wsl_exists": bool(vault_root_wsl and to_host_path(vault_root_wsl).exists()),
        "otto_realm_exists": bool(soul_root_wsl and to_host_path(soul_root_wsl).exists()),
        "canonical_soul_root_exists": bool((root_audit.get("canonical_soul_root") or {}).get("exists")),
        "legacy_wrong_root_exists": bool(root_audit.get("legacy_wrong_root_exists")),
        "profile_snapshot_exists": bool(profile_snapshot and profile_snapshot.get("exists")),
        "heartbeats_dir_exists": bool(heartbeats_dir and heartbeats_dir.get("exists")),
        "brain_dir_exists": bool(brain_dir and brain_dir.get("exists")),
        "qmd_manifest_includes_soul_sources": bool(
            qmd_audit["checks"].get("profile_snapshot_source_present")
            and qmd_audit["checks"].get("soul_or_identity_source_present")
        ),
        "qmd_search_finds_profile_or_heartbeat": bool(
            qmd_audit["checks"].get("profile_snapshot_source_present")
            or qmd_audit["checks"].get("heartbeats_source_present")
        ),
        "control_plane_count": len(control_plane),
        "root_control_doc_count": len(root_docs),
    }

    ok = not failures and all(
        checks[key]
        for key in (
            "repo_root_wsl_exists",
            "vault_root_wsl_exists",
            "otto_realm_exists",
            "profile_snapshot_exists",
            "heartbeats_dir_exists",
        )
    )
    return {
        "ok": ok,
        "state": "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY" if ok else "SOUL1_BLOCKED",
        "checked_at": now_iso(),
        "failures": failures,
        "warnings": warnings,
        "checks": checks,
        "qmd_soul_audit": qmd_audit,
        "root_audit": root_audit,
    }


def build_heartbeat_root_audit() -> dict[str, Any]:
    health = build_soul_health()
    root_audit = health.get("root_audit") or {}
    canonical = root_audit.get("canonical_soul_root") or {}
    legacy = root_audit.get("legacy_wrong_root") or {}
    warnings = list(health.get("warnings") or [])
    if bool(root_audit.get("legacy_wrong_root_exists")):
        warnings.append("legacy_wrong_root_detected_non_destructive")
    return {
        "ok": bool(health.get("ok")),
        "state": "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY" if health.get("ok") else "SOUL1_BLOCKED",
        "checked_at": now_iso(),
        "canonical_soul_root": canonical,
        "legacy_wrong_root": legacy,
        "legacy_wrong_root_exists": bool(root_audit.get("legacy_wrong_root_exists")),
        "wrong_root_candidates": root_audit.get("wrong_root_candidates", []),
        "non_destructive": True,
        "health_checks": health.get("checks", {}),
        "health_failures": health.get("failures", []),
        "warnings": warnings,
    }


def write_soul_health(path: Path | None = None) -> dict[str, Any]:
    health = build_soul_health()
    target = path or soul_health_path()
    write_json(target, health)
    return {"ok": bool(health.get("ok")), "path": str(target), "health": health}
