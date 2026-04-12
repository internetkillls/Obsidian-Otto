from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..logging_utils import get_logger
from ..state import write_json

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
TAG_RE = re.compile(r"(?<!\w)#([A-Za-z0-9_\-/]+)")


@dataclass
class NoteRecord:
    path: str
    title: str
    size: int
    sha1: str
    mtime: float
    has_frontmatter: bool
    frontmatter_text: str
    tags: list[str]
    wikilinks: list[str]
    extension: str
    body_excerpt: str


def _title_from_path(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").strip() or path.name


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def scan_vault(scope: str | None = None) -> dict[str, Any]:
    logger = get_logger("otto.scan")
    paths = load_paths()
    if paths.vault_path is None:
        raise RuntimeError("Vault path not configured. Run initial.bat first.")
    if not paths.vault_path.is_dir():
        raise RuntimeError(f"Vault path is not a directory: {paths.vault_path}")

    base = paths.vault_path
    target = (base / scope).resolve() if scope else base
    if not target.exists():
        raise FileNotFoundError(f"Scope does not exist: {target}")

    notes: list[NoteRecord] = []
    attachments: list[dict[str, Any]] = []

    for path in target.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(base))
        stat = path.stat()
        if path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8", errors="replace")
            fm = FRONTMATTER_RE.match(text)
            body = text[fm.end():] if fm else text
            tags = sorted(set(TAG_RE.findall(body)))
            links = sorted(set(WIKILINK_RE.findall(text)))
            notes.append(
                NoteRecord(
                    path=rel,
                    title=_title_from_path(path),
                    size=stat.st_size,
                    sha1=_sha1(path),
                    mtime=stat.st_mtime,
                    has_frontmatter=bool(fm),
                    frontmatter_text=fm.group(1).strip() if fm else "",
                    tags=tags,
                    wikilinks=links,
                    extension=path.suffix.lower(),
                    body_excerpt=body[:2000],
                )
            )
        else:
            attachments.append(
                {
                    "path": rel,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "extension": path.suffix.lower(),
                }
            )

    notes.sort(key=lambda n: n.path)
    attachments.sort(key=lambda a: a["path"])

    if not notes and not attachments:
        logger.warning(f"[scan] empty vault — no notes or attachments found at scope={scope or '.'}")
        raise RuntimeError(f"Vault scan produced no notes. Check vault path configuration. Scope: {target}")

    payload = {
        "vault": str(base),
        "scope": str(scope or "."),
        "note_count": len(notes),
        "attachment_count": len(attachments),
        "notes": [asdict(n) for n in notes],
        "attachments": attachments,
    }
    write_json(paths.bronze_root / "bronze_manifest.json", payload)
    write_json(paths.artifacts_root / "reports" / "bronze_summary.json", {
        "scope": payload["scope"],
        "note_count": payload["note_count"],
        "attachment_count": payload["attachment_count"],
    })
    logger.info(f"[scan] notes={len(notes)} attachments={len(attachments)} scope={scope or '.'}")
    return payload
