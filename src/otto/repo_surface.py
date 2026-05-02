from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SurfaceRecord:
    path: str
    kind: str
    status: str


CANONICAL_PREFIXES = (
    "src/otto/",
    "scripts/manage/",
    "otto.bat",
)

COMPAT_PREFIXES = (
    "src/app/",
    "src/orchestration/",
    "src/retrieval/",
    "src/tooling/",
)

GOVERNANCE_PREFIXES = (
    ".Otto-Realm/",
    "Otto-Realm/",
)


def classify_repo_surface(path: str) -> SurfaceRecord:
    normalized = path.replace("\\", "/")
    if normalized.startswith(CANONICAL_PREFIXES):
        return SurfaceRecord(path=path, kind="control-plane", status="canonical")
    if normalized.startswith(COMPAT_PREFIXES):
        return SurfaceRecord(path=path, kind="compatibility-shim", status="compatibility")
    if normalized.startswith(GOVERNANCE_PREFIXES):
        return SurfaceRecord(path=path, kind="governance-backed-runtime", status="governance")
    if normalized.endswith((".bat", ".ps1", ".sh")):
        return SurfaceRecord(path=path, kind="operator-entrypoint", status="entrypoint")
    return SurfaceRecord(path=path, kind="other", status="unclassified")


def surface_registry(paths: Iterable[str]) -> list[dict[str, str]]:
    return [classify_repo_surface(path).__dict__ for path in paths]
