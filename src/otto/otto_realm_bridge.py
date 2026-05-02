from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_metadata_enrichment_config, load_paths
from .state import now_iso


def _normalize_rel_path(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def _candidate_roots(paths: Any, config: dict[str, Any]) -> list[Path]:
    realm_cfg = (config.get("metadata_enrichment") or {}).get("otto_realm", {})
    roots = realm_cfg.get("roots") or [".Otto-Realm", "Otto-Realm"]
    base_candidates = [paths.vault_path, paths.repo_root]
    resolved: list[Path] = []
    for raw_root in roots:
        root_value = str(raw_root or "").strip()
        if not root_value:
            continue
        candidate = Path(root_value)
        if not candidate.is_absolute():
            for base in base_candidates:
                if base is None:
                    continue
                resolved_candidate = (base / candidate).resolve()
                if resolved_candidate.exists():
                    resolved.append(resolved_candidate)
                    break
            else:
                continue
        elif candidate.exists():
            resolved.append(candidate)
    seen: set[str] = set()
    deduped: list[Path] = []
    for path in resolved:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _artifact_globs(config: dict[str, Any]) -> tuple[str, ...]:
    realm_cfg = (config.get("metadata_enrichment") or {}).get("otto_realm", {})
    globs = realm_cfg.get("artifact_globs") or (
        "Brain/*.md",
        "Heartbeats/*.md",
        "Memory-Tiers/*.md",
        "Predictions/*.md",
        "Rituals/*.md",
        "Handoff/*.md",
    )
    cleaned: list[str] = []
    for item in globs:
        text = _normalize_rel_path(str(item or ""))
        if text:
            cleaned.append(text)
    return tuple(cleaned)


def load_legacy_otto_realm_context(paths: Any | None = None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    active_paths = paths or load_paths()
    cfg = config or load_metadata_enrichment_config()
    roots = _candidate_roots(active_paths, cfg)
    globs = _artifact_globs(cfg)

    artifacts: list[dict[str, Any]] = []
    for root in roots:
        for pattern in globs:
            for path in sorted(root.glob(pattern)):
                if not path.is_file():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                rel = str(path.relative_to(root)).replace("\\", "/")
                artifacts.append(
                    {
                        "root": str(root),
                        "path": rel,
                        "absolute_path": str(path),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "updated_at": now_iso(),
                    }
                )

    artifacts.sort(key=lambda item: (item["root"], item["path"]))
    latest = artifacts[-10:]
    return {
        "roots": [str(root) for root in roots],
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "latest_artifacts": latest,
    }
