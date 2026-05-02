from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import state_root
from ..state import now_iso, write_json
from .paths import (
    build_root_audit,
    control_plane_entries,
    infer_soul_roots,
    root_control_doc_entries,
    vault_identity_entries,
)
from .scope import build_soul_scope


def soul_manifest_path() -> Path:
    return state_root() / "soul" / "soul_manifest.json"


def build_soul_manifest() -> dict[str, Any]:
    roots = infer_soul_roots()
    vault_root_windows = str(getattr(roots, "vault_root_windows", "C:/Users/joshu/Josh Obsidian"))
    vault_root_wsl = str(getattr(roots, "vault_root_wsl", "/mnt/c/Users/joshu/Josh Obsidian"))
    soul_root_windows = str(getattr(roots, "soul_root_windows", f"{vault_root_windows.rstrip('/')}/.Otto-Realm"))
    soul_root_wsl = str(getattr(roots, "soul_root_wsl", f"{vault_root_wsl.rstrip('/')}/.Otto-Realm"))
    control_plane = control_plane_entries(roots.repo_root_wsl)
    vault_identity = vault_identity_entries(vault_root_wsl)
    root_docs = root_control_doc_entries(roots.repo_root_wsl)
    return {
        "version": 1,
        "generated_at": now_iso(),
        "state": "SOUL1_WSL_IDENTITY_HEARTBEAT_REHYDRATION_READY",
        "repo_root": {
            "windows": roots.repo_root_windows,
            "wsl": roots.repo_root_wsl,
        },
        "vault_root": {
            "windows": vault_root_windows,
            "wsl": vault_root_wsl,
        },
        "soul_root": {
            "windows": soul_root_windows,
            "wsl": soul_root_wsl,
        },
        "control_plane": control_plane,
        "vault_identity": vault_identity,
        "root_control_docs": root_docs,
        "root_audit": build_root_audit(roots),
        "scope": build_soul_scope(),
    }


def write_soul_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest = build_soul_manifest()
    target = path or soul_manifest_path()
    write_json(target, manifest)
    return {"ok": True, "path": str(target), "manifest": manifest}
