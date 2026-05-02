from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from _active_scope import is_active_scope
from _scarcity_common import (
    CLUSTERS,
    FRONTMATTER_RE,
    SCARCITY_FAMILY_TO_CLUSTER,
    dedupe_preserve,
    normalize_list,
    normalize_label_key,
    normalize_scalar,
    now_iso,
    parse_frontmatter,
    read_note_metadata,
    write_json,
)

PILLARS = ("SCARCITY", "ORIENTATION", "ALLOCATION")
FAMILY_MOC_FILES = {
    "orientation": ("ORIENTATION-FAMILY", "ORIENTATION"),
    "allocation": ("ALLOCATION-FAMILY", "ALLOCATION"),
}
KIND_TO_PREFIX = {"scarcity": "LACK-", "orientation": "TO-", "allocation": "ALLO-"}
KIND_TO_DIR = {"scarcity": "scarcity", "orientation": "orientation", "allocation": "allocation"}
TOKEN_RE = re.compile(r"[a-z0-9]+")
COMMON_SEMANTIC_STOPWORDS = {
    "dan",
    "atau",
    "yang",
    "untuk",
    "dari",
    "dengan",
    "pada",
    "ini",
    "itu",
    "di",
    "ke",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "across",
    "about",
}
DEFAULT_SEMANTIC_STOPWORDS: set[str] = set(COMMON_SEMANTIC_STOPWORDS)
DEFAULT_NOISE_WORDS: set[str] = set()
ROUTE_LIKE_WORDS = {
    "archive",
    "archived",
    "draft",
    "record",
    "session",
    "summary",
    "summarizes",
    "variant",
    "duplicate",
    "latest",
    "current",
    "reference",
    "notes",
    "chapter",
    "april",
}


@dataclass(frozen=True)
class PolicyDecision:
    kind: str
    value: str
    normalized_key: str
    decision: str
    reason: str
    merge_target: str | None
    protected: bool
    score_breakdown: dict[str, float | int | bool]


@dataclass(frozen=True)
class EntityRef:
    kind: str
    value: str
    label: str
    slug: str
    file_path: Path
    moc_target: str
    pillar: str


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _slugify(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    cleaned = cleaned.strip("-")
    return (cleaned[:72] if cleaned else "unnamed")


def _normalize_value(prefix: str, value: str) -> tuple[str, str]:
    raw = (value or "").strip()
    if not raw:
        return "unnamed", "unnamed"
    if raw.upper().startswith(prefix):
        suffix = raw[len(prefix) :].strip().lstrip("-_ ")
        label = suffix.replace("-", " ").strip() or raw
        return _slugify(suffix or raw), label
    return _slugify(raw), raw


def _split_frontmatter_raw(text: str) -> tuple[str, str, dict[str, Any]]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return "", text, {}
    fm_raw = text[: match.end()]
    body = text[match.end() :]
    return fm_raw, body, parse_frontmatter(match.group(1))


def _has_wikilink(text: str, target_no_ext: str, basename: str) -> bool:
    left = f"[[{target_no_ext}"
    short = f"[[{basename}"
    return left in text or short in text


def _append_links_block(text: str, heading: str, links: list[str]) -> str:
    trimmed = text.rstrip()
    block_lines = [f"## {heading}"] + [f"- {link}" for link in links]
    block = "\n".join(block_lines)
    if not trimmed:
        return block + "\n"
    return f"{trimmed}\n\n{block}\n"


def _read_frontmatter_field(path: Path, field: str) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    _, _, fm = _split_frontmatter_raw(text)
    value = fm.get(field)
    if value is None:
        return None
    return str(value).strip() or None


def _existing_entities(kind_dir: Path, prefix: str) -> tuple[dict[str, Path], dict[str, Path]]:
    by_slug: dict[str, Path] = {}
    by_label: dict[str, Path] = {}
    if not kind_dir.exists():
        return by_slug, by_label
    for path in kind_dir.glob(f"{prefix}*.md"):
        slug = path.stem.strip()
        if slug:
            by_slug[slug.lower()] = path
        label = _read_frontmatter_field(path, "label")
        if label:
            by_label[label.strip().lower()] = path
    return by_slug, by_label


def _ensure_file_with_links(
    path: Path,
    heading: str,
    required_links: list[str],
    writeback: bool,
    budget_name: str,
    budgets: dict[str, int],
    counters: dict[str, int],
    deferred: list[dict[str, str]],
) -> tuple[bool, list[str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    except OSError as exc:
        deferred.append({"type": "io-error", "path": str(path), "reason": str(exc)})
        return False, []

    missing = []
    for link in required_links:
        target = link[2:-2] if link.startswith("[[") and link.endswith("]]") else link
        if target not in text:
            missing.append(link)
    if not missing:
        return False, []

    if not writeback:
        deferred.append({"type": "read-only", "path": str(path), "reason": f"missing {len(missing)} link(s)"})
        return False, missing
    if counters[budget_name] >= budgets[budget_name]:
        deferred.append({"type": "budget", "path": str(path), "reason": f"{budget_name} budget exhausted"})
        return False, missing

    updated = _append_links_block(text, heading, missing)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated, encoding="utf-8")
    counters[budget_name] += 1
    return True, missing


def _build_entity_content(ref: EntityRef) -> str:
    if ref.kind == "scarcity":
        return (
            "---\n"
            "type: scarcity-entity\n"
            f"label: {ref.value}\n"
            f"slug: {ref.slug}\n"
            f"cluster: {ref.moc_target}\n"
            f"last_generated: {now_iso()}\n"
            "---\n"
            f"# {ref.label}\n\n"
            "## Roll-Up\n"
            f"- Family MOC: [[{ref.moc_target}]]\n"
            f"- Pillar MOC: [[{ref.pillar}]]\n"
        )
    if ref.kind == "orientation":
        return (
            "---\n"
            "type: orientation-entity\n"
            f"label: {ref.value}\n"
            f"slug: {ref.slug}\n"
            f"family: {ref.moc_target}\n"
            f"last_generated: {now_iso()}\n"
            "---\n"
            f"# {ref.label}\n\n"
            "## Roll-Up\n"
            f"- Family MOC: [[{ref.moc_target}]]\n"
            f"- Pillar MOC: [[{ref.pillar}]]\n"
        )
    return (
        "---\n"
        "type: allocation-entity\n"
        f"label: {ref.value}\n"
        f"slug: {ref.slug}\n"
        f"family: {ref.moc_target}\n"
        f"last_generated: {now_iso()}\n"
        "---\n"
        f"# {ref.label}\n\n"
        "## Roll-Up\n"
        f"- Family MOC: [[{ref.moc_target}]]\n"
        f"- Pillar MOC: [[{ref.pillar}]]\n"
    )


def _build_family_moc(kind: str, family_name: str, pillar: str) -> str:
    title = "Orientation Family MOC" if kind == "orientation" else "Allocation Family MOC"
    kind_field = "orientation-family" if kind == "orientation" else "allocation-family"
    return (
        "---\n"
        f"type: {kind_field}\n"
        f"family: {family_name}\n"
        f"last_generated: {now_iso()}\n"
        "---\n"
        f"# {family_name}\n\n"
        f"> {title}\n\n"
        "## Roll-Up\n"
        f"- Pillar MOC: [[{pillar}]]\n"
    )


def _build_pillar_moc(pillar: str) -> str:
    if pillar == "SCARCITY":
        children = "\n".join(f"- [[{cluster}]]" for cluster in CLUSTERS)
    elif pillar == "ORIENTATION":
        children = "- [[ORIENTATION-FAMILY]]"
    else:
        children = "- [[ALLOCATION-FAMILY]]"
    return (
        "---\n"
        "type: pillar-moc\n"
        f"pillar: {pillar}\n"
        f"last_generated: {now_iso()}\n"
        "---\n"
        f"# {pillar}\n\n"
        "## Child MOCs\n"
        f"{children}\n"
    )


def _build_cluster_moc(cluster: str) -> str:
    return (
        "---\n"
        "type: MOC\n"
        f"cluster: {cluster}\n"
        f"last_generated: {now_iso()}\n"
        "---\n"
        f"# {cluster}\n\n"
        "## Roll-Up\n"
        "- Pillar MOC: [[SCARCITY]]\n"
    )


def _acquire_lock(lock_path: Path, stale_seconds: int) -> tuple[bool, str]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        age = max(0, int(now_iso_to_epoch() - lock_path.stat().st_mtime))
        if age > stale_seconds:
            lock_path.unlink(missing_ok=True)
        else:
            return False, f"active lock ({age}s)"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True, "acquired"
    except FileExistsError:
        return False, "active lock"


def now_iso_to_epoch() -> float:
    import time

    return time.time()


def _load_cursor(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("next_index", 0))
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return 0


def _save_cursor(path: Path, next_index: int, note_count: int) -> None:
    payload = {"ts": now_iso(), "next_index": next_index, "note_count": note_count}
    write_json(path, payload)


def _enumerate_target_notes(vault: Path, scope: str) -> list[Path]:
    extra_exclude_dirs = {"node_modules", "dist", "build", "vendor", ".github", ".gitlab", ".vscode", ".idea"}
    candidates: list[Path] = []
    for note in vault.rglob("*.md"):
        rel = note.relative_to(vault)
        rel_parts = [part.lower() for part in rel.parts]
        if any(part in extra_exclude_dirs for part in rel_parts):
            continue
        if any(part.startswith(".") and part != ".otto-realm" for part in rel_parts):
            continue
        if scope == "active" and not is_active_scope(note, vault):
            continue
        if scope == "full" and any(part in {"state", "tests", ".obsidian", ".git", ".trash", ".venv"} for part in note.parts):
            continue
        meta = read_note_metadata(note, vault)
        if meta["scarcity"] or meta["orientation"] or meta["allocation"]:
            candidates.append(note)
    candidates.sort(key=lambda p: str(p.relative_to(vault)).lower())
    return candidates


def _pick_batch(notes: list[Path], start_idx: int, batch_size: int) -> tuple[list[Path], int]:
    if not notes:
        return [], 0
    start = start_idx % len(notes)
    take = min(batch_size, len(notes))
    selected = [notes[(start + i) % len(notes)] for i in range(take)]
    next_index = (start + take) % len(notes)
    return selected, next_index


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _tokens(value: str, block_words: set[str], go_words: set[str]) -> set[str]:
    raw = value.lower()
    result: set[str] = set()
    for token in TOKEN_RE.findall(raw):
        if token in go_words:
            result.add(token)
            continue
        if len(token) < 3:
            continue
        if token in block_words:
            continue
        result.add(token)
    return result


def _semantic_similarity(a: str, b: str, block_words: set[str], go_words: set[str]) -> float:
    ta = _tokens(a, block_words, go_words)
    tb = _tokens(b, block_words, go_words)
    if not ta or not tb:
        return 0.0
    inter = len(ta.intersection(tb))
    union = len(ta.union(tb))
    base = float(inter / union) if union else 0.0
    if not go_words:
        return base
    go_inter = len((ta.intersection(tb)).intersection(go_words))
    go_norm = max(1, len(ta.intersection(go_words)), len(tb.intersection(go_words)))
    bonus = 0.25 * (go_inter / go_norm) if go_inter else 0.0
    return min(1.0, base + bonus)


def _best_semantic_match(
    value: str,
    existing_by_label: dict[str, Path],
    threshold: float,
    block_words: set[str],
    go_words: set[str],
) -> Path | None:
    best_path: Path | None = None
    best_score = 0.0
    for label_lc, path in existing_by_label.items():
        score = _semantic_similarity(value, label_lc, block_words, go_words)
        if score > best_score:
            best_score = score
            best_path = path
    if best_path is None:
        return None
    return best_path if best_score >= threshold else None


def _entity_ignore_key(kind: str, value: str) -> str:
    digest = hashlib.sha1(f"{kind}|{value.strip().lower()}".encode("utf-8")).hexdigest()[:16]
    return f"entity:{kind}:{digest}"


def _note_ignore_key(note_rel: str) -> str:
    digest = hashlib.sha1(note_rel.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"note:{digest}"


def _load_ignore_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"run_count": 0, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"run_count": 0, "entries": {}}
    if not isinstance(data, dict):
        return {"run_count": 0, "entries": {}}
    run_count = int(data.get("run_count", 0))
    entries = data.get("entries", {})
    if not isinstance(entries, dict):
        entries = {}
    return {"run_count": run_count, "entries": entries}


def _is_ignored(ignore_state: dict[str, Any], key: str, run_count: int) -> bool:
    entry = ignore_state["entries"].get(key)
    if not isinstance(entry, dict):
        return False
    defer_until = int(entry.get("defer_until_run", 0))
    return run_count < defer_until


def _mark_ignored(
    ignore_state: dict[str, Any],
    key: str,
    run_count: int,
    cooldown_runs: int,
    reason: str,
) -> None:
    ignore_state["entries"][key] = {
        "defer_until_run": run_count + max(cooldown_runs, 1),
        "reason": reason,
        "updated_at": now_iso(),
    }


def _clear_ignored(ignore_state: dict[str, Any], key: str) -> None:
    ignore_state["entries"].pop(key, None)


def _load_noise_words(path: Path) -> tuple[set[str], set[str], dict[str, Any]]:
    if not path.exists():
        defaults = {
            "version": "1.0",
            "use_common_stopwords": True,
            "common_stopwords": sorted(COMMON_SEMANTIC_STOPWORDS),
            "custom_stopwords": [],
            "noise_words": sorted(DEFAULT_NOISE_WORDS),
            "go_words": [],
            "notes": "Update via your own n-gram pipeline; this file is dynamic and editable.",
        }
        write_json(path, defaults)
        merged = set(DEFAULT_SEMANTIC_STOPWORDS).union(DEFAULT_NOISE_WORDS)
        return merged, set(), defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        merged = set(DEFAULT_SEMANTIC_STOPWORDS).union(DEFAULT_NOISE_WORDS)
        return merged, set(), {"version": "1.0", "custom_stopwords": [], "noise_words": [], "go_words": []}
    use_common = bool(data.get("use_common_stopwords", True))
    common_stopwords = {
        str(x).strip().lower()
        for x in (data.get("common_stopwords") or COMMON_SEMANTIC_STOPWORDS)
        if str(x).strip()
    } if use_common else set()
    custom_stopwords = {
        str(x).strip().lower()
        for x in (data.get("custom_stopwords") or [])
        if str(x).strip()
    }
    noise_words = {
        str(x).strip().lower()
        for x in (data.get("noise_words") or [])
        if str(x).strip()
    }
    go_words = {
        str(x).strip().lower()
        for x in (data.get("go_words") or [])
        if str(x).strip()
    }
    merged = set(DEFAULT_NOISE_WORDS).union(common_stopwords).union(custom_stopwords).union(noise_words)
    merged = {w for w in merged if w and w not in go_words}
    return merged, go_words, data if isinstance(data, dict) else {"version": "1.0", "custom_stopwords": [], "noise_words": [], "go_words": []}


def _load_protected_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        defaults = {
            "version": "1.0",
            "protected_entities": [],
            "protected_families": [],
            "notes": "Add small human-protected nodes or families that should resist auto-demotion.",
        }
        write_json(path, defaults)
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": "1.0", "protected_entities": [], "protected_families": []}
    if not isinstance(data, dict):
        return {"version": "1.0", "protected_entities": [], "protected_families": []}
    data.setdefault("protected_entities", [])
    data.setdefault("protected_families", [])
    return data


def _candidate_values_from_meta(meta: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "scarcity": dedupe_preserve(meta.get("scarcity") or []),
        "orientation": dedupe_preserve([meta.get("orientation")] if meta.get("orientation") else []),
        "allocation": dedupe_preserve([meta.get("allocation")] if meta.get("allocation") else []),
    }


def _build_candidate_inventory(notes: list[Path], vault: Path) -> tuple[dict[Path, dict[str, Any]], dict[str, dict[str, dict[str, Any]]]]:
    meta_cache: dict[Path, dict[str, Any]] = {}
    inventory: dict[str, dict[str, dict[str, Any]]] = {
        "scarcity": {},
        "orientation": {},
        "allocation": {},
    }
    for note in notes:
        meta = read_note_metadata(note, vault)
        meta_cache[note] = meta
        note_rel = str(note.relative_to(vault))
        for kind, values in _candidate_values_from_meta(meta).items():
            for value in values:
                key = normalize_label_key(value)
                bucket = inventory[kind].setdefault(
                    key,
                    {
                        "kind": kind,
                        "normalized_key": key,
                        "values": [],
                        "notes": [],
                    },
                )
                bucket["values"] = dedupe_preserve([*bucket["values"], value])
                bucket["notes"].append(note_rel)
    return meta_cache, inventory


def _label_tokens(value: str) -> list[str]:
    return TOKEN_RE.findall(str(value or "").lower())


def _stable_node_label(value: str) -> bool:
    tokens = _label_tokens(value)
    if not tokens:
        return False
    if len(tokens) > 4:
        return False
    if len(str(value or "")) > 42:
        return False
    return not any(mark in str(value or "") for mark in (".", ";", ":", ","))


def _sentence_like_value(value: str) -> bool:
    text = str(value or "").strip()
    tokens = _label_tokens(text)
    return len(tokens) >= 7 or len(text) >= 56 or any(mark in text for mark in (".", ";", ":"))


def _protects_candidate(ref: EntityRef, protected_cfg: dict[str, Any]) -> tuple[bool, str | None]:
    slug = ref.slug.lower()
    family = ref.moc_target.lower()
    kind = ref.kind
    for item in protected_cfg.get("protected_entities", []) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("kind", "")).strip().lower() != kind:
            continue
        target_slug = str(item.get("slug", "")).strip().lower()
        if target_slug and target_slug == slug:
            return True, str(item.get("reason") or "protected_entity")
    for item in protected_cfg.get("protected_families", []) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("kind", "")).strip().lower() != kind:
            continue
        target_family = str(item.get("name", "")).strip().lower()
        if target_family and target_family == family:
            return True, str(item.get("reason") or "protected_family")
    return False, None


