from __future__ import annotations

from typing import Any

from .paths import ROOT_CONTROL_DOCS


def build_soul_scope() -> dict[str, Any]:
    return {
        "version": 1,
        "purpose": "soul_identity_heartbeat_rehydration",
        "include_root_control_docs": ROOT_CONTROL_DOCS,
        "include_vault_identity_globs": [
            ".Otto-Realm/Profile Snapshot.md",
            ".Otto-Realm/Central Schedule.md",
            ".Otto-Realm/Brain/**/*.md",
            ".Otto-Realm/Heartbeats/**/*.md",
            ".Otto-Realm/Memory-Tiers/**/*.md",
            ".Otto-Realm/Rituals/**/*.md",
            ".Otto-Realm/Predictions/**/*.md",
        ],
        "active_scope_exclusions_reused": False,
        "dot_folders_allowed_for_soul_scope": [".Otto-Realm"],
        "raw_vault_full_scan_enabled": False,
        "raw_private_unrelated_index_enabled": False,
    }

