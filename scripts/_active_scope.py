"""Shared active-scope exclusion predicates for Phase B and Phase C.

This is a sandbox-safe copy of the vault-side implementation.

Active scope defines which notes count as "content notes" for domain annotation
(Phase B) and scarcity architecture (Phase C). It excludes templates, meta
scaffolding, vault control docs, and third-party bundled code to keep the
working scope clean.
"""

from __future__ import annotations

from pathlib import Path

# Directory-based exclusions
EXCLUDE_DIRS = frozenset(
    {
        # System / vault internals
        ".obsidian",
        ".git",
        ".github",
        ".gitlab",
        ".trash",
        ".venv",
        "node_modules",
        "vendor",
        "dist",
        "build",
        # State and test scaffolding
        "state",
        "tests",
        # Content-adjacent scaffolding (excluded from scarcity normalization)
        "10-Inbox/Typst",
        "reports",
        "scripts",
        "config",
        "docs",
        "Otto-Realm",
        "x",
        "z Incubator",
        "Assets",
        "Clippings",
        "Collections",
        # Templates and scaffolding
        "!My/Template",
        "Action/+Inbox",
        "+Inbox",
        "00-Meta/canvas-meta",
        # Vault metadata / scaffolding
        "00-Meta",  # all MOC, hub, .base, companion files
        "Skills",  # skill reference files
        "00_Templates",  # otto / obsidian template files
    }
)

# Root-level control document stems (always excluded)
EXCLUDE_ROOT_DOCS = frozenset(
    {
        "AGENTS",
        "CLAUDE",
        "HEARTBEAT",
        "IDENTITY",
        "memory",
        "HANDOFF",
        "HANDOFF_SUMMARY_LATEST",
        "AGENT",
        "BRAT-log",
        "README",
        "SOUL",
        "TOOLS",
        "USER",
        "Vault-Architecture",
        "Canvas-Index",
        "2026-04-07T235913",
        "2026-04-09 Personal-System-in-Data",
        "Dummy Campaign",
        "normalization_plan_v1",
        "profile_v1",
    }
)

# Filename-based exclusions (scaffold / template / noise markers)
EXCLUDE_NAME_PATTERNS = frozenset(
    {
        # Obsidian template markers
        "BT_Templates",
        "Template -",
        "Template.",
        "Templates -",
        ".Template.",
        "Templater",
        # Third-party bundled code noise
        "README",
        "LICENSE",
        ".venv",
        "site-packages",
    }
)

# Specific vault-relative paths excluded from active scarcity scope.
EXCLUDE_REL_PATHS = frozenset(
    {
        "01-inbox/book_list_v2.md",
        "01-inbox/josh-plan.md",
        "30-projects/crackresearch-sme/spec/2026-04-15-crack-research-sme-design.md",
    }
)


def _normalize_parts(path: Path) -> tuple[str, ...]:
    """Get normalized path parts (forward-slash, lowercased) for exclusion matching."""

    return tuple(p.replace("\\", "/").strip().lower() for p in path.parts)


_EXCLUDE_DIRS_LC = frozenset(e.lower().rstrip("/") for e in EXCLUDE_DIRS)
_EXCLUDE_DIR_NAME_LC = frozenset(e for e in _EXCLUDE_DIRS_LC if "/" not in e)
_EXCLUDE_DIR_PREFIXES = tuple(tuple(seg for seg in e.split("/") if seg) for e in _EXCLUDE_DIRS_LC if "/" in e)


def _in_exclude_dirs(part: str) -> bool:
    part_lc = part.lower().rstrip("/")
    return part_lc in _EXCLUDE_DIR_NAME_LC


def _matches_exclude_prefix(rel_parts: tuple[str, ...]) -> bool:
    for prefix in _EXCLUDE_DIR_PREFIXES:
        n = len(prefix)
        if n == 0 or len(rel_parts) < n:
            continue
        if rel_parts[:n] == prefix:
            return True
    return False


def is_active_scope(path: Path, vault: Path | None = None) -> bool:
    """Return True if path is in active scope (i.e. counts as a content note)."""

    # Skip dot-files
    if path.stem.startswith("."):
        return False

    # Strip vault prefix to get relative path for root-level checks
    if vault is not None:
        try:
            rel = path.relative_to(vault)
        except ValueError:
            rel = path
    else:
        rel = path

    rel_norm = "/".join(_normalize_parts(rel))
    if rel_norm in EXCLUDE_REL_PATHS:
        return False
    rel_parts_norm = _normalize_parts(rel)
    if _matches_exclude_prefix(rel_parts_norm):
        return False

    # Root-level control doc: relative path has exactly 1 part (filename at vault root)
    if len(rel.parts) == 1:
        if rel.stem in EXCLUDE_ROOT_DOCS:
            return False

    # Directory exclusions (case-insensitive)
    for part in rel_parts_norm:
        if _in_exclude_dirs(part):
            return False

    # Filename pattern exclusions
    stem = path.stem
    for pat in EXCLUDE_NAME_PATTERNS:
        if pat in stem:
            return False

    return True