def _candidate_merge_target(
    *,
    kind: str,
    value: str,
    ref: EntityRef,
    existing_by_label: dict[str, Path],
    semantic_threshold: float,
    block_words: set[str],
    go_words: set[str],
) -> str | None:
    stable_labels = {
        label_lc: path
        for label_lc, path in existing_by_label.items()
        if _stable_node_label(label_lc)
    }
    if stable_labels and kind in {"orientation", "allocation"}:
        semantic = _best_semantic_match(value, stable_labels, semantic_threshold, block_words, go_words)
        if semantic is not None:
            return str(semantic)
    if kind == "scarcity":
        return ref.moc_target
    return ref.moc_target


def _policy_decision(
    *,
    kind: str,
    value: str,
    ref: EntityRef,
    inventory_entry: dict[str, Any],
    existing_by_label: dict[str, Path],
    protected_cfg: dict[str, Any],
    block_words: set[str],
    go_words: set[str],
    semantic_threshold: float,
) -> PolicyDecision:
    tokens = _label_tokens(value)
    token_set = set(tokens)
    reuse_count = len(inventory_entry.get("notes", []) or [])
    is_sentence = _sentence_like_value(value)
    is_stable = _stable_node_label(value)
    route_hit_count = len(token_set.intersection(ROUTE_LIKE_WORDS.union(block_words)))
    note_specific = bool(re.search(r"\b(this|latest|current|specific|april|chapter|draft|version)\b", str(value or "").lower()))
    protected, protected_reason = _protects_candidate(ref, protected_cfg)
    merge_target = _candidate_merge_target(
        kind=kind,
        value=value,
        ref=ref,
        existing_by_label=existing_by_label,
        semantic_threshold=semantic_threshold,
        block_words=block_words,
        go_words=go_words,
    )
    existing_entity = ref.file_path.exists()
    knowledge_score = min(1.0, reuse_count / 3.0)
    stable_score = 1.0 if is_stable else 0.0
    sentence_penalty = 1.0 if is_sentence else 0.0
    route_penalty = min(1.0, route_hit_count / 2.0)
    note_specific_penalty = 1.0 if note_specific else 0.0
    kind_penalty = 1.0 if kind == "allocation" else 0.6 if kind == "orientation" else 0.2
    score_breakdown = {
        "reuse_count": reuse_count,
        "knowledge_score": round(knowledge_score, 3),
        "stable_label": is_stable,
        "sentence_like": is_sentence,
        "route_like_count": route_hit_count,
        "note_specific": note_specific,
        "kind_penalty": round(kind_penalty, 3),
        "existing_entity": existing_entity,
        "protected": protected,
    }

    if protected:
        return PolicyDecision(
            kind=kind,
            value=value,
            normalized_key=inventory_entry["normalized_key"],
            decision="keep",
            reason=protected_reason or "protected",
            merge_target=merge_target,
            protected=True,
            score_breakdown=score_breakdown,
        )

    if route_hit_count and reuse_count <= 1 and not existing_entity:
        return PolicyDecision(
            kind=kind,
            value=value,
            normalized_key=inventory_entry["normalized_key"],
            decision="ignore_route",
            reason="route_like_low_reuse",
            merge_target=merge_target,
            protected=False,
            score_breakdown=score_breakdown,
        )

    if kind == "allocation" and is_sentence and reuse_count <= 2:
        return PolicyDecision(
            kind=kind,
            value=value,
            normalized_key=inventory_entry["normalized_key"],
            decision="demote_frontmatter",
            reason="granular_allocation_sentence",
            merge_target=merge_target,
            protected=False,
            score_breakdown=score_breakdown,
        )

    if kind == "orientation" and is_sentence and reuse_count <= 1:
        return PolicyDecision(
            kind=kind,
            value=value,
            normalized_key=inventory_entry["normalized_key"],
            decision="demote_frontmatter",
            reason="sentence_like_orientation",
            merge_target=merge_target,
            protected=False,
            score_breakdown=score_breakdown,
        )

    if not is_stable and reuse_count <= 2 and merge_target:
        return PolicyDecision(
            kind=kind,
            value=value,
            normalized_key=inventory_entry["normalized_key"],
            decision="merge_into_family",
            reason="merge_to_existing_or_family",
            merge_target=merge_target,
            protected=False,
            score_breakdown=score_breakdown,
        )

    if kind == "allocation" and len(tokens) <= 3 and reuse_count <= 1 and (note_specific or route_hit_count):
        return PolicyDecision(
            kind=kind,
            value=value,
            normalized_key=inventory_entry["normalized_key"],
            decision="demote_tag",
            reason="small_local_allocation",
            merge_target=merge_target,
            protected=False,
            score_breakdown=score_breakdown,
        )

    if knowledge_score + stable_score - sentence_penalty - route_penalty - note_specific_penalty - (0.15 * kind_penalty) > -0.15:
        return PolicyDecision(
            kind=kind,
            value=value,
            normalized_key=inventory_entry["normalized_key"],
            decision="keep",
            reason="stable_or_reused",
            merge_target=merge_target,
            protected=False,
            score_breakdown=score_breakdown,
        )

    fallback_decision = "demote_frontmatter" if kind in {"orientation", "allocation"} else "merge_into_family"
    return PolicyDecision(
        kind=kind,
        value=value,
        normalized_key=inventory_entry["normalized_key"],
        decision=fallback_decision,
        reason="default_deflation_policy",
        merge_target=merge_target,
        protected=False,
        score_breakdown=score_breakdown,
    )


