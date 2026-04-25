from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_paths
from .state import now_iso, read_json, write_json


CANONICAL_CRON_TZ = "Asia/Bangkok"
APPROVED_MEMORY_DREAMING_EXPR = "0 11 * * *"
DREAM_REPORT_TITLES = {
    "light": "Light Sleep",
    "rem": "REM Sleep",
    "deep": "Deep Sleep",
}
_INLINE_DREAM_MARKER_RE = re.compile(r"<!--\s*openclaw:dreaming:.*?-->", re.IGNORECASE)
_INLINE_DREAM_START_RE = re.compile(r"<!--\s*openclaw:dreaming:[^:]+:start\s*-->", re.IGNORECASE)
_INLINE_DREAM_END_RE = re.compile(r"<!--\s*openclaw:dreaming:[^:]+:end\s*-->", re.IGNORECASE)
_DATE_STEM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DREAM_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_CONTAMINATION_PATTERNS = (
    re.compile(r"memory/\.dreams/session-corpus/", re.IGNORECASE),
    re.compile(r"\bSystem\s*\(untrusted\)\b", re.IGNORECASE),
    re.compile(r"\bHEARTBEAT_OK\b", re.IGNORECASE),
    re.compile(r"\bheartbeat-ok\b", re.IGNORECASE),
    re.compile(r"\bexec completed\b", re.IGNORECASE),
    re.compile(r"openclaw:dreaming", re.IGNORECASE),
)


@dataclass
class _Section:
    heading: str | None
    lines: list[str]


def live_openclaw_jobs_path() -> Path:
    return Path.home() / ".openclaw" / "cron" / "jobs.json"


def openclaw_cron_contract_path() -> Path:
    return load_paths().state_root / "openclaw" / "cron_contract_v1.json"


def _clone_json(data: Any) -> Any:
    return json.loads(json.dumps(data))


def _managed_otto_job(job: dict[str, Any]) -> bool:
    name = str(job.get("name") or "")
    description = str(job.get("description") or "")
    return (
        name.startswith("otto_")
        or name == "Otto Morning Brief 09:00"
        or name == "Memory Dreaming Promotion"
        or "[managed-by=otto." in description
        or "[managed-by=memory-core.short-term-promotion]" in description
    )


