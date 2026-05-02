from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import load_paths, repo_root
from ..path_compat import is_wsl


DEFAULT_REPO_ROOT_WINDOWS = "C:/Users/joshu/Obsidian-Otto"
DEFAULT_REPO_ROOT_WSL = "/mnt/c/Users/joshu/Obsidian-Otto"
DEFAULT_VAULT_ROOT_WINDOWS = "C:/Users/joshu/Josh Obsidian"
DEFAULT_VAULT_ROOT_WSL = "/mnt/c/Users/joshu/Josh Obsidian"
DEFAULT_LEGACY_WRONG_ROOT_WSL = "/mnt/c/Users/joshu/Obsidian-Otto/Otto-Realm"


CONTROL_PLANE_RELATIVE_PATHS = [
    "state/handoff/latest.json",
    "state/checkpoints/pipeline.json",
    "artifacts/summaries/gold_summary.json",
    "artifacts/reports/kairos_daily_strategy.md",
    "artifacts/reports/dream_summary.md",
    "artifacts/reports/otto_profile.md",
    "state/run_journal/events.jsonl",
    "logs/kairos_profile.log",
]

ROOT_CONTROL_DOCS = [
    "CLAUDE.md",
    "HEARTBEAT.md",
    "IDENTITY.md",
    "SOUL.md",
    "TOOLS.md",
    "AGENTS.md",
]

VAULT_IDENTITY_RELATIVE_PATHS = [
    ".Otto-Realm/Profile Snapshot.md",
    ".Otto-Realm/Central Schedule.md",
    ".Otto-Realm/Brain",
    ".Otto-Realm/Heartbeats",
    ".Otto-Realm/Memory-Tiers",
    ".Otto-Realm/Rituals",
    ".Otto-Realm/Predictions",
]


@dataclass(frozen=True)
class SoulRoots:
    repo_root_windows: str
    repo_root_wsl: str
    vault_root_windows: str
    vault_root_wsl: str
    soul_root_windows: str
    soul_root_wsl: str
    legacy_wrong_root_wsl: str


def infer_soul_roots() -> SoulRoots:
    paths = load_paths()
    actual_repo = str(repo_root()).replace("\\", "/")
    actual_vault = str(paths.vault_path).replace("\\", "/") if paths.vault_path else DEFAULT_VAULT_ROOT_WINDOWS
    vault_windows = DEFAULT_VAULT_ROOT_WINDOWS if DEFAULT_VAULT_ROOT_WINDOWS else actual_vault
    vault_wsl = DEFAULT_VAULT_ROOT_WSL
    return SoulRoots(
        repo_root_windows=DEFAULT_REPO_ROOT_WINDOWS if DEFAULT_REPO_ROOT_WINDOWS else actual_repo,
        repo_root_wsl=DEFAULT_REPO_ROOT_WSL,
        vault_root_windows=vault_windows,
        vault_root_wsl=vault_wsl,
        soul_root_windows=f"{vault_windows.rstrip('/')}/.Otto-Realm",
        soul_root_wsl=f"{vault_wsl.rstrip('/')}/.Otto-Realm",
        legacy_wrong_root_wsl=DEFAULT_LEGACY_WRONG_ROOT_WSL,
    )


def to_host_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/")
    if is_wsl():
        return Path(normalized).expanduser()
    if len(normalized) > 7 and normalized.startswith("/mnt/") and normalized[6] == "/":
        drive = normalized[5].upper()
        tail = normalized[7:]
        return Path(f"{drive}:/{tail}")
    return Path(normalized).expanduser()


def _entry(base: str, rel: str, *, required: bool = False) -> dict[str, Any]:
    raw = f"{base.rstrip('/')}/{rel.lstrip('/')}"
    host = to_host_path(raw)
    return {
        "relative_path": rel,
        "path_wsl": raw,
        "host_path": str(host),
        "exists": host.exists(),
        "is_dir": host.is_dir(),
        "required": required,
    }


def control_plane_entries(repo_root_wsl: str) -> list[dict[str, Any]]:
    return [_entry(repo_root_wsl, rel) for rel in CONTROL_PLANE_RELATIVE_PATHS]


def root_control_doc_entries(repo_root_wsl: str) -> list[dict[str, Any]]:
    return [_entry(repo_root_wsl, rel) for rel in ROOT_CONTROL_DOCS]


def vault_identity_entries(vault_root_wsl: str) -> list[dict[str, Any]]:
    required = {".Otto-Realm/Profile Snapshot.md", ".Otto-Realm/Heartbeats"}
    return [_entry(vault_root_wsl, rel, required=rel in required) for rel in VAULT_IDENTITY_RELATIVE_PATHS]


def _sample_wrong_root_candidates(path: Path, *, limit: int = 20) -> list[str]:
    if not path.exists() or not path.is_dir():
        return []
    candidates: list[str] = []
    for child in sorted(path.rglob("*")):
        rel = child.relative_to(path).as_posix()
        if rel:
            candidates.append(rel)
        if len(candidates) >= limit:
            break
    return candidates


def build_root_audit(roots: SoulRoots | None = None, *, sample_limit: int = 20) -> dict[str, Any]:
    roots = roots or infer_soul_roots()
    vault_root_windows = str(getattr(roots, "vault_root_windows", DEFAULT_VAULT_ROOT_WINDOWS))
    vault_root_wsl = str(getattr(roots, "vault_root_wsl", DEFAULT_VAULT_ROOT_WSL))
    soul_root_windows = str(getattr(roots, "soul_root_windows", f"{vault_root_windows.rstrip('/')}/.Otto-Realm"))
    soul_root_wsl = str(getattr(roots, "soul_root_wsl", f"{vault_root_wsl.rstrip('/')}/.Otto-Realm"))
    legacy_wrong_root_wsl = str(getattr(roots, "legacy_wrong_root_wsl", DEFAULT_LEGACY_WRONG_ROOT_WSL))

    canonical_path = to_host_path(soul_root_wsl)
    legacy_path = to_host_path(legacy_wrong_root_wsl)
    legacy_candidates = _sample_wrong_root_candidates(legacy_path, limit=sample_limit)
    return {
        "canonical_soul_root": {
            "path_windows": soul_root_windows,
            "path_wsl": soul_root_wsl,
            "host_path": str(canonical_path),
            "exists": canonical_path.exists(),
            "is_dir": canonical_path.is_dir(),
        },
        "legacy_wrong_root": {
            "path_wsl": legacy_wrong_root_wsl,
            "host_path": str(legacy_path),
            "exists": legacy_path.exists(),
            "is_dir": legacy_path.is_dir(),
        },
        "legacy_wrong_root_exists": legacy_path.exists(),
        "wrong_root_candidates": legacy_candidates,
        "wrong_root_candidates_count": len(legacy_candidates),
        "warning": "legacy_wrong_root_detected" if legacy_path.exists() else None,
        "non_destructive": True,
    }
