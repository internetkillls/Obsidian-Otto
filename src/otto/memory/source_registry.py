from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import repo_root
from ..path_compat import is_wsl


REGISTRY_VERSION = 1


@dataclass(frozen=True)
class SourceEntry:
    id: str
    kind: str
    path_windows: str
    path_wsl: str
    required: bool
    qmd_index: bool
    vault_writeback: bool
    privacy: str
    owner: str
    pattern: str = "**/*.md"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceEntry":
        return cls(
            id=str(payload["id"]),
            kind=str(payload["kind"]),
            path_windows=str(payload["path_windows"]),
            path_wsl=str(payload["path_wsl"]),
            required=bool(payload.get("required", False)),
            qmd_index=bool(payload.get("qmd_index", False)),
            vault_writeback=bool(payload.get("vault_writeback", False)),
            privacy=str(payload["privacy"]),
            owner=str(payload["owner"]),
            pattern=str(payload.get("pattern") or "**/*.md"),
        )

    def path_for_runtime(self) -> Path:
        return Path(self.path_wsl if is_wsl() else self.path_windows)

    def to_qmd_source(self) -> dict[str, str]:
        return {"name": self.id, "path": self.path_wsl, "pattern": self.pattern}


def source_registry_path() -> Path:
    return repo_root() / "state" / "memory" / "source_registry.json"


def default_source_registry() -> dict[str, Any]:
    return {
        "version": REGISTRY_VERSION,
        "sources": [
            {
                "id": "otto-facts",
                "kind": "curated_memory",
                "path_windows": "C:/Users/joshu/Josh Obsidian/.Otto-Realm/Memory-Tiers/01-Facts",
                "path_wsl": "/mnt/c/Users/joshu/Josh Obsidian/.Otto-Realm/Memory-Tiers/01-Facts",
                "required": True,
                "qmd_index": True,
                "vault_writeback": True,
                "privacy": "private_reviewed",
                "owner": "otto",
            },
            {
                "id": "otto-interpretations",
                "kind": "curated_memory",
                "path_windows": "C:/Users/joshu/Josh Obsidian/.Otto-Realm/Memory-Tiers/02-Interpretations",
                "path_wsl": "/mnt/c/Users/joshu/Josh Obsidian/.Otto-Realm/Memory-Tiers/02-Interpretations",
                "required": True,
                "qmd_index": True,
                "vault_writeback": True,
                "privacy": "private_reviewed",
                "owner": "otto",
            },
            {
                "id": "otto-speculations",
                "kind": "curated_memory",
                "path_windows": "C:/Users/joshu/Josh Obsidian/.Otto-Realm/Memory-Tiers/03-Speculations",
                "path_wsl": "/mnt/c/Users/joshu/Josh Obsidian/.Otto-Realm/Memory-Tiers/03-Speculations",
                "required": True,
                "qmd_index": True,
                "vault_writeback": True,
                "privacy": "private_reviewed",
                "owner": "otto",
            },
            {
                "id": "otto-brain",
                "kind": "curated_profile",
                "path_windows": "C:/Users/joshu/Josh Obsidian/.Otto-Realm/Brain",
                "path_wsl": "/mnt/c/Users/joshu/Josh Obsidian/.Otto-Realm/Brain",
                "required": True,
                "qmd_index": True,
                "vault_writeback": True,
                "privacy": "private_reviewed",
                "owner": "otto",
            },
            {
                "id": "otto-briefing",
                "kind": "otto_realm",
                "path_windows": "C:/Users/joshu/Josh Obsidian/.Otto-Realm",
                "path_wsl": "/mnt/c/Users/joshu/Josh Obsidian/.Otto-Realm",
                "required": True,
                "qmd_index": True,
                "vault_writeback": True,
                "privacy": "private",
                "owner": "otto",
            },
            {
                "id": "otto-crack-research",
                "kind": "program_research",
                "path_windows": "C:/Users/joshu/Josh Obsidian/20-Programs/Crack-Research",
                "path_wsl": "/mnt/c/Users/joshu/Josh Obsidian/20-Programs/Crack-Research",
                "required": True,
                "qmd_index": True,
                "vault_writeback": False,
                "privacy": "private",
                "owner": "obsidian",
            },
            {
                "id": "instagram_graph_raw",
                "kind": "social_raw",
                "path_windows": "C:/Users/joshu/Obsidian-Otto/state/social/instagram/raw",
                "path_wsl": "/mnt/c/Users/joshu/Obsidian-Otto/state/social/instagram/raw",
                "required": False,
                "qmd_index": False,
                "vault_writeback": False,
                "privacy": "sensitive",
                "owner": "otto",
            },
            {
                "id": "profile_gold",
                "kind": "profile_gold",
                "path_windows": "C:/Users/joshu/Obsidian-Otto/state/profile/gold",
                "path_wsl": "/mnt/c/Users/joshu/Obsidian-Otto/state/profile/gold",
                "required": False,
                "qmd_index": True,
                "vault_writeback": True,
                "privacy": "private_reviewed",
                "owner": "otto",
            },
        ],
    }


def write_default_source_registry(path: Path | None = None, *, overwrite: bool = False) -> Path:
    path = path or source_registry_path()
    if path.exists() and not overwrite:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(default_source_registry(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_source_registry(path: Path | None = None) -> dict[str, Any]:
    path = path or source_registry_path()
    if not path.exists():
        return default_source_registry()
    return json.loads(path.read_text(encoding="utf-8"))


def iter_sources(registry: dict[str, Any] | None = None) -> list[SourceEntry]:
    registry = registry or load_source_registry()
    return [SourceEntry.from_dict(item) for item in registry.get("sources", []) if isinstance(item, dict)]


def qmd_indexable_sources(registry: dict[str, Any] | None = None) -> list[SourceEntry]:
    return [source for source in iter_sources(registry) if source.qmd_index]


def validate_source_registry(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_source_registry()
    sources = iter_sources(registry)
    seen: set[str] = set()
    source_reports: list[dict[str, Any]] = []
    errors: list[str] = []

    if registry.get("version") != REGISTRY_VERSION:
        errors.append("unsupported-registry-version")

    for source in sources:
        if source.id in seen:
            errors.append(f"duplicate-source:{source.id}")
        seen.add(source.id)
        path = source.path_for_runtime()
        exists = path.exists()
        if source.required and not exists:
            errors.append(f"required-source-missing:{source.id}")
        if source.kind.endswith("_raw") and source.qmd_index:
            errors.append(f"raw-source-qmd-enabled:{source.id}")
        source_reports.append(
            {
                "id": source.id,
                "kind": source.kind,
                "path": str(path),
                "required": source.required,
                "exists": exists,
                "qmd_index": source.qmd_index,
                "vault_writeback": source.vault_writeback,
                "privacy": source.privacy,
            }
        )

    return {
        "ok": not errors,
        "version": registry.get("version"),
        "source_count": len(sources),
        "qmd_indexable_count": len([source for source in sources if source.qmd_index]),
        "errors": errors,
        "sources": source_reports,
    }
