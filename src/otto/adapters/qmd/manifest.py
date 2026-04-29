from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...config import repo_root
from ...memory.source_registry import REGISTRY_VERSION, SourceEntry, qmd_indexable_sources, validate_source_registry
from ...state import now_iso, write_json


MANIFEST_VERSION = 1
DEFAULT_QMD_COMMAND = "/usr/bin/qmd"


def qmd_manifest_path() -> Path:
    return repo_root() / "state" / "qmd" / "qmd_manifest.json"


def _source_to_manifest_entry(source: SourceEntry) -> dict[str, Any]:
    return {
        "id": source.id,
        "kind": source.kind,
        "path": source.path_wsl,
        "path_windows": source.path_windows,
        "path_wsl": source.path_wsl,
        "required": source.required,
        "pattern": source.pattern,
        "privacy": source.privacy,
        "owner": source.owner,
    }


def build_qmd_manifest(
    registry: dict[str, Any] | None = None,
    *,
    runtime: str = "wsl_shadow",
    qmd_command: str = DEFAULT_QMD_COMMAND,
) -> dict[str, Any]:
    """Build the Otto-approved QMD source manifest from the source registry."""
    registry_health = validate_source_registry(registry)
    sources = [_source_to_manifest_entry(source) for source in qmd_indexable_sources(registry)]
    required_missing = [
        error.split(":", 1)[1]
        for error in registry_health.get("errors", [])
        if isinstance(error, str) and error.startswith("required-source-missing:")
    ]
    return {
        "version": MANIFEST_VERSION,
        "registry_version": REGISTRY_VERSION,
        "runtime": runtime,
        "qmd_command": qmd_command,
        "generated_at": now_iso(),
        "ok": bool(registry_health.get("ok")),
        "source_count": len(sources),
        "required_missing": required_missing,
        "registry_errors": registry_health.get("errors", []),
        "sources": sources,
    }


def write_qmd_manifest(
    path: Path | None = None,
    *,
    registry: dict[str, Any] | None = None,
    runtime: str = "wsl_shadow",
    qmd_command: str = DEFAULT_QMD_COMMAND,
) -> dict[str, Any]:
    manifest = build_qmd_manifest(registry, runtime=runtime, qmd_command=qmd_command)
    target = path or qmd_manifest_path()
    write_json(target, manifest)
    return {
        "ok": bool(manifest.get("ok")),
        "path": str(target),
        "manifest": manifest,
    }


def load_qmd_manifest(path: Path | None = None) -> dict[str, Any] | None:
    target = path or qmd_manifest_path()
    if not target.exists():
        return None
    data = json.loads(target.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def qmd_manifest_health(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = manifest or load_qmd_manifest() or build_qmd_manifest()
    errors: list[str] = []
    if manifest.get("version") != MANIFEST_VERSION:
        errors.append("unsupported-manifest-version")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("manifest-has-no-sources")
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            errors.append("manifest-source-not-object")
            continue
        path = source.get("path")
        if not path:
            errors.append(f"manifest-source-missing-path:{source.get('id')}")
        if str(source.get("kind", "")).endswith("_raw"):
            errors.append(f"raw-source-in-qmd-manifest:{source.get('id')}")
    errors.extend(str(error) for error in manifest.get("registry_errors", []) if error)
    return {
        "ok": not errors,
        "errors": errors,
        "source_count": len(sources) if isinstance(sources, list) else 0,
        "manifest": manifest,
    }
