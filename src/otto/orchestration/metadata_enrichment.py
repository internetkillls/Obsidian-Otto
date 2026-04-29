from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..config import load_metadata_enrichment_config, load_paths
from ..events import Event, EventBus, EVENT_METADATA_ENRICHMENT
from ..fs_utils import exists as path_exists, is_dir as path_is_dir, is_file as path_is_file, iter_markdown_files, read_text, relative_path, write_text
from ..logging_utils import append_jsonl, get_logger
from ..obsidian_commands import build_advanced_uri, build_file_target, open_uri
from ..otto_realm_bridge import load_legacy_otto_realm_context
from ..scoping import is_active_scope
from ..state import now_iso, read_json, write_json

FRONTMATTER_RE = re.compile(r"^\ufeff?---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_\-/.]+)")


@dataclass
class NoteSnapshot:
    path: Path
    rel_path: str
    title: str
    has_frontmatter: bool
    frontmatter: dict[str, Any]
    raw_frontmatter: str
    body: str
    body_tags: list[str]
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


def _normalize_tag(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("#"):
        text = text[1:]
    text = text.strip()
    return text or None


def _normalize_tag_list(value: Any) -> list[str]:
    items: list[str] = []
    if value is None:
        return []
    if isinstance(value, str):
        parts: list[Any] = [value]
    elif isinstance(value, (list, tuple, set)):
        parts = list(value)
    else:
        parts = [value]
    for part in parts:
        normalized = _normalize_tag(part)
        if normalized:
            items.append(normalized)
    return _dedupe_preserve(items)


def _normalize_aliases(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    return _dedupe_preserve(cleaned)


def _normalize_wikilinks_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    normalized: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        normalized.append(_normalize_wikilink_target(text))
    return _dedupe_preserve([item for item in normalized if item])


def _normalize_wikilink_target(value: str) -> str:
    text = value.strip()
    if "|" in text:
        text = text.split("|", 1)[0].strip()
    return text


def _extract_body_tags(body: str) -> list[str]:
    return _dedupe_preserve([match.group(1).strip() for match in TAG_RE.finditer(body)])


def _extract_body_wikilinks(body: str) -> list[str]:
    links: list[str] = []
    for match in WIKILINK_RE.finditer(body):
        target = _normalize_wikilink_target(match.group(1))
        if target:
            links.append(target)
    return _dedupe_preserve(links)


def _title_from_path(path: Path) -> str:
    title = path.stem.replace("-", " ").replace("_", " ").strip()
    return title or path.name


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


def _read_note(path: Path, vault: Path) -> NoteSnapshot:
    text = read_text(path, encoding="utf-8")
    frontmatter, raw_frontmatter, body = _split_frontmatter(text)
    return NoteSnapshot(
        path=path,
        rel_path=relative_path(path, vault).replace("\\", "/"),
        title=str(frontmatter.get("title") or _title_from_path(path)).strip(),
        has_frontmatter=bool(frontmatter),
        frontmatter=frontmatter,
        raw_frontmatter=raw_frontmatter,
        body=body,
        body_tags=_extract_body_tags(body),
        wikilinks=_extract_body_wikilinks(body),
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


def _extract_qid(frontmatter: dict[str, Any]) -> str | None:
    for key in ("wikidata_id", "wikidata", "wikidata_qid", "qid"):
        value = frontmatter.get(key)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            candidates = [str(item).strip() for item in value if str(item).strip()]
        else:
            candidates = [str(value).strip()]
        for candidate in candidates:
            match = re.search(r"Q\d+", candidate, flags=re.IGNORECASE)
            if match:
                return match.group(0).upper()
    return None


def _wikidata_url(qid: str, api_base: str) -> str:
    parsed = urllib.parse.urlparse(api_base)
    if parsed.scheme and parsed.netloc:
        base = f"{parsed.scheme}://{parsed.netloc}"
    else:
        base = "https://www.wikidata.org"
    return f"{base}/wiki/Special:EntityData/{qid}.json"


def _fetch_wikidata_entity(qid: str, api_base: str, user_agent: str, timeout_seconds: int = 20) -> dict[str, Any]:
    url = _wikidata_url(qid, api_base)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent or "Obsidian-Otto Metadata Enrichment"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    entity = (((payload or {}).get("entities") or {}).get(qid)) or {}
    labels = entity.get("labels") or {}
    descriptions = entity.get("descriptions") or {}
    aliases = entity.get("aliases") or {}

    def _best_text(bundle: dict[str, Any]) -> str | None:
        for lang in ("en", "id"):
            entry = bundle.get(lang)
            if entry and isinstance(entry, dict):
                text = str(entry.get("value") or "").strip()
                if text:
                    return text
        for entry in bundle.values():
            if isinstance(entry, dict):
                text = str(entry.get("value") or "").strip()
                if text:
                    return text
        return None

    def _alias_list(bundle: dict[str, Any]) -> list[str]:
        result: list[str] = []
        for lang in ("en", "id"):
            entries = bundle.get(lang) or []
            if isinstance(entries, list):
                for item in entries:
                    if isinstance(item, dict):
                        text = str(item.get("value") or "").strip()
                        if text:
                            result.append(text)
        if not result:
            for entries in bundle.values():
                if isinstance(entries, list):
                    for item in entries:
                        if isinstance(item, dict):
                            text = str(item.get("value") or "").strip()
                            if text:
                                result.append(text)
        return _dedupe_preserve(result)

    return {
        "qid": qid,
        "label": _best_text(labels),
        "description": _best_text(descriptions),
        "aliases": _alias_list(aliases),
        "url": f"https://www.wikidata.org/wiki/{qid}",
        "source_url": url,
    }


def _backend_config() -> dict[str, Any]:
    return load_metadata_enrichment_config().get("metadata_enrichment", {})


def _backend_write_policy(backend: str) -> dict[str, bool]:
    cfg = _backend_config().get("backends", {}).get(backend, {})
    policy = cfg.get("write", {})
    return {
        "tags": bool(policy.get("tags", False)),
        "aliases": bool(policy.get("aliases", False)),
        "wikilinks": bool(policy.get("wikilinks", False)),
        "entity_fields": bool(policy.get("entity_fields", False)),
    }


def _backend_label(backend: str) -> str:
    cfg = _backend_config().get("backends", {}).get(backend, {})
    return str(cfg.get("label") or backend).strip() or backend


def _backend_command_labels(backend: str) -> dict[str, str]:
    cfg = _backend_config().get("backends", {}).get(backend, {})
    labels = cfg.get("command_labels") or {}
    if not isinstance(labels, dict):
        return {}
    return {str(k): str(v) for k, v in labels.items() if str(v).strip()}


def _execution_config() -> dict[str, Any]:
    cfg = _backend_config().get("execution", {})
    return cfg if isinstance(cfg, dict) else {}


def _backend_priority(mode: str, entity_present: bool) -> list[str]:
    cfg = _backend_config()
    if mode == "entity" or entity_present:
        return list(cfg.get("entity_backend_priority") or ["wikidata_importer", "metadata_menu", "metaedit"])
    return list(cfg.get("core_backend_priority") or ["metadata_menu", "metaedit"])


def _select_backend(mode: str, *, entity_present: bool, explicit_backend: str | None = None) -> str:
    backends = _backend_config().get("backends", {})
    if explicit_backend and explicit_backend != "auto":
        return explicit_backend
    for backend in _backend_priority(mode, entity_present):
        if bool((backends.get(backend) or {}).get("enabled", True)):
            return backend
    return _backend_priority(mode, entity_present)[0]


def _normalize_frontmatter(snapshot: NoteSnapshot, *, backend: str, qid_payload: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    policy = _backend_write_policy(backend)
    frontmatter = dict(snapshot.frontmatter)
    changes: list[str] = []

    raw_tags = frontmatter.get("tags")
    observed_tags = _dedupe_preserve(_normalize_tag_list(frontmatter.get("tags")) + snapshot.body_tags)
    current_tags = _normalize_tag_list(raw_tags)
    if policy["tags"] and observed_tags != current_tags:
        frontmatter["tags"] = observed_tags
        changes.append("tags")

    raw_aliases = frontmatter.get("aliases")
    aliases = _normalize_aliases(raw_aliases)
    if policy["aliases"] and raw_aliases is not None and raw_aliases != aliases:
        frontmatter["aliases"] = aliases
        changes.append("aliases")

    raw_wikilinks = frontmatter.get("wikilinks")
    if policy["wikilinks"] and raw_wikilinks is not None:
        normalized_links = _normalize_wikilinks_list(raw_wikilinks)
        if raw_wikilinks != normalized_links:
            frontmatter["wikilinks"] = normalized_links
            changes.append("wikilinks")

    if qid_payload and policy["entity_fields"]:
        entity_fields = {
            "wikidata_id": qid_payload.get("qid"),
            "wikidata_label": qid_payload.get("label"),
            "wikidata_description": qid_payload.get("description"),
            "wikidata_aliases": qid_payload.get("aliases") or [],
            "wikidata_url": qid_payload.get("url"),
            "wikidata_last_fetched": now_iso(),
        }
        for key, value in entity_fields.items():
            if value in (None, "", []):
                continue
            if frontmatter.get(key) != value:
                frontmatter[key] = value
                changes.append(key)

    return frontmatter, changes, {
        "observed_tags": observed_tags,
        "normalized_tags": _normalize_tag_list(frontmatter.get("tags")),
        "wikilinks": snapshot.wikilinks,
        "aliases": _normalize_aliases(frontmatter.get("aliases")),
    }


def _write_note(snapshot: NoteSnapshot, frontmatter: dict[str, Any]) -> bool:
    original = read_text(snapshot.path, encoding="utf-8")
    body = snapshot.body
    new_text = _dump_frontmatter(frontmatter)
    if new_text:
        new_text = f"{new_text}\n{body.lstrip()}" if body.strip() else new_text
        if not new_text.endswith("\n"):
            new_text += "\n"
    else:
        new_text = original
    if new_text == original:
        return False
    write_text(snapshot.path, new_text, encoding="utf-8")
    return True


def _verify_note(snapshot: NoteSnapshot, expected_frontmatter: dict[str, Any], vault: Path) -> dict[str, Any]:
    current = _read_note(snapshot.path, vault)
    current_frontmatter = current.frontmatter
    matches = current_frontmatter == expected_frontmatter
    return {
        "matches": matches,
        "current_frontmatter": current_frontmatter,
        "expected_frontmatter": expected_frontmatter,
    }


def _note_report(snapshot: NoteSnapshot, backend: str, mode: str, normalized: dict[str, Any], changes: list[str], qid_payload: dict[str, Any] | None) -> dict[str, Any]:
    frontmatter = snapshot.frontmatter
    notes: list[str] = []
    conflicts: list[str] = []
    unresolved: list[str] = []

    if not snapshot.has_frontmatter:
        notes.append("frontmatter_missing")
    if snapshot.body_tags and not normalized["normalized_tags"]:
        unresolved.append("tags_from_body_unresolved")
    if mode == "entity" and not qid_payload:
        unresolved.append("wikidata_entity_missing")

    if frontmatter.get("tags") and normalized["normalized_tags"] and _normalize_tag_list(frontmatter.get("tags")) != normalized["normalized_tags"]:
        conflicts.append("tags_normalized")
    if snapshot.wikilinks:
        notes.append("wikilinks_observed")

    return {
        "path": snapshot.rel_path,
        "title": snapshot.title,
        "backend": backend,
        "backend_label": _backend_label(backend),
        "command_labels": _backend_command_labels(backend),
        "mode": mode,
        "has_frontmatter": snapshot.has_frontmatter,
        "frontmatter_keys": sorted(str(key) for key in frontmatter.keys()),
        "observed_tags": normalized["observed_tags"],
        "normalized_tags": normalized["normalized_tags"],
        "wikilinks": snapshot.wikilinks,
        "aliases": normalized["aliases"],
        "changes": changes,
        "conflicts": conflicts,
        "unresolved": unresolved,
        "qid": qid_payload.get("qid") if qid_payload else _extract_qid(frontmatter),
        "wikidata": qid_payload,
        "notes": notes,
    }


def _build_command_plan(paths: Any, snapshot: NoteSnapshot, backend: str, mode: str) -> dict[str, Any] | None:
    labels = _backend_command_labels(backend)
    command_name = labels.get(mode)
    if not command_name:
        return None

    execution_cfg = _execution_config()
    uri_scheme = str(execution_cfg.get("uri_scheme") or "advanced-uri").strip().lower()
    vault_name = str((paths.vault_path.name if paths.vault_path else paths.repo_root.name) or "").strip() or "Obsidian Vault"
    note_target = build_file_target(snapshot.path, paths.vault_path)

    plan: dict[str, Any] = {
        "backend": backend,
        "backend_label": _backend_label(backend),
        "mode": mode,
        "command_name": command_name,
        "note_target": note_target,
        "uri_scheme": uri_scheme,
    }

    if uri_scheme == "advanced-uri":
        plan["uri"] = build_advanced_uri(
            vault_name=vault_name,
            command_name=command_name,
            filepath=note_target,
        )
    return plan


def _dispatch_command(plan: dict[str, Any], *, mode: str, confirm: bool, target_count: int) -> dict[str, Any]:
    if mode in {"apply", "entity"}:
        return {
            "ok": False,
            "skipped": True,
            "reason": "write-mode-uses-internal-writer",
        }
    if target_count != 1:
        return {
            "ok": False,
            "skipped": True,
            "reason": "dispatch-single-target-only",
        }
    uri = str(plan.get("uri") or "").strip()
    if not uri:
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing-uri",
        }
    return open_uri(uri)


def _active_scope_count(vault: Path, targets: list[Path]) -> int:
    return sum(1 for path in targets if is_active_scope(path, vault))


def _report_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Metadata Enrichment",
        "",
        f"- ts: `{result['ts']}`",
        f"- mode: `{result['mode']}`",
        f"- backend: `{result['backend']['name']}`",
        f"- scope: `{result['scope']}`",
        f"- target_count: `{result['target_count']}`",
        f"- changed_count: `{result['changed_count']}`",
        f"- verified_count: `{result['verified_count']}`",
        f"- unresolved_count: `{result['unresolved_count']}`",
    ]
    if result.get("legacy_otto_realm"):
        legacy = result["legacy_otto_realm"]
        lines.extend(
            [
                "",
                "## Legacy Otto-Realm Bridge",
                "",
                f"- roots: `{', '.join(legacy.get('roots') or []) or 'n/a'}`",
                f"- artifact_count: `{legacy.get('artifact_count', 0)}`",
            ]
        )
    lines.extend(["", "## Targets", ""])
    for item in result.get("results", []):
        changes = ", ".join(item.get("changes") or []) or "none"
        unresolved = ", ".join(item.get("unresolved") or []) or "none"
        lines.append(f"- `{item['path']}` | backend={item['backend_label']} | changes={changes} | unresolved={unresolved}")
    if not result.get("results"):
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _merge_handoff_latest(paths: Any, result: dict[str, Any]) -> Path:
    latest_path = paths.state_root / "handoff" / "latest.json"
    existing = read_json(latest_path, default={}) or {}
    artifacts = [str(item) for item in (existing.get("artifacts") or []) if str(item).strip()]
    artifacts.extend([result["report_path"], result["checkpoint_path"]])
    bridge_path = result.get("bridge_path")
    if bridge_path:
        artifacts.append(str(bridge_path))
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
    existing["metadata_enrichment"] = {
        "ts": result["ts"],
        "mode": result["mode"],
        "backend": result["backend"],
        "target_count": result["target_count"],
        "changed_count": result["changed_count"],
        "verified_count": result["verified_count"],
        "unresolved_count": result["unresolved_count"],
        "report_path": result["report_path"],
        "checkpoint_path": result["checkpoint_path"],
        "bridge_path": bridge_path,
        "legacy_otto_realm": result.get("legacy_otto_realm"),
    }
    existing["artifacts"] = deduped
    existing["metadata_enrichment_next_actions"] = result.get("next_actions") or []
    existing["metadata_enrichment_latest_report"] = result["report_path"]
    existing["metadata_enrichment_bridge_path"] = bridge_path
    write_json(latest_path, existing)
    return latest_path


def _write_bridge_packet(paths: Any, result: dict[str, Any]) -> Path:
    packet = {
        "source": "metadata-enrichment",
        "role": "b",
        "status": "handoff",
        "updated_at": result["ts"],
        "summary": f"Metadata enrichment {result['mode']} run over {result['target_count']} note(s)",
        "artifacts": [result["report_path"], result["checkpoint_path"]],
        "next_actions": result.get("next_actions") or [],
        "next_action": (result.get("next_actions") or [None])[0],
        "language": "en",
        "mode": result["mode"],
        "backend": result["backend"],
        "legacy_otto_realm": result.get("legacy_otto_realm"),
    }
    out_dir = paths.state_root / "handoff" / "from_cowork"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    out_path = out_dir / f"{stamp}_b_handoff.json"
    write_json(out_path, packet)
    append_jsonl(out_dir / "b_metadata_enrichment.jsonl", packet)
    return out_path


def _resolve_targets_and_scope(paths: Any, scope: str, notes: list[str]) -> tuple[list[Path], str]:
    vault = paths.vault_path
    if vault is None:
        raise RuntimeError("Vault path is not configured")
    if not path_is_dir(vault):
        raise RuntimeError(f"Vault path is not a directory: {vault}")

    resolved_scope = scope or "active"
    targets = _resolve_note_targets(vault, resolved_scope, notes)
    return targets, resolved_scope


def run_metadata_enrichment(
    *,
    mode: str = "review",
    scope: str = "active",
    notes: list[str] | None = None,
    backend: str = "auto",
    confirm: bool = False,
    verify_after: bool = True,
    dispatch_command: bool = False,
) -> dict[str, Any]:
    logger = get_logger("otto.metadata_enrichment")
    paths = load_paths()
    config = load_metadata_enrichment_config().get("metadata_enrichment", {})
    note_list = [str(item).strip() for item in (notes or []) if str(item).strip()]
    targets, resolved_scope = _resolve_targets_and_scope(paths, scope, note_list)
    if not targets:
        raise FileNotFoundError(f"No notes matched scope {resolved_scope!r}")

    legacy_otto_realm = load_legacy_otto_realm_context(paths, load_metadata_enrichment_config())
    selected_backend = _select_backend(mode, entity_present=(mode == "entity"), explicit_backend=backend)
    backend_label = _backend_label(selected_backend)
    api_cfg = config.get("wikidata", {}) if isinstance(config.get("wikidata", {}), dict) else {}
    user_agent = str(api_cfg.get("user_agent") or "Obsidian-Otto Metadata Enrichment")
    api_base = str(api_cfg.get("api_base") or "https://www.wikidata.org/w/api.php")

    results: list[dict[str, Any]] = []
    changed_count = 0
    verified_count = 0
    blocked_count = 0
    unresolved_count = 0
    applied_paths: list[str] = []
    next_actions: list[str] = []
    dispatched_commands: list[dict[str, Any]] = []

    for path in targets:
        snapshot = _read_note(path, paths.vault_path)
        qid = _extract_qid(snapshot.frontmatter)
        qid_payload = None
        if mode == "entity":
            if qid:
                try:
                    qid_payload = _fetch_wikidata_entity(qid, api_base=api_base, user_agent=user_agent)
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                    logger.warning("[metadata-enrichment] Wikidata fetch failed for %s: %s", snapshot.rel_path, exc)
                    qid_payload = None
            else:
                unresolved_count += 1

        normalized_frontmatter, changes, normalized = _normalize_frontmatter(
            snapshot,
            backend=selected_backend,
            qid_payload=qid_payload,
        )

        note_result = _note_report(snapshot, selected_backend, mode, normalized, changes, qid_payload)
        note_result["candidate_frontmatter"] = normalized_frontmatter
        command_plan = _build_command_plan(paths, snapshot, selected_backend, mode)
        if command_plan:
            note_result["command_plan"] = command_plan

        if note_result["unresolved"]:
            unresolved_count += len(note_result["unresolved"])
        if changes:
            note_result["candidate_changes"] = changes

        write_allowed = mode in {"apply", "entity"}
        if write_allowed and not confirm:
            note_result["blocked"] = True
            note_result["block_reason"] = "confirmation-required"
            blocked_count += 1
            next_actions.append(f"Confirm {mode} for {snapshot.rel_path}")
        elif write_allowed and confirm:
            note_result["blocked"] = False
            wrote = _write_note(snapshot, normalized_frontmatter)
            note_result["written"] = wrote
            if wrote:
                changed_count += 1
                applied_paths.append(snapshot.rel_path)
            if verify_after:
                verification = _verify_note(snapshot, normalized_frontmatter, paths.vault_path)
                note_result["verification"] = verification
                if verification["matches"]:
                    verified_count += 1
                else:
                    note_result["verification"]["drift"] = True
        else:
            note_result["blocked"] = False
            if mode == "verify":
                verification = _verify_note(snapshot, normalized_frontmatter, paths.vault_path)
                note_result["verification"] = verification
                if verification["matches"]:
                    verified_count += 1
                else:
                    next_actions.append(f"Apply normalization to {snapshot.rel_path}")

        if dispatch_command and command_plan:
            dispatch_result = _dispatch_command(command_plan, mode=mode, confirm=confirm, target_count=len(targets))
            note_result["command_dispatch"] = dispatch_result
            if dispatch_result.get("ok"):
                dispatched_commands.append(
                    {
                        "path": snapshot.rel_path,
                        "uri": command_plan.get("uri"),
                        "backend": selected_backend,
                        "mode": mode,
                    }
                )

        results.append(note_result)

    ts = now_iso()
    report_dir = paths.artifacts_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = report_dir / "metadata_enrichment.json"
    report_md_path = report_dir / "metadata_enrichment.md"
    checkpoint_dir = paths.state_root / "run_journal" / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_metadata_enrichment.json"

    report_payload = {
        "ts": ts,
        "mode": mode,
        "scope": resolved_scope,
        "backend": {
            "name": selected_backend,
            "label": backend_label,
            "command_labels": _backend_command_labels(selected_backend),
        },
        "target_count": len(targets),
        "changed_count": changed_count,
        "verified_count": verified_count,
        "blocked_count": blocked_count,
        "unresolved_count": unresolved_count,
        "applied_paths": applied_paths,
        "dispatched_commands": dispatched_commands,
        "legacy_otto_realm": legacy_otto_realm,
        "results": results,
        "next_actions": _dedupe_preserve(next_actions),
    }

    write_json(report_json_path, report_payload)
    report_md_path.write_text(_report_markdown(report_payload), encoding="utf-8")
    write_json(checkpoint_path, report_payload)

    bus = EventBus(paths)
    bus.publish(
        Event(
            type=EVENT_METADATA_ENRICHMENT,
            source="metadata-enrichment",
            payload={
                "mode": mode,
                "backend": selected_backend,
                "target_count": len(targets),
                "changed_count": changed_count,
                "verified_count": verified_count,
                "blocked_count": blocked_count,
                "unresolved_count": unresolved_count,
                "report_path": str(report_json_path),
            },
        )
    )

    bridge_path = _write_bridge_packet(paths, {**report_payload, "report_path": str(report_json_path), "checkpoint_path": str(checkpoint_path)})
    result = {
        **report_payload,
        "report_path": str(report_json_path),
        "report_md_path": str(report_md_path),
        "checkpoint_path": str(checkpoint_path),
        "bridge_path": str(bridge_path),
        "status": "ok" if blocked_count == 0 else ("warn" if changed_count or verified_count else "blocked"),
    }
    _merge_handoff_latest(paths, result)
    logger.info(
        "[metadata-enrichment] mode=%s backend=%s targets=%s changed=%s verified=%s",
        mode,
        selected_backend,
        len(targets),
        changed_count,
        verified_count,
    )
    return result
