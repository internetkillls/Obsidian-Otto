from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

from ..config import load_paths, load_retrieval_config
from ..fs_utils import exists as path_exists, is_dir as path_is_dir, is_file as path_is_file, iter_files, read_bytes, read_text
from ..logging_utils import get_logger
from ..state import write_json

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_\-/.]+)")


@dataclass
class NoteRecord:
    path: str
    title: str
    size: int
    sha1: str
    mtime: float
    has_frontmatter: bool
    frontmatter_text: str
    tags: list[str]
    wikilinks: list[str]
    extension: str
    body_excerpt: str
    scarcity: list[str]
    necessity: float | None
    artificial: float | None
    orientation: str | None
    allocation: str | None
    cluster_membership: list[str]
    aliases: list[str]


SCARCITY_TAG_KEYS = {
    "scarcity": True,
    "necessity": False,
    "artificial": False,
    "orientation": False,
    "allocation": False,
    "cluster": True,
    "cluster_membership": True,
}


@dataclass(frozen=True)
class ScanBoundary:
    include_prefixes: tuple[str, ...]
    exclude_prefixes: tuple[str, ...]


DEFAULT_INCLUDE_PREFIXES = (
    ".Otto-Realm/Brain/",
    ".Otto-Realm/Memory-Tiers/",
)
DEFAULT_EXCLUDE_PREFIXES = (
    ".Otto-Realm/",
)


def _yaml_frontmatter(frontmatter_text: str) -> dict[str, Any]:
    if not frontmatter_text.strip():
        return {}
    try:
        parsed = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        items = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                items.append(text)
        return items
    text = str(value).strip()
    return [text] if text else []


