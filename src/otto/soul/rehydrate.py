from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import append_jsonl, state_root
from ..memory.source_registry import ensure_soul_identity_sources
from ..state import now_iso, write_json
from .health import build_soul_health
from .manifest import build_soul_manifest
from .paths import infer_soul_roots, to_host_path


REQUIRED_CANONICAL_DIRS = [
    ".Otto-Realm/Heartbeats",
    ".Otto-Realm/Brain",
    ".Otto-Realm/Memory-Tiers",
    ".Otto-Realm/Rituals",
    ".Otto-Realm/Predictions",
]
REQUIRED_CANONICAL_FILES = [
    ".Otto-Realm/Profile Snapshot.md",
]


def _seed_frontmatter_body() -> str:
    return (
        "---\n"
        "otto_state: seeded_missing_canonical_file\n"
        "review_required: true\n"
        "source: soul_rehydrate\n"
        "---\n\n"
        "Canonical SOUL file was seeded because it was missing.\n"
    )


def _seed_missing_canonical_soul(*, write: bool) -> dict[str, Any]:
    roots = infer_soul_roots()
    vault_root = to_host_path(roots.vault_root_wsl)
    to_create_dirs: list[str] = []
    created_dirs: list[str] = []
    to_create_files: list[str] = []
    created_files: list[str] = []

    for rel in REQUIRED_CANONICAL_DIRS:
        path = vault_root / rel
        if not path.exists():
            to_create_dirs.append(str(path))
            if write:
                path.mkdir(parents=True, exist_ok=True)
                created_dirs.append(str(path))

    for rel in REQUIRED_CANONICAL_FILES:
        path = vault_root / rel
        if not path.exists():
            to_create_files.append(str(path))
            if write:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(_seed_frontmatter_body(), encoding="utf-8")
                created_files.append(str(path))

    return {
        "ok": True,
        "write": write,
        "vault_root": str(vault_root),
        "canonical_soul_root": str(vault_root / ".Otto-Realm"),
        "to_create_dirs": to_create_dirs,
        "to_create_files": to_create_files,
        "created_dirs": created_dirs,
        "created_files": created_files,
        "seed_frontmatter": {
            "otto_state": "seeded_missing_canonical_file",
            "review_required": True,
            "source": "soul_rehydrate",
        },
        "non_destructive": True,
    }


def soul_rehydrate_last_path() -> Path:
    return state_root() / "soul" / "soul_rehydrate_last.json"


def soul_rehydrate_runs_path() -> Path:
    return state_root() / "soul" / "soul_rehydrate_runs.jsonl"


def run_soul_rehydrate(*, dry_run: bool = True, write: bool = False) -> dict[str, Any]:
    apply_writes = bool(write and not dry_run)
    seeding = _seed_missing_canonical_soul(write=apply_writes)
    registry_patch = ensure_soul_identity_sources(write=apply_writes)
    manifest = build_soul_manifest()
    health = build_soul_health()
    result: dict[str, Any] = {
        "ok": bool(health.get("ok")),
        "state": "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY" if health.get("ok") else "SOUL1_BLOCKED",
        "dry_run": dry_run,
        "write": write,
        "updated_at": now_iso(),
        "seeding": seeding,
        "manifest": manifest,
        "health": health,
        "registry_patch": registry_patch,
    }
    if apply_writes:
        write_json(state_root() / "soul" / "soul_manifest.json", manifest)
        write_json(state_root() / "soul" / "soul_health.json", health)
        write_json(soul_rehydrate_last_path(), result)
        append_jsonl(soul_rehydrate_runs_path(), result)
    return result
