from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..logging_utils import get_logger
from ..state import now_iso, read_json, write_json


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "training-item"


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_frontmatter_value(text: str, key: str) -> str | None:
    match = re.search(rf"(?im)^{re.escape(key)}:\s*(.+?)\s*$", text)
    if not match:
        return None
    return match.group(1).strip().strip("'\"")


def _split_frontmatter(text: str) -> tuple[list[str], list[str], bool]:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return [], lines, False
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index], lines[index + 1 :], True
    return [], lines, False


def _upsert_frontmatter(text: str, updates: dict[str, str]) -> str:
    frontmatter_lines, body_lines, has_frontmatter = _split_frontmatter(text)
    if not has_frontmatter:
        frontmatter_lines = []
    keys_seen: set[str] = set()
    updated_lines: list[str] = []
    for line in frontmatter_lines:
        match = re.match(r"^([A-Za-z0-9_]+):", line.strip())
        if not match:
            updated_lines.append(line)
            continue
        key = match.group(1)
        if key in updates:
            updated_lines.append(f"{key}: {updates[key]}")
            keys_seen.add(key)
        else:
            updated_lines.append(line)
    for key, value in updates.items():
        if key not in keys_seen:
            updated_lines.append(f"{key}: {value}")
    rebuilt = ["---", *updated_lines, "---"]
    if body_lines:
        rebuilt.extend(body_lines)
    return "\n".join(rebuilt).rstrip() + "\n"


def _body_section(text: str, heading: str) -> str:
    marker = f"{heading}\n"
    if marker not in text:
        return ""
    chunk = text.split(marker, 1)[1]
    next_heading = re.split(r"\n##\s+", chunk, maxsplit=1)
    return next_heading[0].strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-/]*", text))


def _is_substantive_answer(text: str, *, min_words: int, min_chars: int) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped in {"-", "(none)", "(todo)", "todo"}:
        return False
    return len(stripped) >= min_chars and _word_count(stripped) >= min_words


@dataclass
class MentorProbe:
    probe_id: str
    weakness_key: str
    weakness: str
    title: str
    note_name: str
    status: str = "pending"
    gap_type: str = "unknown"
    path: str | None = None
    created_at: str | None = None
    answered_at: str | None = None
    explanation: str = ""
    application: str = ""
    uncertainty: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "weakness_key": self.weakness_key,
            "weakness": self.weakness,
            "title": self.title,
            "note_name": self.note_name,
            "status": self.status,
            "gap_type": self.gap_type,
            "path": self.path,
            "created_at": self.created_at,
            "answered_at": self.answered_at,
            "explanation": self.explanation,
            "application": self.application,
            "uncertainty": self.uncertainty,
        }


@dataclass
class MentorTask:
    task_id: str
    weakness_key: str
    weakness: str
    title: str
    prompt: str
    completion_signal: str
    note_name: str
    gap_type: str = "unknown"
    probe_id: str | None = None
    status: str = "pending"
    path: str | None = None
    created_at: str | None = None
    resolved_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "weakness_key": self.weakness_key,
            "weakness": self.weakness,
            "title": self.title,
            "prompt": self.prompt,
            "completion_signal": self.completion_signal,
            "note_name": self.note_name,
            "gap_type": self.gap_type,
            "probe_id": self.probe_id,
            "status": self.status,
            "path": self.path,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


@dataclass
class MentorRunResult:
    ts: str
    state_path: str
    report_path: str
    queue_root: str
    active_probes: list[MentorProbe] = field(default_factory=list)
    pending_tasks: list[MentorTask] = field(default_factory=list)
    completed_tasks: list[MentorTask] = field(default_factory=list)
    skipped_tasks: list[MentorTask] = field(default_factory=list)
    weakness_registry: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_probe: MentorProbe | None = None
    created_task: MentorTask | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "state_path": self.state_path,
            "report_path": self.report_path,
            "queue_root": self.queue_root,
            "active_probes": [item.as_dict() for item in self.active_probes],
            "pending_tasks": [item.as_dict() for item in self.pending_tasks],
            "completed_tasks": [item.as_dict() for item in self.completed_tasks],
            "skipped_tasks": [item.as_dict() for item in self.skipped_tasks],
            "weakness_registry": self.weakness_registry,
            "created_probe": self.created_probe.as_dict() if self.created_probe else None,
            "created_task": self.created_task.as_dict() if self.created_task else None,
        }