def _normalize_scalar(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result


def _extract_structured_tags(tags: list[str]) -> dict[str, list[str]]:
    metadata: dict[str, list[str]] = {key: [] for key in SCARCITY_TAG_KEYS}
    for tag in tags:
        raw = tag.strip()
        lowered = raw.lower()
        for key in SCARCITY_TAG_KEYS:
            prefixes = [f"{key}/", f"{key}_", f"{key}-"]
            match = next((prefix for prefix in prefixes if lowered.startswith(prefix)), None)
            if match is None:
                continue
            suffix = raw[len(match):].strip()
            if suffix:
                metadata[key].append(suffix)
            break
    return metadata


def _merge_scarcity_metadata(frontmatter: dict[str, Any], tags: list[str]) -> dict[str, Any]:
    tag_meta = _extract_structured_tags(tags)
    scarcity = _normalize_list(frontmatter.get("scarcity")) or tag_meta["scarcity"]
    orientation = _normalize_scalar(frontmatter.get("orientation")) or _normalize_scalar(
        tag_meta["orientation"][0] if tag_meta["orientation"] else None
    )
    allocation = _normalize_scalar(frontmatter.get("allocation")) or _normalize_scalar(
        tag_meta["allocation"][0] if tag_meta["allocation"] else None
    )
    necessity = _normalize_float(frontmatter.get("necessity"))
    if necessity is None and tag_meta["necessity"]:
        necessity = _normalize_float(tag_meta["necessity"][0])
    artificial = _normalize_float(frontmatter.get("artificial"))
    if artificial is None and tag_meta["artificial"]:
        artificial = _normalize_float(tag_meta["artificial"][0])

    cluster_membership = _normalize_list(frontmatter.get("cluster_membership"))
    if not cluster_membership:
        cluster_membership = tag_meta["cluster_membership"] or tag_meta["cluster"]
    if not cluster_membership:
        cluster_membership = list(scarcity)

    return {
        "scarcity": _dedupe_preserve(_normalize_list(scarcity)),
        "necessity": necessity,
        "artificial": artificial,
        "orientation": orientation,
        "allocation": allocation,
        "cluster_membership": _dedupe_preserve(_normalize_list(cluster_membership)),
    }


def _title_from_path(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").strip() or path.name


def _sha1(path: Path) -> str:
    return hashlib.sha1(read_bytes(path)).hexdigest()


def _normalize_rel_path(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def _normalize_prefixes(values: Any, defaults: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, list):
        values = list(defaults)
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        trimmed = _normalize_rel_path(value)
        if not trimmed:
            continue
        prefix = f"{trimmed}/"
        if prefix not in normalized:
            normalized.append(prefix)
    return tuple(normalized)


def _load_scan_boundary() -> ScanBoundary:
    cfg = load_retrieval_config().get("scan", {})
    return ScanBoundary(
        include_prefixes=_normalize_prefixes(cfg.get("include_prefixes"), DEFAULT_INCLUDE_PREFIXES),
        exclude_prefixes=_normalize_prefixes(cfg.get("exclude_prefixes"), DEFAULT_EXCLUDE_PREFIXES),
    )


def _match_prefix(path: str, prefixes: tuple[str, ...]) -> str | None:
    normalized = _normalize_rel_path(path)
    for prefix in prefixes:
        if normalized.startswith(prefix[:-1]) and (
            normalized == prefix[:-1] or normalized.startswith(prefix)
        ):
            return prefix
    return None


def _classify_scan_path(path: str, boundary: ScanBoundary) -> tuple[bool, str | None]:
    included_by = _match_prefix(path, boundary.include_prefixes)
    if included_by:
        return True, included_by
    excluded_by = _match_prefix(path, boundary.exclude_prefixes)
    if excluded_by:
        return False, excluded_by
    return True, None


def scan_vault(scope: str | None = None) -> dict[str, Any]:
    logger = get_logger("otto.scan")
    paths = load_paths()
    if paths.vault_path is None:
        raise RuntimeError("Vault path not configured. Run initial.bat first.")
    if not path_is_dir(paths.vault_path):
        raise RuntimeError(f"Vault path is not a directory: {paths.vault_path}")

    base = paths.vault_path
    target = (base / scope).resolve() if scope else base
    if not path_exists(target):
        raise FileNotFoundError(f"Scope does not exist: {target}")

    notes: list[NoteRecord] = []
    attachments: list[dict[str, Any]] = []
    boundary = _load_scan_boundary()
    excluded_notes = 0
    excluded_attachments = 0
    excluded_by_prefix: dict[str, int] = {}
    excluded_samples: list[str] = []

    for path in iter_files(target):
        if not path_is_file(path):
            continue
        rel = str(path.relative_to(base))
        allowed, matched_prefix = _classify_scan_path(rel, boundary)
        if not allowed:
            if path.suffix.lower() == ".md":
                excluded_notes += 1
            else:
                excluded_attachments += 1
            if matched_prefix:
                excluded_by_prefix[matched_prefix] = excluded_by_prefix.get(matched_prefix, 0) + 1
            if len(excluded_samples) < 12:
                excluded_samples.append(_normalize_rel_path(rel))
            continue
        stat = path.stat()
        if path.suffix.lower() == ".md":
            text = read_text(path, encoding="utf-8", errors="replace")
            fm = FRONTMATTER_RE.match(text)
            body = text[fm.end():] if fm else text
            tags = sorted(set(TAG_RE.findall(body)))
            links = sorted(set(WIKILINK_RE.findall(text)))
            frontmatter_text = fm.group(1).strip() if fm else ""
            frontmatter_data = _yaml_frontmatter(frontmatter_text)
            scarcity_meta = _merge_scarcity_metadata(frontmatter_data, tags)
            aliases = _dedupe_preserve(_normalize_list(frontmatter_data.get("aliases")))
            notes.append(
                NoteRecord(
                    path=rel,
                    title=_title_from_path(path),
                    size=stat.st_size,
                    sha1=_sha1(path),
                    mtime=stat.st_mtime,
                    has_frontmatter=bool(fm),
                    frontmatter_text=frontmatter_text,
                    tags=tags,
                    wikilinks=links,
                    extension=path.suffix.lower(),
                    body_excerpt=body[:2000],
                    scarcity=scarcity_meta["scarcity"],
                    necessity=scarcity_meta["necessity"],
                    artificial=scarcity_meta["artificial"],
                    orientation=scarcity_meta["orientation"],
                    allocation=scarcity_meta["allocation"],
                    cluster_membership=scarcity_meta["cluster_membership"],
                    aliases=aliases,
                )
            )
        else:
            attachments.append(
                {
                    "path": rel,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "extension": path.suffix.lower(),
                }
            )

    notes.sort(key=lambda n: n.path)
    attachments.sort(key=lambda a: a["path"])

    if not notes and not attachments:
        logger.warning(f"[scan] empty vault — no notes or attachments found at scope={scope or '.'}")
        raise RuntimeError(f"Vault scan produced no notes. Check vault path configuration. Scope: {target}")

    payload = {
        "vault": str(base),
        "scope": str(scope or "."),
        "note_count": len(notes),
        "attachment_count": len(attachments),
        "notes": [asdict(n) for n in notes],
        "attachments": attachments,
        "scan_boundary": {
            "include_prefixes": list(boundary.include_prefixes),
            "exclude_prefixes": list(boundary.exclude_prefixes),
            "excluded_note_count": excluded_notes,
            "excluded_attachment_count": excluded_attachments,
            "excluded_by_prefix": excluded_by_prefix,
            "excluded_samples": excluded_samples,
        },
    }
    write_json(paths.bronze_root / "bronze_manifest.json", payload)
    write_json(paths.artifacts_root / "reports" / "bronze_summary.json", {
        "scope": payload["scope"],
        "note_count": payload["note_count"],
        "attachment_count": payload["attachment_count"],
        "included_prefixes": list(boundary.include_prefixes),
        "excluded_prefixes": list(boundary.exclude_prefixes),
        "excluded_note_count": excluded_notes,
        "excluded_attachment_count": excluded_attachments,
        "excluded_by_prefix": excluded_by_prefix,
    })
    logger.info(
        f"[scan] notes={len(notes)} attachments={len(attachments)} "
        f"excluded_notes={excluded_notes} excluded_attachments={excluded_attachments} scope={scope or '.'}"
    )
    return payload
