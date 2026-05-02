from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
try:
    import yaml
except Exception:  # pragma: no cover - optional fallback
    yaml = None

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_\-/.]+)")
CLUSTERS = ("MEMORY", "SKILL", "DESIGN", "SYSTEM", "THEORY", "CRAFT", "VOICE", "CONTEXT")
SCARCITY_FAMILY_TO_CLUSTER = {
    "context": "MEMORY",
    "standardization": "SKILL",
    "novel_solution": "DESIGN",
    "novice_solution": "DESIGN",
    "interconnectivity": "SYSTEM",
    "first_principles": "THEORY",
    "expressive_form": "CRAFT",
    "legitimation": "VOICE",
    "situational_ground": "CONTEXT",
}

STRUCTURED_TAG_KEYS = (
    "scarcity",
    "necessity",
    "artificial",
    "orientation",
    "allocation",
    "cluster",
    "cluster_membership",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _load_env_file(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def resolve_vault_path(repo_root: Path) -> Path:
    value = os.environ.get("OTTO_VAULT_PATH") or _load_env_file(repo_root / ".env").get("OTTO_VAULT_PATH") or ""
    if not value:
        return repo_root
    return Path(value).expanduser().resolve()


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    return parse_frontmatter(match.group(1)), text[match.end() :]


def parse_frontmatter(text: str) -> dict[str, Any]:
    if yaml is not None:
        try:
            parsed = yaml.safe_load(text) or {}
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    result: dict[str, Any] = {}
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        if raw.startswith((" ", "\t")) or ":" not in raw:
            index += 1
            continue

        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()

        if not value:
            items: list[Any] = []
            lookahead = index + 1
            while lookahead < len(lines):
                child = lines[lookahead]
                stripped = child.strip()
                if not stripped:
                    lookahead += 1
                    continue
                if child.startswith("- "):
                    items.append(parse_scalar(child[2:].strip()))
                    lookahead += 1
                    continue
                if child.startswith("  - "):
                    items.append(parse_scalar(child[4:].strip()))
                    lookahead += 1
                    continue
                break
            result[key] = items
            index = lookahead
            continue

        result[key] = parse_scalar(value)
        index += 1

    return result


def parse_scalar(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part) for part in inner.split(",")]
    if stripped.startswith(("\"", "'")) and stripped.endswith(("\"", "'")):
        return stripped[1:-1]
    lowered = stripped.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        if "." in stripped:
            return float(stripped)
        return int(stripped)
    except ValueError:
        return stripped


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        output = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                output.append(text)
        return output
    text = str(value).strip()
    return [text] if text else []


def normalize_scalar(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result


def normalize_label_key(value: str) -> str:
    return re.sub(r"[\s\\-]+", "_", value.strip().lower())


def extract_tags(text: str) -> list[str]:
    return sorted(set(TAG_RE.findall(text)))


def extract_structured_tags(tags: list[str]) -> dict[str, list[str]]:
    metadata = {key: [] for key in STRUCTURED_TAG_KEYS}
    for tag in tags:
        lowered = tag.lower().strip()
        for key in STRUCTURED_TAG_KEYS:
            prefixes = (f"{key}/", f"{key}_", f"{key}-")
            prefix = next((candidate for candidate in prefixes if lowered.startswith(candidate)), None)
            if prefix is None:
                continue
            suffix = tag[len(prefix) :].strip()
            if suffix:
                metadata[key].append(suffix)
            break
    return metadata


def derive_clusters(scarcity: list[str], explicit_clusters: list[str]) -> list[str]:
    if explicit_clusters:
        return dedupe_preserve([value.upper() for value in explicit_clusters])
    matched = []
    for value in scarcity:
        key = normalize_label_key(value)
        if key.upper() in CLUSTERS:
            matched.append(key.upper())
            continue
        cluster = SCARCITY_FAMILY_TO_CLUSTER.get(key)
        if cluster:
            matched.append(cluster)
    return dedupe_preserve(matched)


def read_note_metadata(path: Path, vault: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = split_frontmatter(text)
    tags = extract_tags(text)
    tag_meta = extract_structured_tags(tags)

    scarcity = normalize_list(frontmatter.get("scarcity")) or tag_meta["scarcity"]
    necessity = normalize_float(frontmatter.get("necessity"))
    if necessity is None and tag_meta["necessity"]:
        necessity = normalize_float(tag_meta["necessity"][0])

    artificial = normalize_float(frontmatter.get("artificial"))
    if artificial is None and tag_meta["artificial"]:
        artificial = normalize_float(tag_meta["artificial"][0])

    orientation = normalize_scalar(frontmatter.get("orientation")) or normalize_scalar(
        tag_meta["orientation"][0] if tag_meta["orientation"] else None
    )
    allocation = normalize_scalar(frontmatter.get("allocation")) or normalize_scalar(
        tag_meta["allocation"][0] if tag_meta["allocation"] else None
    )

    explicit_clusters = (
        normalize_list(frontmatter.get("cluster_membership"))
        or tag_meta["cluster_membership"]
        or tag_meta["cluster"]
    )
    cluster_membership = derive_clusters(scarcity, explicit_clusters)

    has_frontmatter_scarcity = "scarcity" in frontmatter
    return {
        "note_path": str(path.relative_to(vault)),
        "scarcity": dedupe_preserve(normalize_list(scarcity)),
        "necessity": necessity,
        "artificial": artificial,
        "orientation": orientation,
        "allocation": allocation,
        "cluster_membership": cluster_membership,
        "has_frontmatter_scarcity": has_frontmatter_scarcity,
        "tags": tags,
        "body_excerpt": body[:400],
    }
