from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ..config import load_paths
from ..fs_utils import exists as path_exists, is_dir as path_is_dir, is_file as path_is_file, iter_markdown_files, read_text, relative_path, rename as rename_path, write_text
from ..logging_utils import get_logger
from ..scoping import is_active_scope
from ..state import now_iso, read_json, write_json

FRONTMATTER_RE = re.compile(r"^\ufeff?---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
HASH_SUFFIX_RE = re.compile(r"(?:[\s_-]+)(?:[0-9a-fA-F]{8,64}|[A-Za-z0-9]{16,64})$")


@dataclass
class NoteSnapshot:
    path: Path
    rel_path: str
    title: str
    has_frontmatter: bool
    frontmatter: dict[str, Any]
    body: str
    wikilinks: list[str]


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r'[\\/:"*?<>|]+', " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" _-")


def _normalize_aliases(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    return _dedupe_preserve([_normalize_text(item) for item in items if str(item).strip()])


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, "", text
    raw_frontmatter = match.group(1)
    body = text[match.end():]
    try:
        parsed = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return parsed, raw_frontmatter, body


def _dump_frontmatter(metadata: dict[str, Any]) -> str:
    if not metadata:
        return ""
    dumped = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{dumped}\n---\n"


def _title_from_body(body: str) -> str:
    match = H1_RE.search(body)
    if match:
        return _normalize_text(match.group(1))
    for line in body.splitlines():
        cleaned = _normalize_text(line)
        if cleaned:
            return cleaned
    return ""


def _strip_hash_suffix(text: str) -> str:
    cleaned = _normalize_text(text)
    while True:
        stripped = HASH_SUFFIX_RE.sub("", cleaned).strip(" _-()[]")
        stripped = re.sub(r"\s+", " ", stripped).strip()
        if stripped == cleaned:
            break
        cleaned = stripped
    return cleaned


def _read_note(path: Path, vault: Path) -> NoteSnapshot:
    text = read_text(path, encoding="utf-8", errors="replace")
    frontmatter, _raw_frontmatter, body = _split_frontmatter(text)
    title = _normalize_text(frontmatter.get("title") or _title_from_body(body) or _strip_hash_suffix(path.stem) or path.stem)
    wikilinks = []
    for match in WIKILINK_RE.finditer(body):
        raw = match.group(1).strip()
        if raw:
            wikilinks.append(raw.split("|", 1)[0].strip())
    return NoteSnapshot(
        path=path,
        rel_path=relative_path(path, vault).replace("\\", "/"),
        title=title,
        has_frontmatter=bool(frontmatter),
        frontmatter=frontmatter,
        body=body,
        wikilinks=_dedupe_preserve(wikilinks),
    )


def _resolve_note_targets(vault: Path, scope: str, notes: list[str]) -> list[Path]:
    if notes:
        resolved: list[Path] = []
        for raw in notes:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = (vault / candidate).resolve()
            if path_exists(candidate):
                resolved.append(candidate)
        return resolved

    normalized_scope = (scope or "active").strip()
    if normalized_scope == "active":
        return [path for path in sorted(iter_markdown_files(vault)) if is_active_scope(path, vault)]
    if normalized_scope == "full":
        return [
            path
            for path in sorted(iter_markdown_files(vault))
            if not any(
                part in {"state", "tests", ".obsidian", ".git", ".trash", ".venv", ".Otto-Realm", "Otto-Realm"}
                for part in path.parts
            )
        ]

    target = Path(normalized_scope)
    if not target.is_absolute():
        target = (vault / target).resolve()
    if path_is_file(target):
        return [target]
    if path_is_dir(target):
        return sorted(path for path in iter_markdown_files(target) if path_exists(path))
    return []


def _merge_aliases(existing: Any, *extra: str) -> list[str]:
    aliases = _normalize_aliases(existing)
    for item in extra:
        cleaned = _normalize_text(item)
        if cleaned and cleaned.lower() not in {value.lower() for value in aliases}:
            aliases.append(cleaned)
    return _dedupe_preserve(aliases)


def _propose_snapshot(snapshot: NoteSnapshot) -> dict[str, Any]:
    base_stem = _strip_hash_suffix(snapshot.path.stem)
    title_source = _normalize_text(snapshot.frontmatter.get("title") or snapshot.title or base_stem)
    proposed_stem = title_source or base_stem or snapshot.path.stem
    rename_needed = base_stem != snapshot.path.stem and proposed_stem != snapshot.path.stem
    if not rename_needed:
        proposed_stem = snapshot.path.stem
    target_path = snapshot.path.with_name(f"{proposed_stem}{snapshot.path.suffix}") if rename_needed else snapshot.path
    aliases = _merge_aliases(snapshot.frontmatter.get("aliases"), snapshot.path.stem, snapshot.title)
    if rename_needed:
        aliases = _merge_aliases(aliases, snapshot.path.stem, snapshot.title)
    frontmatter = dict(snapshot.frontmatter)
    frontmatter["title"] = _normalize_text(proposed_stem or title_source or snapshot.title or snapshot.path.stem)
    if aliases:
        frontmatter["aliases"] = aliases
    return {
        "source_path": str(snapshot.path),
        "source_rel_path": snapshot.rel_path,
        "current_stem": snapshot.path.stem,
        "target_stem": proposed_stem,
        "target_path": str(target_path),
        "rename_needed": rename_needed,
        "hash_suffix_removed": base_stem != snapshot.path.stem,
        "frontmatter": frontmatter,
        "frontmatter_changed": frontmatter != snapshot.frontmatter,
        "has_frontmatter": snapshot.has_frontmatter,
        "aliases": aliases,
    }


def _render_note(frontmatter: dict[str, Any], body: str) -> str:
    rendered_frontmatter = _dump_frontmatter(frontmatter)
    body_text = body.lstrip("\n")
    if rendered_frontmatter:
        if body_text:
            return f"{rendered_frontmatter}\n{body_text}"
        return rendered_frontmatter
    return body


def _write_note(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    write_text(path, _render_note(frontmatter, body), encoding="utf-8")


def _normalize_wikilink_target(raw: str) -> tuple[str, str, str]:
    target, pipe, display = raw.partition("|")
    path, anchor_sep, anchor = target.partition("#")
    return path.strip(), anchor if anchor_sep else "", display if pipe else ""


def _rewritten_link(raw: str, mapping: dict[str, str]) -> str | None:
    target, anchor, display = _normalize_wikilink_target(raw)
    normalized = target.replace("\\", "/").strip()
    stem = Path(normalized).stem
    candidates = {
        normalized,
        normalized.removesuffix(".md"),
        stem,
    }
    replacement: str | None = None
    for candidate in candidates:
        if candidate in mapping:
            replacement = mapping[candidate]
            break
    if replacement is None:
        return None
    new_target = replacement
    if anchor:
        new_target = f"{new_target}#{anchor}"
    if display:
        new_target = f"{new_target}|{display}"
    return f"[[{new_target}]]"


def _rewrite_links_in_text(text: str, mapping: dict[str, str]) -> tuple[str, int]:
    changed = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        rewritten = _rewritten_link(match.group(1), mapping)
        if rewritten is None:
            return match.group(0)
        changed += 1
        return rewritten

    return WIKILINK_RE.sub(repl, text), changed


def _rewrite_scope_links(vault: Path, mapping: dict[str, str], scope: str) -> int:
    if not mapping:
        return 0
    if scope == "full":
        target_paths = [
            path
            for path in sorted(iter_markdown_files(vault))
            if not any(
                part in {"state", "tests", ".obsidian", ".git", ".trash", ".venv", ".Otto-Realm", "Otto-Realm"}
                for part in path.parts
            )
        ]
    else:
        target = (vault / scope).resolve() if scope not in {"", "active"} and not Path(scope).is_absolute() else Path(scope)
        if path_is_file(target):
            target_paths = [target]
        elif path_is_dir(target):
            target_paths = sorted(path for path in iter_markdown_files(target) if path_exists(path))
        else:
            target_paths = [path for path in sorted(iter_markdown_files(vault)) if is_active_scope(path, vault)]

    rewritten_count = 0
    for path in target_paths:
        if not path_exists(path):
            continue
        text = read_text(path, encoding="utf-8", errors="replace")
        updated, changed = _rewrite_links_in_text(text, mapping)
        if changed:
            write_text(path, updated, encoding="utf-8")
            rewritten_count += changed
    return rewritten_count


def _report_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Notion Export Hygiene",
        "",
        f"- ts: `{result['ts']}`",
        f"- mode: `{result['mode']}`",
        f"- scope: `{result['scope']}`",
        f"- target_count: `{result['target_count']}`",
        f"- renamed_count: `{result['renamed_count']}`",
        f"- frontmatter_written_count: `{result['frontmatter_written_count']}`",
        f"- link_rewrite_count: `{result['link_rewrite_count']}`",
    ]
    lines.extend(["", "## Targets", ""])
    for item in result.get("results", []):
        flags = ", ".join(item.get("flags") or []) or "none"
        lines.append(
            f"- `{item['source_rel_path']}` -> `{item['target_rel_path']}` | flags={flags} | aliases={', '.join(item.get('aliases') or []) or 'none'}"
        )
    if not result.get("results"):
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _merge_handoff_latest(paths: Any, result: dict[str, Any]) -> Path:
    latest_path = paths.state_root / "handoff" / "latest.json"
    existing = read_json(latest_path, default={}) or {}
    artifacts = [str(item) for item in (existing.get("artifacts") or []) if str(item).strip()]
    artifacts.extend([result["report_path"], result["checkpoint_path"]])
    deduped: list[str] = []
    seen: set[str] = set()
    for item in artifacts:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    existing["updated_at"] = now_iso()
    existing["status"] = existing.get("status") or "ready"
    existing["notion_export_hygiene"] = {
        "ts": result["ts"],
        "mode": result["mode"],
        "scope": result["scope"],
        "target_count": result["target_count"],
        "renamed_count": result["renamed_count"],
        "frontmatter_written_count": result["frontmatter_written_count"],
        "link_rewrite_count": result["link_rewrite_count"],
        "report_path": result["report_path"],
        "checkpoint_path": result["checkpoint_path"],
        "pipeline_path": result.get("pipeline_path"),
    }
    existing["artifacts"] = deduped
    existing["notion_export_hygiene_next_actions"] = result.get("next_actions") or []
    write_json(latest_path, existing)
    return latest_path


def run_notion_export_hygiene(
    *,
    mode: str = "review",
    scope: str = "active",
    notes: list[str] | None = None,
    confirm: bool = False,
    rewrite_links: bool = True,
    reindex_after: bool = False,
) -> dict[str, Any]:
    logger = get_logger("otto.notion_export_hygiene")
    paths = load_paths()
    vault = paths.vault_path
    if vault is None:
        raise RuntimeError("Vault path is not configured")
    if not path_is_dir(vault):
        raise RuntimeError(f"Vault path is not a directory: {vault}")

    note_list = [str(item).strip() for item in (notes or []) if str(item).strip()]
    targets = _resolve_note_targets(vault, scope, note_list)
    if not targets:
        raise FileNotFoundError(f"No notes matched scope {scope!r}")

    plans: list[dict[str, Any]] = []
    for path in targets:
        if not path_exists(path):
            continue
        snapshot = _read_note(path, vault)
        plan = _propose_snapshot(snapshot)
        flags = []
        if plan["rename_needed"]:
            flags.append("hash_suffix")
        if not snapshot.has_frontmatter:
            flags.append("frontmatter_missing")
        if "title" not in snapshot.frontmatter or not str(snapshot.frontmatter.get("title") or "").strip():
            flags.append("title_missing")
        plan["flags"] = flags
        if plan["rename_needed"] or not snapshot.has_frontmatter or not str(snapshot.frontmatter.get("title") or "").strip():
            plans.append({**plan, "snapshot": snapshot})

    renamed_count = 0
    frontmatter_written_count = 0
    link_rewrite_count = 0
    next_actions: list[str] = []
    applied_paths: list[str] = []
    rename_map: dict[str, str] = {}

    for plan in plans:
        snapshot: NoteSnapshot = plan["snapshot"]
        frontmatter = dict(plan["frontmatter"])
        target_path = Path(plan["target_path"])
        target_rel_path = relative_path(target_path, vault).replace("\\", "/")
        if mode in {"apply"} and confirm:
            if plan["rename_needed"] and snapshot.path != target_path:
                if path_exists(target_path) and target_path != snapshot.path:
                    raise FileExistsError(f"Target path already exists: {target_path}")
                rename_path(snapshot.path, target_path)
                renamed_count += 1
                applied_paths.append(target_rel_path)
                rename_map[snapshot.path.stem] = target_path.stem
                rename_map[snapshot.rel_path.removesuffix(".md")] = target_rel_path.removesuffix(".md")
            _write_note(target_path, frontmatter, snapshot.body)
            frontmatter_written_count += 1
        else:
            if plan["rename_needed"]:
                next_actions.append(f"Rename {snapshot.rel_path} -> {target_rel_path}")
            if not snapshot.has_frontmatter or not str(snapshot.frontmatter.get("title") or "").strip():
                next_actions.append(f"Add frontmatter title to {snapshot.rel_path}")
        plan["target_path"] = str(target_path)
        plan["target_rel_path"] = target_rel_path
        plan["aliases"] = frontmatter.get("aliases") or []
        plan["frontmatter"] = frontmatter

    if mode in {"apply"} and confirm and rewrite_links and rename_map:
        link_rewrite_count = _rewrite_scope_links(vault, rename_map, scope)

    if mode == "verify":
        for plan in plans:
            snapshot = _read_note(Path(plan["target_path"]), vault)
            if plan["frontmatter"] != snapshot.frontmatter:
                next_actions.append(f"Verify note normalization for {plan['target_rel_path']}")
            if plan["rename_needed"] and path_exists(Path(plan["source_path"])):
                next_actions.append(f"Rename still pending for {plan['source_rel_path']}")

    ts = now_iso()
    report_dir = paths.artifacts_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = report_dir / "notion_export_hygiene.json"
    report_md_path = report_dir / "notion_export_hygiene.md"
    checkpoint_dir = paths.state_root / "run_journal" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_notion_export_hygiene.json"

    report_payload = {
        "ts": ts,
        "mode": mode,
        "scope": scope,
        "target_count": len(plans),
        "renamed_count": renamed_count,
        "frontmatter_written_count": frontmatter_written_count,
        "link_rewrite_count": link_rewrite_count,
        "applied_paths": applied_paths,
        "results": [
            {
                k: v
                for k, v in plan.items()
                if k not in {"snapshot", "frontmatter"}
            }
            for plan in plans
        ],
        "next_actions": _dedupe_preserve(next_actions),
    }

    write_json(report_json_path, report_payload)
    write_text(report_md_path, _report_markdown(report_payload), encoding="utf-8")
    write_json(checkpoint_path, report_payload)

    pipeline_result: dict[str, Any] | None = None
    pipeline_path: str | None = None
    if reindex_after and mode in {"apply"} and confirm:
        from ..pipeline import run_pipeline

        pipeline_result = run_pipeline(scope=scope, full=(scope == "full"))
        pipeline_path = str((paths.state_root / "checkpoints" / "pipeline.json").resolve())

    result = {
        **report_payload,
        "report_path": str(report_json_path),
        "report_md_path": str(report_md_path),
        "checkpoint_path": str(checkpoint_path),
        "pipeline": pipeline_result,
        "pipeline_path": pipeline_path,
        "status": "ok" if (mode != "apply" or confirm) else "warn",
    }
    _merge_handoff_latest(paths, result)
    logger.info(
        "[notion-export-hygiene] mode=%s targets=%s renamed=%s frontmatter=%s links=%s",
        mode,
        len(plans),
        renamed_count,
        frontmatter_written_count,
        link_rewrite_count,
    )
    return result