class MentoringEngine:
    TRAINING_ROOT = ".Otto-Realm/Training"

    def __init__(self) -> None:
        self.paths = load_paths()
        if self.paths.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        self.vault_path = self.paths.vault_path
        self.logger = get_logger("otto.mentor")
        self.training_root = self.vault_path / self.TRAINING_ROOT
        self.pending_dir = self.training_root / "pending"
        self.done_dir = self.training_root / "done"
        self.skipped_dir = self.training_root / "skipped"
        self.probes_dir = self.training_root / "probes"
        self.state_path = self.paths.state_root / "kairos" / "mentor_latest.json"
        self.report_path = self.paths.artifacts_root / "reports" / "mentor_daily.md"

    def run(self, *, profile: dict[str, Any]) -> MentorRunResult:
        self._ensure_dirs()
        existing = read_json(self.state_path, default={}) or {}

        completed_tasks = self._read_task_dir(self.done_dir, status="done")
        skipped_tasks = self._read_task_dir(self.skipped_dir, status="skipped")
        resolved_tasks = [*completed_tasks, *skipped_tasks]
        resolved_map = {item.task_id: item for item in resolved_tasks}
        pending_tasks = [
            item for item in self._read_task_dir(self.pending_dir, status="pending")
            if item.task_id not in resolved_map
        ]
        self._prune_resolved_pending(resolved_map)

        probes = self._read_probe_dir(self.probes_dir)
        probes = [self._synchronize_probe_metadata(item) for item in probes]
        active_probes = [item for item in probes if item.status == "pending"]

        risks = list(profile.get("profile_cognitive_risks", []) or profile.get("cognitive_risks", []) or [])
        weakness_registry = self._build_weakness_registry(
            risks=risks,
            probes=probes,
            pending_tasks=pending_tasks,
            completed_tasks=completed_tasks,
            skipped_tasks=skipped_tasks,
        )

        created_probe: MentorProbe | None = None
        created_task: MentorTask | None = None
        all_tasks = [*pending_tasks, *completed_tasks, *skipped_tasks]
        for weakness in risks:
            weakness_key = self._weakness_key(weakness)
            registry = weakness_registry.get(weakness_key, {})
            if self._has_active_item(registry):
                continue
            latest_probe = registry.get("latest_probe")
            if latest_probe and latest_probe.get("status") == "answered":
                if latest_probe.get("gap_type") in {"theory_gap", "application_gap"} and not self._probe_has_task(
                    probe_id=str(latest_probe.get("probe_id") or ""),
                    tasks=all_tasks,
                ):
                    created_task = self._write_pending_task(
                        self._task_from_probe(
                            weakness=weakness,
                            weakness_key=weakness_key,
                            probe_id=str(latest_probe.get("probe_id") or ""),
                            gap_type=str(latest_probe.get("gap_type") or "unknown"),
                        )
                    )
                    pending_tasks.append(created_task)
                    all_tasks.append(created_task)
                    registry["latest_task"] = created_task.as_dict()
                    break
                if registry.get("last_resolution_outcome") in {"done", "skipped"}:
                    created_probe = self._write_probe(self._probe_from_risk(weakness=weakness, weakness_key=weakness_key))
                    active_probes.append(created_probe)
                    registry["latest_probe"] = created_probe.as_dict()
                    registry["latest_gap_type"] = created_probe.gap_type
                    break
                continue
            created_probe = self._write_probe(self._probe_from_risk(weakness=weakness, weakness_key=weakness_key))
            active_probes.append(created_probe)
            weakness_registry.setdefault(weakness_key, self._new_registry_entry(weakness, weakness_key))
            weakness_registry[weakness_key]["latest_probe"] = created_probe.as_dict()
            weakness_registry[weakness_key]["latest_gap_type"] = created_probe.gap_type
            break

        result = MentorRunResult(
            ts=now_iso(),
            state_path=str(self.state_path),
            report_path=str(self.report_path),
            queue_root=str(self.training_root),
            active_probes=active_probes,
            pending_tasks=pending_tasks,
            completed_tasks=completed_tasks,
            skipped_tasks=skipped_tasks,
            weakness_registry=weakness_registry,
            created_probe=created_probe,
            created_task=created_task,
        )
        self._write_state(existing=existing, result=result)
        self._write_report(result)
        self.logger.info(
            "[mentor] probes=%s pending=%s done=%s skipped=%s created_probe=%s created_task=%s",
            len(result.active_probes),
            len(result.pending_tasks),
            len(result.completed_tasks),
            len(result.skipped_tasks),
            bool(result.created_probe),
            bool(result.created_task),
        )
        return result

    def load_state_snapshot(self) -> dict[str, Any]:
        snapshot = read_json(self.state_path, default={}) or {}
        if snapshot:
            return snapshot
        self._ensure_dirs()
        active_probes = [item.as_dict() for item in self._read_probe_dir(self.probes_dir) if item.status == "pending"]
        pending_tasks = [item.as_dict() for item in self._read_task_dir(self.pending_dir, status="pending")]
        completed_tasks = [item.as_dict() for item in self._read_task_dir(self.done_dir, status="done")]
        skipped_tasks = [item.as_dict() for item in self._read_task_dir(self.skipped_dir, status="skipped")]
        return {
            "ts": now_iso(),
            "queue_root": str(self.training_root),
            "active_probes": active_probes,
            "pending_tasks": pending_tasks,
            "completed_tasks": completed_tasks,
            "skipped_tasks": skipped_tasks,
            "weakness_registry": {},
            "feedback_loop_ready": True,
        }

    def list_pending_tasks(self) -> list[MentorTask]:
        self._ensure_dirs()
        return self._read_task_dir(self.pending_dir, status="pending")

    def resolve_pending_task(self, *, task_id: str, outcome: str) -> MentorTask | None:
        normalized_outcome = outcome.strip().lower()
        if normalized_outcome not in {"done", "skipped"}:
            raise ValueError(f"Unsupported outcome: {outcome}")
        for task in self.list_pending_tasks():
            if task.task_id != task_id:
                continue
            source_path = Path(task.path or "")
            if not source_path.exists():
                return None
            resolved_at = now_iso()
            raw = source_path.read_text(encoding="utf-8", errors="replace")
            raw = _upsert_frontmatter(
                raw,
                {
                    "status": normalized_outcome,
                    "resolved_at": resolved_at,
                },
            )
            target_dir = self.done_dir if normalized_outcome == "done" else self.skipped_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / source_path.name
            if target_path.exists():
                target_path = target_dir / f"{source_path.stem}-{normalized_outcome}.md"
            target_path.write_text(raw, encoding="utf-8")
            source_path.unlink(missing_ok=True)
            task.status = normalized_outcome
            task.resolved_at = resolved_at
            task.path = str(target_path)
            return task
        return None

    def _ensure_dirs(self) -> None:
        for path in (self.training_root, self.pending_dir, self.done_dir, self.skipped_dir, self.probes_dir):
            path.mkdir(parents=True, exist_ok=True)

    def _weakness_key(self, weakness: str) -> str:
        lowered = weakness.lower()
        if "commitments can be forgotten" in lowered:
            return "commitment-recall"
        if "overload and confusion" in lowered:
            return "overload-confusion"
        if "context switching" in lowered:
            return "context-switching"
        if "stop conditions" in lowered or "long-running loops" in lowered:
            return "stop-triggers"
        return _slugify(weakness)[:64]

    def _probe_from_risk(self, *, weakness: str, weakness_key: str) -> MentorProbe:
        title = self._probe_title(weakness)
        created_at = now_iso()
        title_key = _slugify(title)
        probe_id = f"probe-{title_key}-{created_at[:10]}"
        return MentorProbe(
            probe_id=probe_id,
            weakness_key=weakness_key,
            weakness=weakness,
            title=title,
            note_name=f"{created_at[:10]}-{title_key}.md",
            created_at=created_at,
        )

    def _probe_title(self, weakness: str) -> str:
        lowered = weakness.lower()
        if "commitments can be forgotten" in lowered:
            return "commitment continuity probe"
        if "overload and confusion" in lowered:
            return "narrowing probe"
        if "context switching" in lowered:
            return "re-entry probe"
        if "stop conditions" in lowered or "long-running loops" in lowered:
            return "stop-trigger probe"
        return "bounded reflection probe"

    def _task_from_probe(self, *, weakness: str, weakness_key: str, probe_id: str, gap_type: str) -> MentorTask:
        title, prompt = self._task_template(weakness=weakness, gap_type=gap_type)
        created_at = now_iso()
        return MentorTask(
            task_id=f"mentor-{probe_id}-{_slugify(title)}",
            weakness_key=weakness_key,
            weakness=weakness,
            title=title,
            prompt=prompt,
            completion_signal="Move this note to done/ or skipped/ after Josh makes a bounded attempt.",
            note_name=f"{created_at[:10]}-{weakness_key}-{_slugify(title)}.md",
            gap_type=gap_type,
            probe_id=probe_id,
            created_at=created_at,
        )

    def _task_template(self, *, weakness: str, gap_type: str) -> tuple[str, str]:
        lowered = weakness.lower()
        if gap_type == "theory_gap":
            if "commitments can be forgotten" in lowered:
                return (
                    "continuity concept drill",
                    "Explain the continuity risk in your own words, then write the one commitment that would most benefit from an external recall anchor.",
                )
            if "overload and confusion" in lowered:
                return (
                    "narrowing concept drill",
                    "Define what makes the current pressure confusing, then reduce it to one decision rule Josh can reuse.",
                )
            if "context switching" in lowered:
                return (
                    "re-entry concept drill",
                    "Describe what a strong re-entry anchor is, then write one example anchor for an active thread.",
                )
            if "stop conditions" in lowered or "long-running loops" in lowered:
                return (
                    "stop-trigger concept drill",
                    "Define the difference between complete, paused, and dropped work for one active loop.",
                )
            return (
                "concept clarification drill",
                "Write the concept in your own words, then state the single rule Josh should remember next time.",
            )
        if "commitments can be forgotten" in lowered:
            return (
                "continuity recall drill",
                "Write the one commitment most likely to slip this week, then write the smallest next action that proves it is still alive.",
            )
        if "overload and confusion" in lowered:
            return (
                "one-step narrowing drill",
                "Take the most confusing active pressure and collapse it into one concrete next step with a visible stop trigger.",
            )
        if "context switching" in lowered:
            return (
                "re-entry anchor drill",
                "Pick one active thread and write the exact resume anchor Josh should see first on re-entry.",
            )
        if "stop conditions" in lowered or "long-running loops" in lowered:
            return (
                "stop-trigger drill",
                "Choose one ongoing loop and define the condition that means the loop is complete, paused, or intentionally dropped.",
            )
        return (
            "bounded reflection drill",
            "Write one short reflection on the current friction, then convert it into a single testable next action.",
        )

    def _read_probe_dir(self, root: Path) -> list[MentorProbe]:
        probes: list[MentorProbe] = []
        for path in sorted(root.glob("*.md")):
            raw = path.read_text(encoding="utf-8", errors="replace")
            explanation = _body_section(raw, "## Explain In Your Own Words")
            application = _body_section(raw, "## Application / Example")
            uncertainty = _body_section(raw, "## Stuck Point / Uncertainty")
            weakness = _extract_frontmatter_value(raw, "weakness") or path.stem
            probe = MentorProbe(
                probe_id=_extract_frontmatter_value(raw, "probe_id") or path.stem,
                weakness_key=_extract_frontmatter_value(raw, "weakness_key") or self._weakness_key(weakness),
                weakness=weakness,
                title=_extract_frontmatter_value(raw, "title") or path.stem.replace("-", " ").title(),
                note_name=path.name,
                status=(_extract_frontmatter_value(raw, "status") or "pending").lower(),
                gap_type=_extract_frontmatter_value(raw, "gap_type") or "unknown",
                path=str(path),
                created_at=_extract_frontmatter_value(raw, "created_at"),
                answered_at=_extract_frontmatter_value(raw, "answered_at"),
                explanation=explanation,
                application=application,
                uncertainty=uncertainty,
            )
            probe = self._classify_probe(probe)
            probes.append(probe)
        return probes

    def _read_task_dir(self, root: Path, *, status: str) -> list[MentorTask]:
        tasks: list[MentorTask] = []
        for path in sorted(root.glob("*.md")):
            raw = path.read_text(encoding="utf-8", errors="replace")
            prompt = _body_section(raw, "## Prompt")
            weakness = _extract_frontmatter_value(raw, "weakness") or path.stem
            tasks.append(
                MentorTask(
                    task_id=_extract_frontmatter_value(raw, "task_id") or path.stem,
                    weakness_key=_extract_frontmatter_value(raw, "weakness_key") or self._weakness_key(weakness),
                    weakness=weakness,
                    title=_extract_frontmatter_value(raw, "title") or path.stem.replace("-", " ").title(),
                    prompt=prompt.strip() or "Review this developmental task.",
                    completion_signal=_extract_frontmatter_value(raw, "completion_signal") or "Move this note after review.",
                    note_name=path.name,
                    gap_type=_extract_frontmatter_value(raw, "gap_type") or "unknown",
                    probe_id=_extract_frontmatter_value(raw, "probe_id"),
                    status=status,
                    path=str(path),
                    created_at=_extract_frontmatter_value(raw, "created_at"),
                    resolved_at=_extract_frontmatter_value(raw, "resolved_at"),
                )
            )
        return tasks

    def _classify_probe(self, probe: MentorProbe) -> MentorProbe:
        explanation_ok = _is_substantive_answer(probe.explanation, min_words=6, min_chars=35)
        application_ok = _is_substantive_answer(probe.application, min_words=4, min_chars=20)
        answered = any(
            _is_substantive_answer(text, min_words=2, min_chars=8)
            for text in (probe.explanation, probe.application, probe.uncertainty)
        )
        if answered:
            probe.status = "answered"
            probe.answered_at = probe.answered_at or now_iso()
            if not explanation_ok:
                probe.gap_type = "theory_gap"
            elif not application_ok:
                probe.gap_type = "application_gap"
            else:
                probe.gap_type = "resolved"
        else:
            probe.status = "pending"
            probe.gap_type = "unknown"
            probe.answered_at = None
        return probe

    def _synchronize_probe_metadata(self, probe: MentorProbe) -> MentorProbe:
        if not probe.path:
            return probe
        path = Path(probe.path)
        if not path.exists():
            return probe
        raw = path.read_text(encoding="utf-8", errors="replace")
        status = (_extract_frontmatter_value(raw, "status") or "").lower()
        gap_type = _extract_frontmatter_value(raw, "gap_type") or ""
        answered_at = _extract_frontmatter_value(raw, "answered_at") or ""
        updates: dict[str, str] = {}
        if status != probe.status:
            updates["status"] = probe.status
        if gap_type != probe.gap_type:
            updates["gap_type"] = probe.gap_type
        desired_answered_at = probe.answered_at or ""
        if answered_at != desired_answered_at:
            updates["answered_at"] = desired_answered_at
        if updates:
            path.write_text(_upsert_frontmatter(raw, updates), encoding="utf-8")
        return probe

    def _prune_resolved_pending(self, resolved_map: dict[str, MentorTask]) -> None:
        for path in self.pending_dir.glob("*.md"):
            raw = path.read_text(encoding="utf-8", errors="replace")
            task_id = _extract_frontmatter_value(raw, "task_id") or path.stem
            if task_id not in resolved_map:
                continue
            if path.parent == self.pending_dir and path.suffix.lower() == ".md":
                path.unlink(missing_ok=True)

    def _probe_has_task(self, *, probe_id: str, tasks: list[MentorTask]) -> bool:
        return any(item.probe_id == probe_id for item in tasks if probe_id)

    def _has_active_item(self, registry: dict[str, Any]) -> bool:
        latest_probe = registry.get("latest_probe") or {}
        latest_task = registry.get("latest_task") or {}
        return latest_probe.get("status") == "pending" or latest_task.get("status") == "pending"

    def _new_registry_entry(self, weakness: str, weakness_key: str) -> dict[str, Any]:
        return {
            "weakness": weakness,
            "weakness_key": weakness_key,
            "latest_gap_type": "unknown",
            "latest_probe": None,
            "latest_task": None,
            "last_resolved_at": None,
            "last_resolution_outcome": None,
        }

    def _build_weakness_registry(
        self,
        *,
        risks: list[str],
        probes: list[MentorProbe],
        pending_tasks: list[MentorTask],
        completed_tasks: list[MentorTask],
        skipped_tasks: list[MentorTask],
    ) -> dict[str, dict[str, Any]]:
        registry: dict[str, dict[str, Any]] = {}
        for weakness in risks:
            weakness_key = self._weakness_key(weakness)
            registry[weakness_key] = self._new_registry_entry(weakness, weakness_key)
        for probe in probes:
            entry = registry.setdefault(probe.weakness_key, self._new_registry_entry(probe.weakness, probe.weakness_key))
            current_probe = entry.get("latest_probe")
            if current_probe is None or _parse_ts(probe.created_at) >= _parse_ts(current_probe.get("created_at")):
                entry["latest_probe"] = probe.as_dict()
                entry["latest_gap_type"] = probe.gap_type
        for task in [*pending_tasks, *completed_tasks, *skipped_tasks]:
            entry = registry.setdefault(task.weakness_key, self._new_registry_entry(task.weakness, task.weakness_key))
            current_task = entry.get("latest_task")
            if current_task is None or _parse_ts(task.created_at) >= _parse_ts(current_task.get("created_at")):
                entry["latest_task"] = task.as_dict()
            if task.status in {"done", "skipped"}:
                task_resolved_at = task.resolved_at or task.created_at
                if _parse_ts(task_resolved_at) >= _parse_ts(entry.get("last_resolved_at")):
                    entry["last_resolved_at"] = task_resolved_at
                    entry["last_resolution_outcome"] = task.status
        return registry

    def _write_probe(self, probe: MentorProbe) -> MentorProbe:
        path = self.probes_dir / probe.note_name
        created_at = probe.created_at or now_iso()
        lines = [
            "---",
            f"probe_id: {probe.probe_id}",
            f"weakness_key: {probe.weakness_key}",
            f"weakness: {probe.weakness}",
            f"title: {probe.title}",
            "status: pending",
            f"created_at: {created_at}",
            "answered_at: ",
            "gap_type: unknown",
            "---",
            f"# Probe: {probe.title}",
            "",
            "## Why",
            probe.weakness,
            "",
            "## Explain In Your Own Words",
            "",
            "## Application / Example",
            "",
            "## Stuck Point / Uncertainty",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        probe.path = str(path)
        probe.created_at = created_at
        return probe

    def _write_pending_task(self, task: MentorTask) -> MentorTask:
        path = self.pending_dir / task.note_name
        created_at = task.created_at or now_iso()
        lines = [
            "---",
            f"task_id: {task.task_id}",
            f"weakness_key: {task.weakness_key}",
            f"weakness: {task.weakness}",
            f"title: {task.title}",
            "status: pending",
            "source: mentor",
            f"created_at: {created_at}",
            "resolved_at: ",
            f"gap_type: {task.gap_type}",
            f"probe_id: {task.probe_id or ''}",
            f"completion_signal: {task.completion_signal}",
            "---",
            f"# Training Task: {task.title}",
            "",
            "## Why",
            f"{task.weakness} (gap={task.gap_type})",
            "",
            "## Prompt",
            task.prompt,
            "",
            "## Completion",
            "- Move this note into `done/` after making a bounded attempt.",
            "- Move this note into `skipped/` if it is not the right task now.",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        task.path = str(path)
        task.created_at = created_at
        return task

    def _write_state(self, *, existing: dict[str, Any], result: MentorRunResult) -> None:
        resolved = []
        for item in [*result.completed_tasks, *result.skipped_tasks]:
            resolved.append(
                {
                    "task_id": item.task_id,
                    "title": item.title,
                    "status": item.status,
                    "resolved_at": item.resolved_at or now_iso(),
                    "path": item.path,
                    "probe_id": item.probe_id,
                    "weakness_key": item.weakness_key,
                }
            )
        write_json(
            self.state_path,
            {
                **existing,
                "ts": result.ts,
                "queue_root": result.queue_root,
                "active_probes": [item.as_dict() for item in result.active_probes],
                "pending_tasks": [item.as_dict() for item in result.pending_tasks],
                "completed_tasks": [item.as_dict() for item in result.completed_tasks],
                "skipped_tasks": [item.as_dict() for item in result.skipped_tasks],
                "resolved_tasks": resolved,
                "weakness_registry": result.weakness_registry,
                "report_path": result.report_path,
                "feedback_loop_ready": True,
            },
        )

    def _write_report(self, result: MentorRunResult) -> None:
        lines = [
            "# Mentor Daily",
            "",
            f"- generated_at: {result.ts}",
            f"- queue_root: {result.queue_root}",
            f"- active_probe_count: {len(result.active_probes)}",
            f"- pending_task_count: {len(result.pending_tasks)}",
            f"- done_count: {len(result.completed_tasks)}",
            f"- skipped_count: {len(result.skipped_tasks)}",
            "",
            "## Active Probes",
        ]
        for item in result.active_probes:
            lines.append(f"- {item.title} | probe_id={item.probe_id} | weakness={item.weakness_key} | path={item.path}")
        if not result.active_probes:
            lines.append("- (none)")
        lines.extend(["", "## Active Tasks"])
        for item in result.pending_tasks:
            lines.append(f"- {item.title} | task_id={item.task_id} | gap={item.gap_type} | path={item.path}")
        if not result.pending_tasks:
            lines.append("- (none)")
        lines.extend(["", "## Weakness Registry"])
        for weakness_key, entry in sorted(result.weakness_registry.items()):
            lines.append(
                f"- {weakness_key} | gap={entry.get('latest_gap_type', 'unknown')} | "
                f"last_resolution={entry.get('last_resolution_outcome') or 'none'} | "
                f"resolved_at={entry.get('last_resolved_at') or 'n/a'}"
            )
        if not result.weakness_registry:
            lines.append("- (none)")
        lines.extend(["", "## Recently Resolved"])
        for item in [*result.completed_tasks[:5], *result.skipped_tasks[:5]]:
            lines.append(f"- [{item.status}] {item.title} | task_id={item.task_id} | path={item.path}")
        if not result.completed_tasks and not result.skipped_tasks:
            lines.append("- (none)")
        if result.created_probe:
            lines.extend(["", "## Created Probe", f"- {result.created_probe.title} | probe_id={result.created_probe.probe_id}"])
        if result.created_task:
            lines.extend(["", "## Created Task", f"- {result.created_task.title} | task_id={result.created_task.task_id}"])
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