def _shadow_hidden_relations(entities: list[dict[str, Any]], limit: int = 120) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for entity in entities:
        decision = str(entity.get("decision") or "")
        if decision == "keep":
            continue
        group_key = str(entity.get("merge_target") or entity.get("normalized_key") or "")
        if not group_key:
            continue
        key = (str(entity.get("kind") or ""), group_key)
        grouped.setdefault(key, []).append(str(entity.get("note") or ""))
    relations: list[dict[str, Any]] = []
    for (kind, group_key), notes in grouped.items():
        unique_notes = [note for note in dedupe_preserve(notes) if note]
        if len(unique_notes) < 2:
            continue
        anchor = unique_notes[0]
        for target in unique_notes[1:]:
            relations.append(
                {
                    "source_note": anchor,
                    "target_note": target,
                    "kind": kind,
                    "relation": "shared_shadow_entity",
                    "group_key": group_key,
                }
            )
            if len(relations) >= limit:
                return relations
    return relations


def _shadow_machine_artifact(
    *,
    entities: list[dict[str, Any]],
    protected_hits: list[dict[str, Any]],
) -> dict[str, Any]:
    merge_targets = [
        {
            "note": item["note"],
            "kind": item["kind"],
            "value": item["value"],
            "merge_target": item.get("merge_target"),
        }
        for item in entities
        if item.get("decision") == "merge_into_family" and item.get("merge_target")
    ]
    review_groups = _shadow_review_groups(entities)
    return {
        "ts": now_iso(),
        "entities": entities,
        "decisions": [
            {
                "note": item["note"],
                "kind": item["kind"],
                "value": item["value"],
                "decision": item["decision"],
                "reason": item["reason"],
            }
            for item in entities
        ],
        "merge_targets": merge_targets,
        "hidden_relations": _shadow_hidden_relations(entities),
        "protected_hits": protected_hits,
        "review_groups": review_groups,
    }


def _merge_target_to_label(kind: str, merge_target: str | None) -> str | None:
    target = str(merge_target or "").strip()
    if not target:
        return None
    if kind == "allocation" and target.startswith("ALLO-"):
        return target[len("ALLO-") :].replace("-", " ").strip() or None
    if kind == "orientation" and target.startswith("TO-"):
        return target[len("TO-") :].replace("-", " ").strip() or None
    if kind == "scarcity" and target.startswith("LACK-"):
        return target[len("LACK-") :].replace("-", "_").strip() or None
    return None


def _frontmatter_tags_list(frontmatter: dict[str, Any]) -> list[str]:
    return dedupe_preserve(normalize_list(frontmatter.get("tags")))


