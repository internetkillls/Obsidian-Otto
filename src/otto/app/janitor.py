from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_support import classify_runtime, runtime_pid_file


@dataclass
class JanitorTarget:
    path: Path
    reason: str


def _otto_realm_staging_candidates(root: Path) -> list[JanitorTarget]:
    candidates: list[JanitorTarget] = []
    for relative in [
        Path("Otto-Realm") / "dump",
        Path("Otto-Realm") / "cache",
        Path("Otto-Realm") / "staging",
    ]:
        path = root / relative
        if path.exists():
            candidates.append(JanitorTarget(path=path, reason="non-canonical Otto-Realm staging area"))
    return candidates


def discover_targets(
    *,
    root: Path,
    otto_realm_staging_only: bool = False,
) -> list[JanitorTarget]:
    candidates: list[JanitorTarget] = []
    if otto_realm_staging_only:
        return _otto_realm_staging_candidates(root)

    for relative, reason in [
        (Path(".pytest_cache"), "pytest cache"),
        (Path("state") / "pids" / "runtime.pid", "stale runtime pid"),
    ]:
        path = root / relative
        if path.exists():
            candidates.append(JanitorTarget(path=path, reason=reason))

    for path in root.glob(".tmp_*"):
        candidates.append(JanitorTarget(path=path, reason="temporary workspace scratch"))

    corpus_dir = root / "memory" / ".dreams" / "session-corpus"
    if corpus_dir.exists():
        for path in corpus_dir.glob("*.txt"):
            candidates.append(JanitorTarget(path=path, reason="rebuildable dream session corpus"))

    candidates.extend(_otto_realm_staging_candidates(root))
    return candidates


def _protected(path: Path, root: Path) -> bool:
    protected_prefixes = [
        root / "state" / "run_journal",
        root / "state" / "handoff",
        root / "state" / "checkpoints",
        root / "artifacts" / "summaries",
        root / "artifacts" / "reports" / "kairos_daily_strategy.md",
        root / "artifacts" / "reports" / "dream_summary.md",
    ]
    return any(path == prefix or prefix in path.parents for prefix in protected_prefixes)


def run_janitor(
    *,
    root: Path,
    dry_run: bool = False,
    compact: bool = False,
    otto_realm_staging_only: bool = False,
) -> dict[str, Any]:
    discovered = discover_targets(root=root, otto_realm_staging_only=otto_realm_staging_only)
    runtime = classify_runtime(runtime_pid_file(root))
    deleted: list[str] = []
    skipped: list[str] = []

    for item in discovered:
        path = item.path
        if _protected(path, root):
            skipped.append(f"{path} (protected)")
            continue
        if path == runtime_pid_file(root) and runtime.status == "RUNNING":
            skipped.append(f"{path} (runtime active)")
            continue
        if dry_run:
            skipped.append(f"{path} (dry-run)")
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        deleted.append(str(path))

    compacted: list[str] = []
    if compact:
        for path in [root / "memory" / ".dreams" / "session-corpus"]:
            if path.exists() and path.is_dir():
                empty_dirs = [p for p in path.iterdir() if p.is_dir() and not any(p.iterdir())]
                for empty_dir in empty_dirs:
                    if not dry_run:
                        empty_dir.rmdir()
                    compacted.append(str(empty_dir))

    return {
        "dry_run": dry_run,
        "compact": compact,
        "otto_realm_staging_only": otto_realm_staging_only,
        "discovered": [{"path": str(item.path), "reason": item.reason} for item in discovered],
        "deleted": deleted,
        "skipped": skipped,
        "compacted": compacted,
    }