def _job_issue_messages(job: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not _managed_otto_job(job):
        return issues
    schedule = job.get("schedule") or {}
    if not isinstance(schedule, dict) or schedule.get("kind") != "cron":
        return issues
    name = str(job.get("name") or job.get("id") or "unknown-job")
    tz = str(schedule.get("tz") or "").strip()
    if tz != CANONICAL_CRON_TZ:
        issues.append(f"{name}: cron timezone should be {CANONICAL_CRON_TZ}")
    if name == "Memory Dreaming Promotion":
        expr = str(schedule.get("expr") or "").strip()
        if expr != APPROVED_MEMORY_DREAMING_EXPR:
            issues.append(
                f"{name}: cron expression should be {APPROVED_MEMORY_DREAMING_EXPR} instead of {expr or '(missing)'}"
            )
    return issues


def _normalize_job(job: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    normalized = _clone_json(job)
    observed_issues = _job_issue_messages(normalized)
    fixes_applied: list[str] = []
    if not _managed_otto_job(normalized):
        return normalized, observed_issues, fixes_applied

    schedule = normalized.get("schedule") or {}
    if not isinstance(schedule, dict) or schedule.get("kind") != "cron":
        return normalized, observed_issues, fixes_applied

    name = str(normalized.get("name") or normalized.get("id") or "unknown-job")
    if str(schedule.get("tz") or "").strip() != CANONICAL_CRON_TZ:
        schedule["tz"] = CANONICAL_CRON_TZ
        fixes_applied.append(f"{name}: set cron timezone to {CANONICAL_CRON_TZ}")
    if name == "Memory Dreaming Promotion" and str(schedule.get("expr") or "").strip() != APPROVED_MEMORY_DREAMING_EXPR:
        schedule["expr"] = APPROVED_MEMORY_DREAMING_EXPR
        fixes_applied.append(f"{name}: moved cron schedule to {APPROVED_MEMORY_DREAMING_EXPR}")
    normalized["schedule"] = schedule
    return normalized, observed_issues, fixes_applied


def _job_contract(job: dict[str, Any]) -> dict[str, Any]:
    schedule = job.get("schedule") or {}
    payload = job.get("payload") or {}
    delivery = job.get("delivery") or {}
    return {
        "job_id": job.get("id"),
        "job_key": job.get("name"),
        "description": job.get("description"),
        "enabled": bool(job.get("enabled", False)),
        "schedule": {
            "kind": schedule.get("kind"),
            "expr": schedule.get("expr"),
            "tz": schedule.get("tz"),
        },
        "wake_mode": job.get("wakeMode"),
        "session_target": job.get("sessionTarget"),
        "payload_kind": payload.get("kind"),
        "delivery_mode": delivery.get("mode"),
        "source": "live-jobs.json",
    }


def sync_openclaw_cron_contract(
    jobs_path: Path | None = None,
    contract_path: Path | None = None,
    *,
    apply_fixes: bool = True,
) -> dict[str, Any]:
    live_jobs_path = jobs_path or live_openclaw_jobs_path()
    target_contract_path = contract_path or openclaw_cron_contract_path()
    payload = read_json(live_jobs_path, default=None)
    if not isinstance(payload, dict):
        result = {
            "ok": False,
            "reason": "jobs-json-missing-or-invalid",
            "jobs_path": str(live_jobs_path),
            "contract_path": str(target_contract_path),
            "sync_performed": False,
            "observed_issues": [],
            "current_issues": ["jobs.json missing or invalid"],
        }
        write_json(target_contract_path, result)
        return result

    raw_jobs = payload.get("jobs") or []
    normalized_jobs: list[dict[str, Any]] = []
    observed_issues: list[str] = []
    fixes_applied: list[str] = []
    changed = False
    for raw_job in raw_jobs:
        job = raw_job if isinstance(raw_job, dict) else {}
        normalized_job, job_issues, job_fixes = _normalize_job(job)
        normalized_jobs.append(normalized_job)
        observed_issues.extend(job_issues)
        fixes_applied.extend(job_fixes)
        changed = changed or normalized_job != job

    effective_jobs = normalized_jobs if apply_fixes else [_clone_json(job) for job in raw_jobs if isinstance(job, dict)]

    if apply_fixes and changed:
        updated_payload = _clone_json(payload)
        updated_payload["jobs"] = normalized_jobs
        write_json(live_jobs_path, updated_payload)

    current_issues = []
    for job in effective_jobs:
        current_issues.extend(_job_issue_messages(job))

    contract = {
        "version": "1.0.0",
        "generated_at": now_iso(),
        "timezone": CANONICAL_CRON_TZ,
        "scheduler_store": str(live_jobs_path),
        "generated_from": "live-jobs.json",
        "validation": {
            "drift_free": not current_issues,
            "observed_issues": observed_issues,
            "current_issues": current_issues,
            "fixes_applied": fixes_applied,
            "apply_fixes": apply_fixes,
        },
        "jobs": [_job_contract(job) for job in effective_jobs],
    }
    write_json(target_contract_path, contract)
    return {
        "ok": True,
        "reason": "cron-contract-synced",
        "jobs_path": str(live_jobs_path),
        "contract_path": str(target_contract_path),
        "sync_performed": bool(apply_fixes and changed),
        "job_count": len(effective_jobs),
        "observed_issues": observed_issues,
        "current_issues": current_issues,
        "fixes_applied": fixes_applied,
    }


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _DREAM_FRONTMATTER_RE.match(text)
    if not match:
        return {}, text.strip()
    metadata: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in match.group(1).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and current_key == "tags":
            metadata.setdefault("tags", []).append(stripped[2:].strip())
            continue
        if ":" not in line:
            current_key = None
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if current_key == "tags":
            metadata["tags"] = []
            if value:
                metadata["tags"].append(value)
            continue
        metadata[current_key] = value
    body = text[match.end():].strip()
    return metadata, body


def _dump_frontmatter(metadata: dict[str, Any]) -> str:
    ordered_keys = [
        "title",
        "type",
        "phase",
        "status",
        "generated_by",
        "artifact_lane",
        "date",
        "created",
        "updated",
    ]
    lines = ["---"]
    for key in ordered_keys:
        value = metadata.get(key)
        if value:
            lines.append(f"{key}: {value}")
    tags = [str(tag).strip() for tag in (metadata.get("tags") or []) if str(tag).strip()]
    lines.append("tags:")
    for tag in tags:
        lines.append(f"  - {tag}")
    lines.append("---")
    return "\n".join(lines)


def _has_contamination(text: str) -> bool:
    return any(pattern.search(text) for pattern in _CONTAMINATION_PATTERNS)


def _split_sections(lines: list[str]) -> list[_Section]:
    sections: list[_Section] = []
    current = _Section(heading=None, lines=[])
    for line in lines:
        if line.startswith("#"):
            if current.heading is not None or current.lines:
                sections.append(current)
            current = _Section(heading=line, lines=[])
            continue
        current.lines.append(line)
    if current.heading is not None or current.lines:
        sections.append(current)
    return sections


def _filter_section_lines(lines: list[str]) -> list[str]:
    filtered: list[str] = []
    current_block: list[str] = []

    def flush_block() -> None:
        nonlocal current_block
        if not current_block:
            return
        block_text = "\n".join(current_block)
        if not _has_contamination(block_text):
            filtered.extend(current_block)
        current_block = []

    for line in lines:
        if _INLINE_DREAM_MARKER_RE.search(line):
            continue
        if line.startswith("- "):
            flush_block()
            current_block = [line]
            continue
        if current_block:
            if line.startswith("  ") or not line.strip():
                current_block.append(line)
                continue
            flush_block()
        if _has_contamination(line):
            continue
        filtered.append(line)
    flush_block()
    while filtered and not filtered[0].strip():
        filtered.pop(0)
    while filtered and not filtered[-1].strip():
        filtered.pop()
    return filtered


def _ensure_section_defaults(sections: list[_Section], phase: str) -> list[str]:
    lines: list[str] = []
    if phase == "rem":
        defaults = {
            "### Reflections": ["- No stable reflection themes survived Otto sanitation."],
            "### Possible Lasting Truths": ["- No strong candidate truths surfaced."],
        }
        seen: set[str] = set()
        for section in sections:
            heading = section.heading or ""
            content = section.lines[:]
            if heading in defaults:
                seen.add(heading)
                if not any(line.startswith("- ") for line in content):
                    content = defaults[heading][:]
            if heading:
                if lines:
                    lines.append("")
                lines.append(heading)
            lines.extend(content or defaults.get(heading, []))
        for heading, default_lines in defaults.items():
            if heading in seen:
                continue
            if lines:
                lines.append("")
            lines.append(heading)
            lines.extend(default_lines)
        return lines

    if phase == "light":
        heading = next((section.heading for section in sections if section.heading), "# Light Sleep")
        body_lines = []
        for section in sections:
            if section.heading and section.heading != heading:
                body_lines.append("")
                body_lines.append(section.heading)
            body_lines.extend(section.lines)
        kept_bullets = [line for line in body_lines if line.startswith("- ")]
        fallback = ["- No candidate memories survived Otto sanitation."]
        return [heading, ""] + (body_lines if kept_bullets else fallback)

    if phase == "deep":
        heading = next((section.heading for section in sections if section.heading), "# Deep Sleep")
        body_lines = []
        for section in sections:
            if section.heading and section.heading != heading:
                body_lines.append("")
                body_lines.append(section.heading)
            body_lines.extend(section.lines)
        if any(line.startswith("- ") for line in body_lines):
            return [heading, ""] + body_lines
        return [
            heading,
            "",
            "- Ranked 0 candidate(s) for durable promotion.",
            "- Promoted 0 candidate(s) into MEMORY.md.",
        ]

    merged: list[str] = []
    for section in sections:
        if section.heading:
            if merged:
                merged.append("")
            merged.append(section.heading)
        merged.extend(section.lines)
    return merged


def _normalize_dream_report(report_path: Path, *, phase: str) -> tuple[bool, bool]:
    original = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else ""
    metadata, body = _parse_frontmatter(original)
    report_date = report_path.stem if _DATE_STEM_RE.match(report_path.stem) else now_iso()[:10]
    created = str(metadata.get("created") or now_iso())
    changed = False

    metadata["title"] = f"Dreaming Report — {DREAM_REPORT_TITLES.get(phase, phase.title())} — {report_date}"
    metadata["type"] = "dream-report"
    metadata["phase"] = phase
    metadata["status"] = "generated"
    metadata["generated_by"] = "openclaw-memory-core"
    metadata["artifact_lane"] = "memory-dreaming"
    metadata["date"] = report_date
    metadata["created"] = created
    metadata["updated"] = now_iso()
    metadata["tags"] = ["generated", "dreaming", "memory-core", "artifact"]

    lines = body.splitlines()
    sections = _split_sections(_filter_section_lines(lines))
    normalized_lines = _ensure_section_defaults(sections, phase)
    normalized_text = _dump_frontmatter(metadata) + "\n" + "\n".join(normalized_lines).strip() + "\n"
    if normalized_text != original:
        report_path.write_text(normalized_text, encoding="utf-8")
        changed = True
    return changed, bool(original)


def _strip_inline_dreaming_blocks(note_path: Path) -> bool:
    original = note_path.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()
    cleaned: list[str] = []
    in_block = False
    changed = False
    for line in lines:
        if _INLINE_DREAM_START_RE.search(line):
            in_block = True
            changed = True
            continue
        if _INLINE_DREAM_END_RE.search(line):
            in_block = False
            changed = True
            continue
        if in_block:
            changed = True
            continue
        if _INLINE_DREAM_MARKER_RE.search(line):
            changed = True
            continue
        cleaned.append(line)

    while len(cleaned) > 1 and not cleaned[-1].strip():
        cleaned.pop()
    normalized = "\n".join(cleaned).rstrip() + "\n"
    if changed and normalized != original:
        note_path.write_text(normalized, encoding="utf-8")
    return changed and normalized != original


def sanitize_generated_dreaming_artifacts(vault_path: Path | None = None) -> dict[str, Any]:
    paths = load_paths()
    target_vault = vault_path or getattr(paths, "vault_path", None)
    if target_vault is None:
        return {
            "ok": False,
            "reason": "vault-path-missing",
            "report_files_changed": [],
            "daily_notes_changed": [],
        }

    report_files_changed: list[str] = []
    daily_notes_changed: list[str] = []
    memory_root = target_vault / "memory"
    dreaming_root = memory_root / "dreaming"

    for phase in ("light", "rem", "deep"):
        phase_dir = dreaming_root / phase
        if not phase_dir.exists():
            continue
        for report_path in sorted(phase_dir.glob("*.md")):
            changed, _ = _normalize_dream_report(report_path, phase=phase)
            if changed:
                report_files_changed.append(str(report_path))

    if memory_root.exists():
        for note_path in sorted(memory_root.glob("*.md")):
            if _DATE_STEM_RE.match(note_path.stem) and _strip_inline_dreaming_blocks(note_path):
                daily_notes_changed.append(str(note_path))

    result = {
        "ok": True,
        "reason": "dreaming-artifacts-sanitized",
        "vault_path": str(target_vault),
        "report_files_changed": report_files_changed,
        "daily_notes_changed": daily_notes_changed,
        "report_change_count": len(report_files_changed),
        "daily_note_change_count": len(daily_notes_changed),
    }
    write_json(paths.state_root / "openclaw" / "dreaming_guardrails.json", result)
    return result