def _maybe_remove_empty_fields(fields: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        cleaned[key] = value
    return cleaned


def _detail_field_name(kind: str) -> str:
    return {"allocation": "allocation_detail", "orientation": "orientation_detail", "scarcity": "scarcity_detail"}[kind]


def _detail_field_value(kind: str, current: str, existing: Any) -> Any:
    if kind == "scarcity":
        return dedupe_preserve(normalize_list(existing) + [current])
    existing_text = normalize_scalar(existing)
    if not existing_text or existing_text == current:
        return current
    return dedupe_preserve([existing_text, current])


def _structured_kind_tag(kind: str, value: str) -> str:
    return f"{kind}/{_slugify(value)}"


def _apply_plan_entry_to_frontmatter(frontmatter: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    kind = str(entry.get("kind") or "")
    decision = str(entry.get("decision") or "")
    if not kind or not decision:
        return _maybe_remove_empty_fields(dict(frontmatter))

    current_value = str(entry.get("current_value") or entry.get("value") or "").strip()
    merge_target_label = _merge_target_to_label(kind, entry.get("merge_target"))
    after_fields = dict(frontmatter)
    detail_field = _detail_field_name(kind)
    tags_after = list(_frontmatter_tags_list(frontmatter))

    if kind == "scarcity":
        scarcity_values = dedupe_preserve(normalize_list(frontmatter.get("scarcity")))
        scarcity_after = [value for value in scarcity_values if value.strip().lower() != current_value.lower()]
        if decision == "merge_into_family" and merge_target_label:
            scarcity_after = dedupe_preserve(scarcity_after + [merge_target_label])
            after_fields[detail_field] = _detail_field_value(kind, current_value, frontmatter.get(detail_field))
        elif decision == "demote_frontmatter":
            after_fields[detail_field] = _detail_field_value(kind, current_value, frontmatter.get(detail_field))
        else:
            tags_after = dedupe_preserve(tags_after + [_structured_kind_tag(kind, current_value)])
        after_fields["scarcity"] = scarcity_after or None
    else:
        if decision == "merge_into_family" and merge_target_label:
            after_fields[kind] = merge_target_label
            after_fields[detail_field] = _detail_field_value(kind, current_value, frontmatter.get(detail_field))
        elif decision == "demote_frontmatter":
            after_fields.pop(kind, None)
            after_fields[detail_field] = _detail_field_value(kind, current_value, frontmatter.get(detail_field))
        else:
            after_fields.pop(kind, None)
            tags_after = dedupe_preserve(tags_after + [_structured_kind_tag(kind, current_value)])

    if tags_after:
        after_fields["tags"] = tags_after
    else:
        after_fields.pop("tags", None)
    return _maybe_remove_empty_fields(after_fields)


def _proposal_cleanup_score(entry: dict[str, Any]) -> int:
    action = str(entry.get("action") or "")
    decision = str(entry.get("decision") or "")
    decision_counts = entry.get("decision_counts", {}) or {}
    base = {
        "convert to tag": 50,
        "demote frontmatter": 45,
        "merge to family": 35,
        "ignore route node": 25,
        "review manually": 15,
        "protect explicitly": 0,
        "keep as node candidate": 0,
    }.get(action, 10)
    decision_bonus = {
        "demote_tag": 8,
        "demote_frontmatter": 6,
        "merge_into_family": 5,
        "ignore_route": 4,
    }.get(decision, 0)
    candidate_bonus = min(int(entry.get("candidate_count") or 0), 12)
    multiplicity_bonus = min(sum(int(v) for v in decision_counts.values()), 12)
    return base + decision_bonus + candidate_bonus + multiplicity_bonus


def _render_simple_yaml(fields: dict[str, Any]) -> str:
    ordered_keys = [
        "scarcity",
        "scarcity_detail",
        "orientation",
        "orientation_detail",
        "allocation",
        "allocation_detail",
        "tags",
    ]
    items = list(fields.items())
    items.sort(key=lambda item: (ordered_keys.index(item[0]) if item[0] in ordered_keys else len(ordered_keys), item[0]))
    lines: list[str] = []
    for key, value in items:
        if isinstance(value, list):
            if not value:
                continue
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines) if lines else "(no frontmatter changes)"


def _render_note_frontmatter(fields: dict[str, Any], body: str) -> str:
    yaml_body = _render_simple_yaml(fields)
    rendered_body = body.lstrip("\n")
    if yaml_body == "(no frontmatter changes)":
        return rendered_body
    if rendered_body:
        return f"---\n{yaml_body}\n---\n{rendered_body}"
    return f"---\n{yaml_body}\n---\n"


def _demotion_plan_entries(
    *,
    vault: Path,
    shadow_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actionable = {
        "demote_frontmatter",
        "demote_tag",
        "merge_into_family",
        "ignore_route",
    }
    plan_entries: list[dict[str, Any]] = []
    for item in shadow_entities:
        decision = str(item.get("decision") or "")
        if decision not in actionable:
            continue
        note_rel = str(item.get("note") or "")
        note_path = vault / note_rel
        if not note_path.exists():
            continue
        try:
            text = note_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _, _, frontmatter = _split_frontmatter_raw(text)
        kind = str(item.get("kind") or "")
        current_value = str(item.get("value") or "").strip()
        before_fields: dict[str, Any] = {}
        detail_field = _detail_field_name(kind)
        before_fields[kind] = frontmatter.get(kind)
        if detail_field in frontmatter:
            before_fields[detail_field] = frontmatter.get(detail_field)
        current_tags = _frontmatter_tags_list(frontmatter)
        if current_tags:
            before_fields["tags"] = current_tags
        after_fields = _apply_plan_entry_to_frontmatter(frontmatter, item)
        action = {
            "demote_frontmatter": "demote frontmatter",
            "demote_tag": "convert to tag",
            "merge_into_family": "merge to family",
            "ignore_route": "ignore route node",
        }.get(decision, "review manually")
        plan_entries.append(
            {
                "note": note_rel,
                "kind": kind,
                "decision": decision,
                "reason": str(item.get("reason") or ""),
                "current_value": current_value,
                "merge_target": item.get("merge_target"),
                "action": action,
                "before": _json_safe_frontmatter(_maybe_remove_empty_fields(before_fields)),
                "after": _json_safe_frontmatter(after_fields),
                "cleanup_score": _proposal_cleanup_score(
                    {
                        "action": action,
                        "decision": decision,
                        "candidate_count": 1,
                        "decision_counts": {decision: 1},
                    }
                ),
            }
        )
    plan_entries.sort(key=lambda entry: (-int(entry.get("cleanup_score") or 0), entry["note"], entry["kind"]))
    return plan_entries


def _apply_demotion_plan(
    *,
    vault: Path,
    artifact: dict[str, Any],
    max_writes: int,
) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    write_budget = max(max_writes, 0)
    applied_count = 0
    for entry in artifact.get("plans", []) or []:
        note_rel = str(entry.get("note") or "")
        note_path = vault / note_rel
        if not note_path.exists():
            skipped.append({"note": note_rel, "reason": "missing_note"})
            continue
        if applied_count >= write_budget:
            skipped.append({"note": note_rel, "reason": "demotion_write_budget_exhausted"})
            continue
        try:
            text = note_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            skipped.append({"note": note_rel, "reason": f"io_read_error:{exc}"})
            continue
        _, body, frontmatter = _split_frontmatter_raw(text)
        updated_frontmatter = _apply_plan_entry_to_frontmatter(frontmatter, entry)
        updated = _render_note_frontmatter(updated_frontmatter, body)
        if updated == text:
            skipped.append({"note": note_rel, "reason": "no_change"})
            continue
        try:
            note_path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            skipped.append({"note": note_rel, "reason": f"io_write_error:{exc}"})
            continue
        applied_count += 1
        applied.append(
            {
                "note": note_rel,
                "action": entry.get("action"),
                "decision": entry.get("decision"),
                "reason": entry.get("reason"),
            }
        )
    artifact["applied"] = applied
    artifact["skipped"] = skipped
    artifact["applied_count"] = len(applied)
    artifact["skipped_count"] = len(skipped)
    return {"applied": applied, "skipped": skipped}


def _demotion_plan_artifact(
    *,
    vault: Path,
    shadow_entities: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    plans = _demotion_plan_entries(vault=vault, shadow_entities=shadow_entities)
    return {
        "ts": now_iso(),
        "mode": "dry-run" if dry_run else "apply",
        "plan_count": len(plans),
        "plans": plans,
        "applied": [],
        "skipped": [],
        "applied_count": 0,
        "skipped_count": 0,
    }


def _demotion_plan_markdown(artifact: dict[str, Any]) -> str:
    plans = artifact.get("plans", []) or []
    lines = [
        "# Demotion Plan Preview",
        "",
        f"- mode: `{artifact.get('mode', 'dry-run')}`",
        f"- rewrites proposed: `{len(plans)}`",
    ]
    if artifact.get("mode") == "apply":
        lines.append(f"- applied: `{artifact.get('applied_count', 0)}`")
        lines.append(f"- skipped: `{artifact.get('skipped_count', 0)}`")
    if not plans:
        lines += ["", "No per-note demotion rewrites proposed in this batch."]
        return "\n".join(lines) + "\n"
    for entry in plans:
        lines += [
            "",
            f"## `{entry['note']}`",
            f"- kind: `{entry['kind']}`",
            f"- decision: `{entry['decision']}`",
            f"- action: `{entry['action']}`",
            f"- reason: `{entry['reason']}`",
            f"- current_value: `{entry['current_value']}`",
        ]
        if entry.get("merge_target"):
            lines.append(f"- merge_target: `{entry['merge_target']}`")
        lines += [
            "",
            "### Before",
            "```yaml",
            _render_simple_yaml(entry.get("before", {})),
            "```",
            "",
            "### Proposed",
            "```yaml",
            _render_simple_yaml(entry.get("after", {})),
            "```",
        ]
    if artifact.get("mode") == "apply":
        lines += ["", "## Apply Result"]
        applied = artifact.get("applied", []) or []
        skipped = artifact.get("skipped", []) or []
        if applied:
            lines.append("- applied:")
            for item in applied[:20]:
                lines.append(
                    f"  - `{item.get('note')}` => `{item.get('action')}` ({item.get('reason')})"
                )
        if skipped:
            lines.append("- skipped:")
            for item in skipped[:20]:
                lines.append(f"  - `{item.get('note')}` ({item.get('reason')})")
    return "\n".join(lines) + "\n"


def _match_frontmatter_value(actual: Any, expected: Any) -> bool:
    actual_normalized = _normalize_review_value(actual)
    expected_normalized = _normalize_review_value(expected)
    if isinstance(actual_normalized, list) or isinstance(expected_normalized, list):
        return _review_value_as_list(actual_normalized) == _review_value_as_list(expected_normalized)
    return actual_normalized == expected_normalized


def _review_value_as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _frontmatter_list_contains_expected(actual: Any, expected: Any) -> bool:
    actual_list = _review_value_as_list(_normalize_review_value(actual))
    expected_list = _review_value_as_list(_normalize_review_value(expected))
    if not expected_list:
        return True
    return all(item in actual_list for item in expected_list)


def _normalize_review_value(value: Any) -> Any:
    wikilink = _normalize_wikilink_like(value)
    if wikilink is not None:
        return wikilink
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        output: list[str] = []
        for item in value:
            normalized = _normalize_review_value(item)
            if normalized is None:
                continue
            if isinstance(normalized, list):
                output.extend(str(part).strip() for part in normalized if str(part).strip())
                continue
            text = str(normalized).strip()
            if text:
                output.append(text)
        return output
    text = normalize_scalar(value)
    if text is None:
        return None
    if text.lower() in {"null", "none"}:
        return None
    return text


def _normalize_wikilink_like(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[[") and stripped.endswith("]]"):
            return stripped
        return None
    if isinstance(value, (list, tuple)) and len(value) == 1:
        inner = value[0]
        if isinstance(inner, (list, tuple)) and len(inner) == 1:
            inner_text = normalize_scalar(inner[0])
            if inner_text:
                return f"[[{inner_text}]]"
    return None


def _has_meaningful_frontmatter_value(value: Any) -> bool:
    normalized = _normalize_review_value(value)
    if normalized is None:
        return False
    if isinstance(normalized, list):
        return bool(normalized)
    return bool(str(normalized).strip())


def _json_safe_frontmatter_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe_frontmatter_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_frontmatter_value(item) for item in value]
    if isinstance(value, set):
        return [_json_safe_frontmatter_value(item) for item in sorted(value, key=str)]
    return value


def _json_safe_frontmatter(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_frontmatter_value(value) for key, value in fields.items()}


def _review_applied_entry(note_path: Path, plan_entry: dict[str, Any]) -> tuple[bool, list[str]]:
    try:
        text = note_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, [f"io_read_error:{exc}"]
    _, _, frontmatter = _split_frontmatter_raw(text)
    expected_after = dict(plan_entry.get("after") or {})
    issues: list[str] = []
    kind = str(plan_entry.get("kind") or "")
    decision = str(plan_entry.get("decision") or "")
    if not kind or not decision:
        return True, issues

    detail_field = _detail_field_name(kind)
    keys_to_compare: list[str] = []
    keys_to_remove: list[str] = []

    if kind == "scarcity":
        keys_to_compare.append("scarcity")
        if detail_field in expected_after:
            keys_to_compare.append(detail_field)
        if decision in {"demote_tag", "ignore_route"} and "tags" in expected_after:
            keys_to_compare.append("tags")
    elif decision == "merge_into_family":
        keys_to_compare.append(kind)
        if detail_field in expected_after:
            keys_to_compare.append(detail_field)
    elif decision == "demote_frontmatter":
        keys_to_remove.append(kind)
        if detail_field in expected_after:
            keys_to_compare.append(detail_field)
    else:
        keys_to_remove.append(kind)
        if "tags" in expected_after:
            keys_to_compare.append("tags")

    for key in keys_to_compare:
        if key == "tags" and decision in {"demote_tag", "ignore_route"}:
            if not _frontmatter_list_contains_expected(frontmatter.get(key), expected_after.get(key)):
                issues.append(f"{key}:expected_after_mismatch")
            continue
        if not _match_frontmatter_value(frontmatter.get(key), expected_after.get(key)):
            issues.append(f"{key}:expected_after_mismatch")
    for key in keys_to_remove:
        if key in frontmatter and _has_meaningful_frontmatter_value(frontmatter.get(key)):
            issues.append(f"{key}:expected_removed_key_still_present")
    return not issues, issues


def _primary_allo_hotspot_family(
    shadow_artifact: dict[str, Any],
    demotion_plan_artifact: dict[str, Any],
) -> str:
    for group in shadow_artifact.get("review_groups", []) or []:
        if str(group.get("prefix") or "") != "ALLO-*":
            continue
        family_groups = group.get("family_groups", []) or []
        if family_groups:
            family = str(family_groups[0].get("family") or "").strip()
            if family:
                return family
    counts: dict[str, int] = {}
    for entry in demotion_plan_artifact.get("plans", []) or []:
        if str(entry.get("kind") or "") != "allocation":
            continue
        family = str(entry.get("merge_target") or "").strip()
        if not family:
            continue
        counts[family] = counts.get(family, 0) + 1
    if counts:
        return max(counts.items(), key=lambda item: (item[1], item[0]))[0]
    return "ALLOCATION-FAMILY"


def _recommended_next_apply_mode(primary_hotspot_family: str) -> str:
    hotspot = primary_hotspot_family.strip().upper()
    if hotspot.startswith("ALLO") or hotspot == "ALLOCATION-FAMILY":
        return "ALLO-only"
    return "mixed-family"


def _recommended_next_action(mode: str, family: str, *, ready_for_openclaw_fetch: bool) -> str:
    if not ready_for_openclaw_fetch:
        if mode == "ALLO-only":
            return (
                f"Review graph-demotion mismatches for {family}, clear the ALLO-only review blockers, "
                "then rerun the bounded batch before enabling OpenClaw research."
            )
        return (
            f"Review graph-demotion mismatches for {family}, clear the mixed-family review blockers, "
            "then rerun the bounded batch before enabling OpenClaw research."
        )
    if mode == "ALLO-only":
        return f"Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for {family}, then apply the next ALLO-only batch."
    return f"Use the reviewed graph-demotion batch to run one bounded OpenClaw fetch for {family}, then apply the next mixed-family batch."


def _graph_review_openclaw_topic(mode: str, family: str, reviewed_note_count: int) -> str:
    return f"{mode} graph demotion follow-up for {family} after reviewed {reviewed_note_count}-note bounded apply"


def _graph_review_quality_verdict(reviewed_count: int, passed_count: int) -> str:
    if reviewed_count <= 0:
        return "inconclusive"
    if passed_count == reviewed_count:
        return "ready"
    if passed_count / reviewed_count >= 0.75:
        return "mostly-ready"
    return "needs-manual-review"


def _graph_review_readability_verdict(quality_verdict: str, primary_hotspot_family: str) -> str:
    if quality_verdict in {"ready", "mostly-ready"}:
        if primary_hotspot_family == "ALLOCATION-FAMILY":
            return "improved_allocation_signal"
        return "improved"
    if quality_verdict == "inconclusive":
        return "inconclusive"
    return "needs_manual_review"


def _build_graph_demotion_review_artifact(
    *,
    vault: Path,
    demotion_plan_artifact: dict[str, Any],
    shadow_artifact: dict[str, Any],
    checkpoint_payload: dict[str, Any],
) -> dict[str, Any]:
    plan_lookup: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for entry in demotion_plan_artifact.get("plans", []) or []:
        key = (
            str(entry.get("note") or ""),
            str(entry.get("decision") or ""),
            str(entry.get("reason") or ""),
        )
        plan_lookup.setdefault(key, []).append(entry)

    reviewed_entries: list[dict[str, Any]] = []
    pass_count = 0
    for applied in demotion_plan_artifact.get("applied", []) or []:
        key = (
            str(applied.get("note") or ""),
            str(applied.get("decision") or ""),
            str(applied.get("reason") or ""),
        )
        plan_entry = None
        if plan_lookup.get(key):
            plan_entry = plan_lookup[key].pop(0)
        note_rel = str(applied.get("note") or "")
        note_path = vault / note_rel
        ok, issues = _review_applied_entry(note_path, plan_entry or {"after": {}, "before": {}})
        if ok:
            pass_count += 1
        reviewed_entries.append(
            {
                "note": note_rel,
                "kind": str((plan_entry or {}).get("kind") or ""),
                "action": str(applied.get("action") or ""),
                "decision": str(applied.get("decision") or ""),
                "status": "pass" if ok else "fail",
                "issues": issues,
            }
        )

    reviewed_count = len(reviewed_entries)
    unique_notes = sorted({item["note"] for item in reviewed_entries})
    primary_hotspot_family = _primary_allo_hotspot_family(shadow_artifact, demotion_plan_artifact)
    next_mode = _recommended_next_apply_mode(primary_hotspot_family)
    quality_verdict = _graph_review_quality_verdict(reviewed_count, pass_count)
    graph_readability_verdict = _graph_review_readability_verdict(quality_verdict, primary_hotspot_family)
    ready_for_openclaw_fetch = quality_verdict in {"ready", "mostly-ready"} and reviewed_count > 0
    next_action = _recommended_next_action(
        next_mode,
        primary_hotspot_family,
        ready_for_openclaw_fetch=ready_for_openclaw_fetch,
    )

    return {
        "ts": now_iso(),
        "updated_at": now_iso(),
        "reviewed_note_count": reviewed_count,
        "reviewed_unique_note_count": len(unique_notes),
        "review_pass_count": pass_count,
        "review_fail_count": max(reviewed_count - pass_count, 0),
        "quality_verdict": quality_verdict,
        "graph_readability_verdict": graph_readability_verdict,
        "recommended_next_apply_mode": next_mode,
        "primary_hotspot_family": primary_hotspot_family,
        "recommended_next_action": next_action,
        "ready_for_openclaw_fetch": ready_for_openclaw_fetch,
        "openclaw_topic": _graph_review_openclaw_topic(next_mode, primary_hotspot_family, reviewed_count),
        "source_apply_checkpoint_ts": checkpoint_payload.get("ts"),
        "source_demotion_mode": demotion_plan_artifact.get("mode"),
        "source_demotion_applied_count": demotion_plan_artifact.get("applied_count", 0),
        "source_demotion_skipped_count": demotion_plan_artifact.get("skipped_count", 0),
        "reviewed_notes": reviewed_entries,
        "unique_notes": unique_notes,
    }


def _handoff_drop_path(repo: Path, updated_at: str, role: str, status: str) -> Path:
    stamp = re.sub(r"[^0-9T]", "", updated_at.replace(":", "")).strip()
    stamp = stamp[:13] if len(stamp) >= 13 else stamp
    if not stamp:
        stamp = now_iso().replace("-", "").replace(":", "")[:13]
    return repo / "state" / "handoff" / "from_cowork" / f"{stamp}_{role}_{status}.json"


def _latest_graph_apply_checkpoint(repo: Path) -> tuple[str, dict[str, Any]]:
    checkpoint_dir = repo / "state" / "run_journal" / "checkpoints"
    candidates = sorted(checkpoint_dir.glob("*graph_shadow_demotion_apply*.json"))
    if not candidates:
        return "", {}
    latest = candidates[-1]
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        payload = {}
    return str(latest), payload if isinstance(payload, dict) else {}


def _allo_hotspot_entries(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    review_groups = _filtered_review_groups(artifact, family_prefix="ALLO")
    if not review_groups:
        return []
    entries: list[dict[str, Any]] = []
    for group in review_groups:
        for family_group in group.get("family_groups", []):
            if str(family_group.get("primary_triage") or "") in {"human_expensive_keep", "keep_candidate"}:
                continue
            entry = {
                "family": str(family_group.get("family") or "unassigned"),
                "primary_triage": str(family_group.get("primary_triage") or "none"),
                "action": str(family_group.get("suggested_action") or "review manually"),
                "why": str(family_group.get("suggested_action_why") or ""),
                "decision_counts": dict(family_group.get("decision_counts", {}) or {}),
                "triage_counts": dict(family_group.get("triage_counts", {}) or {}),
                "candidate_count": sum(int(v) for v in (family_group.get("decision_counts", {}) or {}).values()),
                "examples": list(family_group.get("examples", []) or []),
            }
            entry["cleanup_payoff"] = _proposal_cleanup_score(entry)
            entries.append(entry)
    entries.sort(key=lambda item: (-int(item["cleanup_payoff"]), -int(item["candidate_count"]), item["family"]))
    return entries


def _allo_hotspots_markdown(artifact: dict[str, Any]) -> str:
    hotspots = _allo_hotspot_entries(artifact)
    lines = [
        "# ALLO Inflation Hotspots",
        "",
        f"- hotspot_families: `{len(hotspots)}`",
        "- ordering: `highest cleanup payoff first`",
    ]
    if not hotspots:
        lines += ["", "No ALLO-specific inflation hotspots in this batch."]
        return "\n".join(lines) + "\n"
    for item in hotspots:
        decisions = ", ".join(f"{k}={v}" for k, v in sorted(item["decision_counts"].items())) or "none"
        triage = ", ".join(f"{k}={v}" for k, v in sorted(item["triage_counts"].items())) or "none"
        lines += [
            "",
            f"## `{item['family']}`",
            f"- cleanup_payoff: `{item['cleanup_payoff']}`",
            f"- action: `{item['action']}`",
            f"- why: {item['why']}",
            f"- candidates: `{item['candidate_count']}`",
            f"- triage: `{triage}`",
            f"- decisions: `{decisions}`",
        ]
        if item["examples"]:
            lines.append("- example notes:")
            for example in item["examples"][:5]:
                lines.append(
                    f"  - `{example.get('note')}` -> `{example.get('value')}` => `{example.get('decision')}` ({example.get('reason')})"
                )
    return "\n".join(lines) + "\n"


def _shadow_markdown(artifact: dict[str, Any]) -> str:
    entities = artifact.get("entities", []) or []
    lines = [
        "# Shadow Graph Node Deflation",
        "",
        f"- Candidates reviewed: `{len(entities)}`",
        f"- Hidden relations: `{len(artifact.get('hidden_relations', []) or [])}`",
        f"- Protected hits: `{len(artifact.get('protected_hits', []) or [])}`",
        "",
        "## Inflation Hotspots",
    ]
    hotspots = [item for item in entities if item.get("decision") != "keep"]
    if hotspots:
        for item in hotspots[:20]:
            lines.append(
                f"- `{item['note']}` -> `{item['kind']}` `{item['value']}` => `{item['decision']}` "
                f"({item['reason']})"
            )
    else:
        lines.append("- none")
    lines += ["", "## Protected Nodes Kept"]
    if artifact.get("protected_hits"):
        for item in artifact["protected_hits"][:20]:
            lines.append(
                f"- `{item['kind']}` `{item['value']}` kept because `{item['reason']}`"
            )
    else:
        lines.append("- none")
    lines += ["", "## Candidate Merges"]
    if artifact.get("merge_targets"):
        for item in artifact["merge_targets"][:20]:
            lines.append(
                f"- `{item['note']}` -> `{item['kind']}` `{item['value']}` -> `{item['merge_target']}`"
            )
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _kind_review_prefix(kind: str) -> str:
    return {"allocation": "ALLO-*", "orientation": "TO-*", "scarcity": "LACK-*"}[kind]


def _triage_label_for_entity(entity: dict[str, Any]) -> str:
    kind = str(entity.get("kind") or "")
    decision = str(entity.get("decision") or "")
    protected = bool(entity.get("protected"))
    if protected and decision == "keep":
        return "human_expensive_keep"
    if decision == "merge_into_family":
        return "merge_to_family"
    if decision in {"demote_frontmatter", "demote_tag"}:
        return "cheap_metadata"
    if decision == "ignore_route":
        return "ignore_route"
    if decision == "keep":
        return "keep_candidate"
    if kind == "allocation":
        return "cheap_metadata"
    return "review_manually"


def _primary_triage_label(counts: dict[str, int]) -> str:
    priority = {
        "human_expensive_keep": 0,
        "merge_to_family": 1,
        "cheap_metadata": 2,
        "ignore_route": 3,
        "keep_candidate": 4,
        "review_manually": 5,
    }
    if not counts:
        return "none"
    return sorted(counts.items(), key=lambda item: (-item[1], priority.get(item[0], 99), item[0]))[0][0]


def _triage_priority(triage: str, *, for_deflation: bool = False) -> int:
    if for_deflation:
        priorities = {
            "cheap_metadata": 0,
            "merge_to_family": 1,
            "ignore_route": 2,
            "review_manually": 3,
            "human_expensive_keep": 4,
            "keep_candidate": 5,
            "none": 6,
        }
        return priorities.get(triage, 99)
    priorities = {
        "human_expensive_keep": 0,
        "merge_to_family": 1,
        "cheap_metadata": 2,
        "ignore_route": 3,
        "keep_candidate": 4,
        "review_manually": 5,
        "none": 6,
    }
    return priorities.get(triage, 99)


def _family_urgency_score(group_prefix: str, family_group: dict[str, Any]) -> tuple[int, int, int]:
    triage_counts = family_group.get("triage_counts", {})
    deflation_count = sum(
        count for triage, count in triage_counts.items() if triage not in {"keep_candidate", "human_expensive_keep"}
    )
    protected_count = int(triage_counts.get("human_expensive_keep", 0))
    primary_triage = str(family_group.get("primary_triage") or "none")
    priority = _triage_priority(primary_triage, for_deflation=(group_prefix == "ALLO-*"))
    return (priority, -deflation_count, protected_count)


def _suggested_action_for_family(family_group: dict[str, Any]) -> tuple[str, str]:
    triage = str(family_group.get("primary_triage") or "none")
    decision_counts = family_group.get("decision_counts", {})
    if triage == "human_expensive_keep":
        return "protect explicitly", "human-marked expensive node or family should resist automatic deflation"
    if triage == "merge_to_family":
        return "merge to family", "multiple note-local variants should collapse into the parent family"
    if triage == "cheap_metadata":
        if int(decision_counts.get("demote_tag", 0)) >= int(decision_counts.get("demote_frontmatter", 0)):
            return "convert to tag", "this looks too local or tactical to deserve a durable node"
        return "demote frontmatter", "this is useful classification, but too granular for graph-node status"
    if triage == "ignore_route":
        return "ignore route node", "this behaves like a route/index label rather than knowledge mass"
    if triage == "keep_candidate":
        return "keep as node candidate", "reuse and stability are strong enough to keep this in node consideration"
    return "review manually", "signals are mixed and need human judgment"


def _normalize_family_prefix_filter(value: str | None) -> str | None:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    mapping = {
        "ALLO": "ALLO-*",
        "ALLO-*": "ALLO-*",
        "TO": "TO-*",
        "TO-*": "TO-*",
        "LACK": "LACK-*",
        "LACK-*": "LACK-*",
    }
    return mapping.get(raw)


def _normalize_only_triage_filter(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    allowed = {
        "human_expensive_keep",
        "merge_to_family",
        "cheap_metadata",
        "ignore_route",
        "keep_candidate",
        "review_manually",
    }
    return raw if raw in allowed else None


def _normalize_only_action_filter(value: str | None) -> str | None:
    raw = " ".join(str(value or "").strip().lower().split())
    if not raw:
        return None
    mapping = {
        "protect explicitly": "protect explicitly",
        "merge to family": "merge to family",
        "demote frontmatter": "demote frontmatter",
        "convert to tag": "convert to tag",
        "ignore route node": "ignore route node",
        "keep as node candidate": "keep as node candidate",
        "review manually": "review manually",
    }
    return mapping.get(raw)


def _filtered_review_groups(
    artifact: dict[str, Any],
    family_prefix: str | None = None,
    only_triage: str | None = None,
    only_action: str | None = None,
) -> list[dict[str, Any]]:
    review_groups = artifact.get("review_groups", []) or []
    normalized = _normalize_family_prefix_filter(family_prefix)
    triage_filter = _normalize_only_triage_filter(only_triage)
    action_filter = _normalize_only_action_filter(only_action)
    results: list[dict[str, Any]] = []
    for group in review_groups:
        if normalized is not None and str(group.get("prefix")) != normalized:
            continue
        family_groups = group.get("family_groups", []) or []
        if triage_filter is not None:
            family_groups = [
                family_group
                for family_group in family_groups
                if str(family_group.get("primary_triage") or "") == triage_filter
            ]
        if action_filter is not None:
            family_groups = [
                family_group
                for family_group in family_groups
                if str(family_group.get("suggested_action") or "") == action_filter
            ]
        if not family_groups:
            continue
        cloned = dict(group)
        cloned["family_groups"] = family_groups
        cloned["candidate_count"] = sum(sum(item["decision_counts"].values()) for item in family_groups)
        results.append(cloned)
    return results


def _shadow_review_groups(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    ordered_prefixes = ("ALLO-*", "TO-*", "LACK-*")
    for entity in entities:
        kind = str(entity.get("kind") or "")
        if kind not in KIND_TO_PREFIX:
            continue
        prefix = _kind_review_prefix(kind)
        group = grouped.setdefault(
            prefix,
            {
                "prefix": prefix,
                "kind": kind,
                "decision_counts": {},
                "triage_counts": {},
                "protected_hits": 0,
                "inflation_candidates": 0,
                "family_groups": {},
            },
        )
        decision = str(entity.get("decision") or "unknown")
        triage = _triage_label_for_entity(entity)
        group["decision_counts"][decision] = int(group["decision_counts"].get(decision, 0)) + 1
        group["triage_counts"][triage] = int(group["triage_counts"].get(triage, 0)) + 1
        if bool(entity.get("protected")):
            group["protected_hits"] += 1
        if decision != "keep":
            group["inflation_candidates"] += 1

        family_key = str(entity.get("merge_target") or entity.get("normalized_key") or "unassigned")
        family_group = group["family_groups"].setdefault(
            family_key,
            {
                "family": family_key,
                "decision_counts": {},
                "triage_counts": {},
                "examples": [],
            },
        )
        family_group["decision_counts"][decision] = int(family_group["decision_counts"].get(decision, 0)) + 1
        family_group["triage_counts"][triage] = int(family_group["triage_counts"].get(triage, 0)) + 1
        if len(family_group["examples"]) < 6 and (decision != "keep" or bool(entity.get("protected"))):
            family_group["examples"].append(
                {
                    "note": entity.get("note"),
                    "value": entity.get("value"),
                    "decision": decision,
                    "triage": triage,
                    "reason": entity.get("reason"),
                    "protected": bool(entity.get("protected")),
                }
            )

    results: list[dict[str, Any]] = []
    for prefix in ordered_prefixes:
        group = grouped.get(prefix)
        if group is None:
            continue
        family_groups = list(group["family_groups"].values())
        for family_group in family_groups:
            family_group["primary_triage"] = _primary_triage_label(family_group["triage_counts"])
            action, action_why = _suggested_action_for_family(family_group)
            family_group["suggested_action"] = action
            family_group["suggested_action_why"] = action_why
        family_groups.sort(key=lambda item: (*_family_urgency_score(prefix, item), item["family"]))
        group["family_groups"] = family_groups
        group["candidate_count"] = sum(group["decision_counts"].values())
        group["primary_triage"] = _primary_triage_label(group["triage_counts"])
        results.append(group)
    return results


def _shadow_review_markdown(artifact: dict[str, Any]) -> str:
    review_groups = artifact.get("review_groups", []) or []
    lines = [
        "# Shadow Graph Family Review",
        "",
        f"- Candidates reviewed: `{len(artifact.get('entities', []) or [])}`",
        f"- Hidden relations: `{len(artifact.get('hidden_relations', []) or [])}`",
        f"- Protected hits: `{len(artifact.get('protected_hits', []) or [])}`",
    ]
    if not review_groups:
        lines += ["", "No family-level proposals yet."]
        return "\n".join(lines) + "\n"

    for group in review_groups:
        lines += [
            "",
            f"## {group['prefix']} Review",
            f"- candidates: `{group['candidate_count']}`",
            f"- inflation_candidates: `{group['inflation_candidates']}`",
            f"- protected_hits: `{group['protected_hits']}`",
            f"- primary_triage: `{group['primary_triage']}`",
        ]
        decision_summary = ", ".join(
            f"{decision}={count}" for decision, count in sorted(group["decision_counts"].items())
        )
        lines.append(f"- decisions: `{decision_summary or 'none'}`")
        triage_summary = ", ".join(
            f"{triage}={count}" for triage, count in sorted(group["triage_counts"].items())
        )
        lines.append(f"- triage: `{triage_summary or 'none'}`")
        for family_group in group.get("family_groups", [])[:8]:
            family_summary = ", ".join(
                f"{decision}={count}" for decision, count in sorted(family_group["decision_counts"].items())
            )
            triage_summary = ", ".join(
                f"{triage}={count}" for triage, count in sorted(family_group["triage_counts"].items())
            )
            lines += [
                "",
                f"### Family `{family_group['family']}`",
                f"- primary_triage: `{family_group['primary_triage']}`",
                f"- decisions: `{family_summary or 'none'}`",
                f"- triage: `{triage_summary or 'none'}`",
            ]
            if family_group.get("examples"):
                for example in family_group["examples"]:
                    protected_note = " [protected]" if example.get("protected") else ""
                    lines.append(
                        f"- `{example['note']}` -> `{example['value']}` => `{example['decision']}` "
                        f"[{example['triage']}] "
                        f"({example['reason']}){protected_note}"
                    )
            else:
                lines.append("- no highlighted examples")
    return "\n".join(lines) + "\n"


def _shadow_family_summary_table(
    artifact: dict[str, Any],
    family_prefix: str | None = None,
    only_triage: str | None = None,
    only_action: str | None = None,
    top_family_rows: int | None = None,
) -> str:
    review_groups = _filtered_review_groups(artifact, family_prefix, only_triage, only_action)
    headers = ("Prefix", "Family", "Triage", "Action", "Candidates", "Protected", "Decisions")
    rows: list[tuple[str, ...]] = []
    for group in review_groups:
        for family_group in group.get("family_groups", []):
            decisions = ",".join(
                f"{decision}={count}" for decision, count in sorted(family_group["decision_counts"].items())
            ) or "-"
            rows.append(
                (
                    str(group["prefix"]),
                    str(family_group["family"]),
                    str(family_group.get("primary_triage") or "none"),
                    str(family_group.get("suggested_action") or "review manually"),
                    str(sum(family_group["decision_counts"].values())),
                    str(sum(1 for ex in family_group.get("examples", []) if ex.get("protected"))),
                    decisions,
                )
            )
    if top_family_rows is not None and top_family_rows > 0:
        rows = rows[:top_family_rows]
    if not rows:
        return "Prefix | Family | Triage | Action | Candidates | Protected | Decisions\n(no family proposals)\n"
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))
    def fmt(row: tuple[str, ...]) -> str:
        return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row))
    separator = "-+-".join("-" * width for width in widths)
    lines = [fmt(headers), separator]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines) + "\n"


def _shadow_family_csv_rows(
    artifact: dict[str, Any],
    family_prefix: str | None = None,
    only_triage: str | None = None,
    only_action: str | None = None,
) -> list[dict[str, str]]:
    review_groups = _filtered_review_groups(artifact, family_prefix, only_triage, only_action)
    rows: list[dict[str, str]] = []
    for group in review_groups:
        for family_group in group.get("family_groups", []):
            examples = family_group.get("examples", []) or []
            example_notes = " | ".join(str(example.get("note") or "") for example in examples[:3])
            example_values = " | ".join(str(example.get("value") or "") for example in examples[:3])
            example_reasons = " | ".join(str(example.get("reason") or "") for example in examples[:3])
            rows.append(
                {
                    "prefix": str(group["prefix"]),
                    "family": str(family_group["family"]),
                    "triage": str(family_group.get("primary_triage") or "none"),
                    "action": str(family_group.get("suggested_action") or "review manually"),
                    "why": str(family_group.get("suggested_action_why") or ""),
                    "candidate_count": str(sum(family_group["decision_counts"].values())),
                    "protected_example_count": str(sum(1 for example in examples if example.get("protected"))),
                    "decisions": ",".join(
                        f"{decision}={count}" for decision, count in sorted(family_group["decision_counts"].items())
                    ),
                    "example_notes": example_notes,
                    "example_values": example_values,
                    "example_reasons": example_reasons,
                }
            )
    return rows


def _write_shadow_family_csv(
    path: Path,
    artifact: dict[str, Any],
    family_prefix: str | None = None,
    only_triage: str | None = None,
    only_action: str | None = None,
) -> None:
    rows = _shadow_family_csv_rows(
        artifact,
        family_prefix=family_prefix,
        only_triage=only_triage,
        only_action=only_action,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "prefix",
        "family",
        "triage",
        "action",
        "why",
        "candidate_count",
        "protected_example_count",
        "decisions",
        "example_notes",
        "example_values",
        "example_reasons",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _resolve_entity(
    *,
    kind: str,
    value: str,
    meta_root: Path,
    existing_by_slug: dict[str, Path],
    existing_by_label: dict[str, Path],
    semantic_threshold: float,
    block_words: set[str],
    go_words: set[str],
) -> EntityRef:
    prefix = KIND_TO_PREFIX[kind]
    kind_dir = meta_root / KIND_TO_DIR[kind]
    slug_tail, label = _normalize_value(prefix, value)
    slug = f"{prefix}{slug_tail}"
    target_path = kind_dir / f"{slug}.md"

    if target_path.exists():
        path = target_path
    elif slug.lower() in existing_by_slug:
        path = existing_by_slug[slug.lower()]
    elif value.strip().lower() in existing_by_label:
        path = existing_by_label[value.strip().lower()]
    elif kind in {"orientation", "allocation"}:
        semantic = _best_semantic_match(value, existing_by_label, semantic_threshold, block_words, go_words)
        path = semantic if semantic is not None else target_path
    else:
        path = target_path

    if kind == "scarcity":
        key = normalize_label_key(label)
        cluster = SCARCITY_FAMILY_TO_CLUSTER.get(key)
        if not cluster and key.upper() in CLUSTERS:
            cluster = key.upper()
        moc_target = cluster or "CONTEXT"
        pillar = "SCARCITY"
    elif kind == "orientation":
        moc_target = FAMILY_MOC_FILES["orientation"][0]
        pillar = "ORIENTATION"
    else:
        moc_target = FAMILY_MOC_FILES["allocation"][0]
        pillar = "ALLOCATION"
    return EntityRef(kind=kind, value=value.strip(), label=label, slug=slug, file_path=path, moc_target=moc_target, pillar=pillar)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and shape LACK/TO/ALLO roll-up graph links")
    parser.add_argument("--vault", default="")
    parser.add_argument("--scope", choices=["active", "full"], default="active")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--writeback", action="store_true")
    parser.add_argument("--max-note-writes", type=int, default=6)
    parser.add_argument("--max-entity-writes", type=int, default=8)
    parser.add_argument("--max-moc-writes", type=int, default=4)
    parser.add_argument("--semantic-threshold", type=float, default=0.78)
    parser.add_argument("--ignore-cooldown-runs", type=int, default=2)
    parser.add_argument("--noise-config", default="config/graph_shaper_noise_words.json")
    parser.add_argument("--protected-config", default="config/graph_shadow_protected_nodes.json")
    parser.add_argument("--lock-seconds", type=int, default=1800)
    parser.add_argument("--output", default="state/run_journal/graph_shape_audit.json")
    parser.add_argument("--markdown-output", default="state/run_journal/graph_shape_audit.md")
    parser.add_argument("--shadow-output", default="state/run_journal/graph_shadow_decisions.json")
    parser.add_argument("--shadow-markdown-output", default="state/run_journal/graph_shadow_decisions.md")
    parser.add_argument("--shadow-review-output", default="state/run_journal/graph_shadow_review.md")
    parser.add_argument("--shadow-review-csv-output", default="state/run_journal/graph_shadow_review.csv")
    parser.add_argument("--demotion-plan-output", default="state/run_journal/graph_demotion_plan.md")
    parser.add_argument("--demotion-plan-json-output", default="state/run_journal/graph_demotion_plan.json")
    parser.add_argument("--graph-demotion-review-output", default="state/run_journal/graph_demotion_review_latest.json")
    parser.add_argument("--allo-hotspots-output", default="state/run_journal/graph_allo_hotspots.md")
    parser.add_argument("--max-demotion-writes", type=int, default=12)
    parser.add_argument("--export-family-summary-csv", action="store_true")
    parser.add_argument("--family-prefix", choices=["ALLO", "TO", "LACK"], default="")
    parser.add_argument(
        "--only-triage",
        choices=["human_expensive_keep", "merge_to_family", "cheap_metadata", "ignore_route", "keep_candidate", "review_manually"],
        default="",
    )
    parser.add_argument("--apply-demotion-plan", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-action", default="")
    parser.add_argument("--top-family-rows", type=int, default=0)
    parser.add_argument("--print-family-summary", action="store_true")
    parser.add_argument("--print-full", action="store_true")
    args = parser.parse_args()

    repo = _repo_root()
    vault = Path(args.vault).expanduser().resolve() if args.vault else Path(
        os.environ.get("OTTO_VAULT_PATH", str(repo))
    ).expanduser().resolve()
    if not vault.exists() or not vault.is_dir():
        raise SystemExit(f"Vault path is not a directory: {vault}")

    lock_path = repo / "state" / "pids" / "graph_shape.lock"
    locked, lock_msg = _acquire_lock(lock_path, stale_seconds=args.lock_seconds)
    if not locked:
        payload = {
            "ts": now_iso(),
            "status": "skipped-lock",
            "reason": lock_msg,
            "vault": str(vault),
            "scope": args.scope,
        }
        write_json((repo / args.output).resolve(), payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    try:
        cursor_path = repo / "state" / "openclaw" / "graph_shape_cursor.json"
        ignore_path = repo / "state" / "openclaw" / "graph_shape_ignore.json"
        noise_path = (repo / args.noise_config).resolve() if not Path(args.noise_config).is_absolute() else Path(args.noise_config)
        protected_path = (repo / args.protected_config).resolve() if not Path(args.protected_config).is_absolute() else Path(args.protected_config)
        block_words, go_words, noise_config_meta = _load_noise_words(noise_path)
        protected_cfg = _load_protected_config(protected_path)
        ignore_state = _load_ignore_state(ignore_path)
        run_count = int(ignore_state.get("run_count", 0)) + 1
        ignore_state["run_count"] = run_count
        start_index = _load_cursor(cursor_path)
        notes = _enumerate_target_notes(vault, args.scope)
        meta_cache, candidate_inventory = _build_candidate_inventory(notes, vault)
        batch, next_index = _pick_batch(notes, start_index, max(args.batch_size, 1))

        budgets = {
            "note_writes": max(args.max_note_writes, 0),
            "entity_writes": max(args.max_entity_writes, 0),
            "moc_writes": max(args.max_moc_writes, 0),
        }
        counters = {"note_writes": 0, "entity_writes": 0, "moc_writes": 0}
        deferred: list[dict[str, str]] = []
        resolved: list[dict[str, str]] = []
        already_present: list[dict[str, str]] = []
        linked: list[dict[str, str]] = []

        meta_root = vault / "00-Meta"
        existing_maps: dict[str, tuple[dict[str, Path], dict[str, Path]]] = {}
        for kind, subdir in KIND_TO_DIR.items():
            existing_maps[kind] = _existing_entities(meta_root / subdir, KIND_TO_PREFIX[kind])

        touched_mocs: dict[str, str] = {}
        note_to_entities: dict[Path, list[EntityRef]] = {}
        shadow_entities: list[dict[str, Any]] = []
        protected_hits: list[dict[str, Any]] = []

        for note_path in batch:
            note_rel = str(note_path.relative_to(vault))
            meta = meta_cache[note_path]
            values = _candidate_values_from_meta(meta)
            refs: list[EntityRef] = []
            for kind, raw_values in values.items():
                slug_map, label_map = existing_maps[kind]
                for value in raw_values:
                    inventory_entry = candidate_inventory[kind][normalize_label_key(value)]
                    ref = _resolve_entity(
                        kind=kind,
                        value=value,
                        meta_root=meta_root,
                        existing_by_slug=slug_map,
                        existing_by_label=label_map,
                        semantic_threshold=max(0.0, min(args.semantic_threshold, 1.0)),
                        block_words=block_words,
                        go_words=go_words,
                    )
                    policy = _policy_decision(
                        kind=kind,
                        value=value,
                        ref=ref,
                        inventory_entry=inventory_entry,
                        existing_by_label=label_map,
                        protected_cfg=protected_cfg,
                        block_words=block_words,
                        go_words=go_words,
                        semantic_threshold=max(0.0, min(args.semantic_threshold, 1.0)),
                    )
                    shadow_record = {
                        "note": note_rel,
                        "kind": kind,
                        "value": value,
                        "normalized_key": policy.normalized_key,
                        "entity_candidate": str(ref.file_path.relative_to(vault)),
                        "decision": policy.decision,
                        "reason": policy.reason,
                        "merge_target": policy.merge_target,
                        "protected": policy.protected,
                        "score_breakdown": policy.score_breakdown,
                    }
                    shadow_entities.append(shadow_record)
                    if policy.protected:
                        protected_hits.append(shadow_record)

                    if policy.decision != "keep":
                        deferred.append(
                            {
                                "type": "policy-gate",
                                "path": str(ref.file_path.relative_to(vault)),
                                "reason": f"{policy.decision}:{policy.reason}",
                            }
                        )
                        continue
                    refs.append(ref)
                    resolved.append(
                        {
                            "note": note_rel,
                            "kind": kind,
                            "value": value,
                            "entity": str(ref.file_path.relative_to(vault)),
                        }
                    )
                    if ref.file_path.exists():
                        _clear_ignored(ignore_state, _entity_ignore_key(kind, value))
                        already_present.append(
                            {
                                "kind": kind,
                                "entity": str(ref.file_path.relative_to(vault)),
                                "reason": "existing-entity",
                            }
                        )
                    else:
                        entity_key = _entity_ignore_key(kind, value)
                        if _is_ignored(ignore_state, entity_key, run_count):
                            deferred.append(
                                {
                                    "type": "entity-create",
                                    "path": str(ref.file_path.relative_to(vault)),
                                    "reason": "cooldown-ignore",
                                }
                            )
                            continue
                        if not args.writeback:
                            deferred.append(
                                {
                                    "type": "entity-create",
                                    "path": str(ref.file_path.relative_to(vault)),
                                    "reason": "read-only",
                                }
                            )
                            continue
                        if counters["entity_writes"] >= budgets["entity_writes"]:
                            deferred.append(
                                {
                                    "type": "entity-create",
                                    "path": str(ref.file_path.relative_to(vault)),
                                    "reason": "entity budget exhausted",
                                }
                            )
                            _mark_ignored(
                                ignore_state,
                                entity_key,
                                run_count=run_count,
                                cooldown_runs=args.ignore_cooldown_runs,
                                reason="entity budget exhausted",
                            )
                            continue
                        ref.file_path.parent.mkdir(parents=True, exist_ok=True)
                        ref.file_path.write_text(_build_entity_content(ref), encoding="utf-8")
                        counters["entity_writes"] += 1
                        slug_map[ref.slug.lower()] = ref.file_path
                        label_map[ref.value.lower()] = ref.file_path
                        _clear_ignored(ignore_state, entity_key)
                        linked.append(
                            {
                                "type": "entity-created",
                                "path": str(ref.file_path.relative_to(vault)),
                            }
                        )
                    touched_mocs[ref.moc_target] = ref.pillar
            note_to_entities[note_path] = refs

        for note_path, refs in note_to_entities.items():
            if not refs:
                continue
            note_rel = str(note_path.relative_to(vault))
            note_key = _note_ignore_key(note_rel)
            text = note_path.read_text(encoding="utf-8", errors="replace")
            required_links: list[str] = []
            for ref in refs:
                rel_no_ext = str(ref.file_path.relative_to(vault)).replace("\\", "/").removesuffix(".md")
                if _has_wikilink(text, rel_no_ext, ref.file_path.stem):
                    continue
                required_links.append(f"[[{rel_no_ext}|{ref.file_path.stem}]]")
            if not required_links:
                continue
            if not args.writeback:
                deferred.append(
                    {
                        "type": "note-link",
                        "path": note_rel,
                        "reason": f"read-only ({len(required_links)} missing)",
                    }
                )
                continue
            if _is_ignored(ignore_state, note_key, run_count):
                deferred.append(
                    {
                        "type": "note-link",
                        "path": note_rel,
                        "reason": "cooldown-ignore",
                    }
                )
                continue
            if counters["note_writes"] >= budgets["note_writes"]:
                deferred.append(
                    {
                        "type": "note-link",
                        "path": note_rel,
                        "reason": "note budget exhausted",
                    }
                )
                _mark_ignored(
                    ignore_state,
                    note_key,
                    run_count=run_count,
                    cooldown_runs=1,
                    reason="note budget exhausted",
                )
                continue
            updated = _append_links_block(text, "Otto Graph Links", required_links)
            note_path.write_text(updated, encoding="utf-8")
            counters["note_writes"] += 1
            _clear_ignored(ignore_state, note_key)
            linked.append(
                {
                    "type": "note-linked",
                    "path": note_rel,
                    "links_added": str(len(required_links)),
                }
            )

        for note_path, refs in note_to_entities.items():
            _ = note_path
            for ref in refs:
                if not ref.file_path.exists():
                    continue
                changed, missing = _ensure_file_with_links(
                    ref.file_path,
                    "Roll-Up",
                    [f"[[{ref.moc_target}]]", f"[[{ref.pillar}]]"],
                    args.writeback,
                    "entity_writes",
                    budgets,
                    counters,
                    deferred,
                )
                if changed:
                    linked.append(
                        {
                            "type": "entity-backlink",
                            "path": str(ref.file_path.relative_to(vault)),
                            "links_added": str(len(missing)),
                        }
                    )

        for pillar in PILLARS:
            pillar_path = meta_root / f"{pillar}.md"
            if pillar_path.exists():
                continue
            if not args.writeback:
                deferred.append({"type": "pillar-create", "path": str(pillar_path.relative_to(vault)), "reason": "read-only"})
                continue
            if counters["moc_writes"] >= budgets["moc_writes"]:
                deferred.append({"type": "pillar-create", "path": str(pillar_path.relative_to(vault)), "reason": "moc budget exhausted"})
                continue
            pillar_path.write_text(_build_pillar_moc(pillar), encoding="utf-8")
            counters["moc_writes"] += 1
            linked.append({"type": "pillar-created", "path": str(pillar_path.relative_to(vault))})

        for moc_name, pillar in sorted(touched_mocs.items()):
            if moc_name in CLUSTERS:
                moc_path = meta_root / f"{moc_name}.md"
                if not moc_path.exists():
                    if not args.writeback:
                        deferred.append({"type": "cluster-create", "path": str(moc_path.relative_to(vault)), "reason": "read-only"})
                        continue
                    if counters["moc_writes"] >= budgets["moc_writes"]:
                        deferred.append({"type": "cluster-create", "path": str(moc_path.relative_to(vault)), "reason": "moc budget exhausted"})
                        continue
                    moc_path.write_text(_build_cluster_moc(moc_name), encoding="utf-8")
                    counters["moc_writes"] += 1
                    linked.append({"type": "cluster-created", "path": str(moc_path.relative_to(vault))})
                changed, missing = _ensure_file_with_links(
                    moc_path,
                    "Roll-Up",
                    [f"[[{pillar}]]"],
                    args.writeback,
                    "moc_writes",
                    budgets,
                    counters,
                    deferred,
                )
                if changed:
                    linked.append({"type": "cluster-up-link", "path": str(moc_path.relative_to(vault)), "links_added": str(len(missing))})
            else:
                kind = "orientation" if moc_name == "ORIENTATION-FAMILY" else "allocation"
                moc_path = meta_root / kind / f"{moc_name}.md"
                if not moc_path.exists():
                    if not args.writeback:
                        deferred.append({"type": "family-create", "path": str(moc_path.relative_to(vault)), "reason": "read-only"})
                        continue
                    if counters["moc_writes"] >= budgets["moc_writes"]:
                        deferred.append({"type": "family-create", "path": str(moc_path.relative_to(vault)), "reason": "moc budget exhausted"})
                        continue
                    moc_path.write_text(_build_family_moc(kind, moc_name, pillar), encoding="utf-8")
                    counters["moc_writes"] += 1
                    linked.append({"type": "family-created", "path": str(moc_path.relative_to(vault))})
                changed, missing = _ensure_file_with_links(
                    moc_path,
                    "Roll-Up",
                    [f"[[{pillar}]]"],
                    args.writeback,
                    "moc_writes",
                    budgets,
                    counters,
                    deferred,
                )
                if changed:
                    linked.append({"type": "family-up-link", "path": str(moc_path.relative_to(vault)), "links_added": str(len(missing))})

        _save_cursor(cursor_path, next_index=next_index, note_count=len(notes))

        growth_ok = len(linked) <= sum(budgets.values()) and len(deferred) >= 0
        report = {
            "ts": now_iso(),
            "status": "ok" if not deferred else "partial",
            "vault": str(vault),
            "scope": args.scope,
            "writeback": bool(args.writeback),
            "noise_config_path": str(noise_path),
            "protected_config_path": str(protected_path),
            "block_words_count": len(block_words),
            "go_words_count": len(go_words),
            "note_count_total": len(notes),
            "note_count_batch": len(batch),
            "cursor_start": start_index,
            "cursor_next": next_index,
            "budgets": budgets,
            "writes_used": counters,
            "ignore_active_count": len(ignore_state.get("entries", {})),
            "resolved_entity_links": resolved[:300],
            "already_present": already_present[:300],
            "linked": linked[:300],
            "missing_or_deferred": deferred[:300],
            "graph_growth": {
                "gradual": growth_ok,
                "note": "bounded writes + cursor batching + canonical links only",
            },
        }
        shadow_artifact = _shadow_machine_artifact(entities=shadow_entities, protected_hits=protected_hits)
        out_json = (repo / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
        out_md = (repo / args.markdown_output).resolve() if not Path(args.markdown_output).is_absolute() else Path(args.markdown_output)
        shadow_json = (repo / args.shadow_output).resolve() if not Path(args.shadow_output).is_absolute() else Path(args.shadow_output)
        shadow_md = (repo / args.shadow_markdown_output).resolve() if not Path(args.shadow_markdown_output).is_absolute() else Path(args.shadow_markdown_output)
        shadow_review_md = (repo / args.shadow_review_output).resolve() if not Path(args.shadow_review_output).is_absolute() else Path(args.shadow_review_output)
        shadow_review_csv = (repo / args.shadow_review_csv_output).resolve() if not Path(args.shadow_review_csv_output).is_absolute() else Path(args.shadow_review_csv_output)
        demotion_plan_md = (repo / args.demotion_plan_output).resolve() if not Path(args.demotion_plan_output).is_absolute() else Path(args.demotion_plan_output)
        demotion_plan_json = (repo / args.demotion_plan_json_output).resolve() if not Path(args.demotion_plan_json_output).is_absolute() else Path(args.demotion_plan_json_output)
        graph_review_json = (repo / args.graph_demotion_review_output).resolve() if not Path(args.graph_demotion_review_output).is_absolute() else Path(args.graph_demotion_review_output)
        allo_hotspots_md = (repo / args.allo_hotspots_output).resolve() if not Path(args.allo_hotspots_output).is_absolute() else Path(args.allo_hotspots_output)
        demotion_plan_artifact = _demotion_plan_artifact(vault=vault, shadow_entities=shadow_entities, dry_run=bool(args.dry_run))
        if args.apply_demotion_plan and not args.dry_run:
            _apply_demotion_plan(vault=vault, artifact=demotion_plan_artifact, max_writes=args.max_demotion_writes)
        checkpoint_path, checkpoint_payload = _latest_graph_apply_checkpoint(repo)
        graph_review_artifact: dict[str, Any] | None = None
        if args.apply_demotion_plan and not args.dry_run:
            graph_review_artifact = _build_graph_demotion_review_artifact(
                vault=vault,
                demotion_plan_artifact=demotion_plan_artifact,
                shadow_artifact=shadow_artifact,
                checkpoint_payload=checkpoint_payload,
            )
            graph_review_artifact["source_apply_checkpoint_path"] = checkpoint_path
            graph_review_artifact["source_demotion_plan_json"] = str(demotion_plan_json)
            graph_review_artifact["source_shadow_review_markdown"] = str(shadow_review_md)
        report["shadow_graph"] = {
            "decision_count": len(shadow_entities),
            "protected_hits": len(protected_hits),
            "hidden_relations": len(shadow_artifact.get("hidden_relations", []) or []),
            "review_groups": len(shadow_artifact.get("review_groups", []) or []),
            "demotion_plan_count": int(demotion_plan_artifact.get("plan_count") or 0),
            "demotion_applied_count": int(demotion_plan_artifact.get("applied_count") or 0),
            "demotion_skipped_count": int(demotion_plan_artifact.get("skipped_count") or 0),
            "json": str(shadow_json),
            "markdown": str(shadow_md),
            "review_markdown": str(shadow_review_md),
            "review_csv": str(shadow_review_csv) if args.export_family_summary_csv else "",
            "demotion_plan_markdown": str(demotion_plan_md) if args.apply_demotion_plan else "",
            "demotion_plan_json": str(demotion_plan_json) if args.apply_demotion_plan else "",
            "graph_demotion_review_json": str(graph_review_json) if graph_review_artifact else "",
            "allo_hotspots_markdown": str(allo_hotspots_md),
        }
        write_json(out_json, report)
        write_json(shadow_json, shadow_artifact)
        if args.apply_demotion_plan:
            write_json(demotion_plan_json, demotion_plan_artifact)
        if graph_review_artifact:
            write_json(graph_review_json, graph_review_artifact)
        next_actions = []
        if graph_review_artifact and graph_review_artifact.get("recommended_next_action"):
            next_actions.append(str(graph_review_artifact["recommended_next_action"]))
        next_actions.extend(
            [
                "Continue bounded heartbeat batches",
                "Review deferred entity creations",
                "Review ALLO/TO/LACK shadow family proposals",
            ]
        )
        deduped_next_actions: list[str] = []
        seen_actions: set[str] = set()
        for item in next_actions:
            key = item.strip().lower()
            if not key or key in seen_actions:
                continue
            seen_actions.add(key)
            deduped_next_actions.append(item)
        bridge_packet = {
            "source": "graph-rollup-audit",
            "role": "c",
            "status": "handoff",
            "updated_at": report["ts"],
            "summary": f"status={report['status']} batch={report['note_count_batch']} linked={len(report['linked'])} deferred={len(report['missing_or_deferred'])}",
            "artifacts": [str(out_json), str(out_md), str(shadow_json), str(shadow_md), str(shadow_review_md), str(allo_hotspots_md)]
            + ([str(shadow_review_csv)] if args.export_family_summary_csv else [])
            + ([str(demotion_plan_md), str(demotion_plan_json)] if args.apply_demotion_plan else [])
            + ([str(graph_review_json)] if graph_review_artifact else []),
            "next_actions": deduped_next_actions,
            "next_action": deduped_next_actions[0] if deduped_next_actions else ("Review ALLO-specific hotspots and demotion previews" if args.apply_demotion_plan else "Review ALLO/TO/LACK shadow family proposals"),
            "language": "id",
        }
        write_json(_handoff_drop_path(repo, bridge_packet["updated_at"], bridge_packet["role"], bridge_packet["status"]), bridge_packet)
        write_json(ignore_path, ignore_state)

        md_lines = [
            "# Otto Graph Roll-Up Audit",
            "",
            f"- Status: `{report['status']}`",
            f"- Notes processed: `{report['note_count_batch']}` of `{report['note_count_total']}`",
            f"- Writes used: note `{counters['note_writes']}`, entity `{counters['entity_writes']}`, moc `{counters['moc_writes']}`",
            "",
            "## Resolved Entity Links",
        ]
        if report["resolved_entity_links"]:
            for item in report["resolved_entity_links"][:20]:
                md_lines.append(
                    f"- `{item['note']}` -> `{item['kind']}` `{item['value']}` -> `{item['entity']}`"
                )
        else:
            md_lines.append("- none")
        md_lines += ["", "## Missing Or Deferred"]
        if report["missing_or_deferred"]:
            for item in report["missing_or_deferred"][:20]:
                md_lines.append(f"- `{item['type']}` `{item['path']}` ({item['reason']})")
        else:
            md_lines.append("- none")
        md_lines += [
            "",
            "## Graph Growth",
            f"- gradual_non_noisy: `{str(report['graph_growth']['gradual']).lower()}`",
            f"- policy: {report['graph_growth']['note']}",
            "",
            "## Shadow Graph",
            f"- decisions: `{report['shadow_graph']['decision_count']}`",
            f"- protected_hits: `{report['shadow_graph']['protected_hits']}`",
            f"- hidden_relations: `{report['shadow_graph']['hidden_relations']}`",
            f"- review_groups: `{report['shadow_graph']['review_groups']}`",
            f"- demotion_plan_count: `{report['shadow_graph']['demotion_plan_count']}`",
            f"- demotion_applied_count: `{report['shadow_graph']['demotion_applied_count']}`",
            f"- demotion_skipped_count: `{report['shadow_graph']['demotion_skipped_count']}`",
            "",
        ]
        if graph_review_artifact:
            md_lines += [
                "## Graph Demotion Review",
                f"- reviewed_note_count: `{graph_review_artifact['reviewed_note_count']}`",
                f"- quality_verdict: `{graph_review_artifact['quality_verdict']}`",
                f"- graph_readability_verdict: `{graph_review_artifact['graph_readability_verdict']}`",
                f"- recommended_next_apply_mode: `{graph_review_artifact['recommended_next_apply_mode']}`",
                f"- primary_hotspot_family: `{graph_review_artifact['primary_hotspot_family']}`",
                f"- recommended_next_action: {graph_review_artifact['recommended_next_action']}",
                "",
            ]
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text("\n".join(md_lines), encoding="utf-8")
        shadow_md.parent.mkdir(parents=True, exist_ok=True)
        shadow_md.write_text(_shadow_markdown(shadow_artifact), encoding="utf-8")
        shadow_review_md.parent.mkdir(parents=True, exist_ok=True)
        shadow_review_md.write_text(_shadow_review_markdown(shadow_artifact), encoding="utf-8")
        allo_hotspots_md.parent.mkdir(parents=True, exist_ok=True)
        allo_hotspots_md.write_text(_allo_hotspots_markdown(shadow_artifact), encoding="utf-8")
        if args.apply_demotion_plan:
            demotion_plan_md.parent.mkdir(parents=True, exist_ok=True)
            demotion_plan_md.write_text(_demotion_plan_markdown(demotion_plan_artifact), encoding="utf-8")
        if args.export_family_summary_csv:
                _write_shadow_family_csv(
                    shadow_review_csv,
                    shadow_artifact,
                    family_prefix=args.family_prefix,
                    only_triage=args.only_triage,
                    only_action=args.only_action,
                )

        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
        summary = {
            "ts": report["ts"],
            "status": report["status"],
            "note_count_batch": report["note_count_batch"],
            "note_count_total": report["note_count_total"],
            "writes_used": report["writes_used"],
            "block_words_count": report["block_words_count"],
            "go_words_count": report["go_words_count"],
            "ignore_active_count": report["ignore_active_count"],
            "resolved_count": len(report["resolved_entity_links"]),
            "already_present_count": len(report["already_present"]),
            "linked_count": len(report["linked"]),
            "deferred_count": len(report["missing_or_deferred"]),
            "shadow_decision_count": report["shadow_graph"]["decision_count"],
            "shadow_hidden_relation_count": report["shadow_graph"]["hidden_relations"],
            "shadow_review_group_count": report["shadow_graph"]["review_groups"],
            "shadow_demotion_plan_count": report["shadow_graph"]["demotion_plan_count"],
            "shadow_demotion_applied_count": report["shadow_graph"]["demotion_applied_count"],
            "shadow_demotion_skipped_count": report["shadow_graph"]["demotion_skipped_count"],
            "graph_gradual": report["graph_growth"]["gradual"],
            "report_json": str(out_json),
            "report_md": str(out_md),
            "shadow_json": str(shadow_json),
            "shadow_md": str(shadow_md),
            "shadow_review_md": str(shadow_review_md),
            "shadow_review_csv": str(shadow_review_csv) if args.export_family_summary_csv else "",
            "demotion_plan_md": str(demotion_plan_md) if args.apply_demotion_plan else "",
            "demotion_plan_json": str(demotion_plan_json) if args.apply_demotion_plan else "",
            "graph_demotion_review_json": str(graph_review_json) if graph_review_artifact else "",
            "allo_hotspots_md": str(allo_hotspots_md),
        }
        if args.apply_demotion_plan and args.dry_run:
            print(_demotion_plan_markdown(demotion_plan_artifact))
        elif args.apply_demotion_plan:
            payload_to_print = report if args.print_full else summary
            print(json.dumps(payload_to_print, ensure_ascii=False, indent=2))
        elif args.print_family_summary:
            print(
                _shadow_family_summary_table(
                    shadow_artifact,
                    family_prefix=args.family_prefix,
                    only_triage=args.only_triage,
                    only_action=args.only_action,
                    top_family_rows=args.top_family_rows,
                )
            )
        else:
            payload_to_print = report if args.print_full else summary
            print(json.dumps(payload_to_print, ensure_ascii=False, indent=2))
        return 0
    finally:
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
