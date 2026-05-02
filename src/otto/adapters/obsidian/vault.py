from __future__ import annotations

from pathlib import Path
from typing import Any

from ...config import load_paths


DEFAULT_ALLOWED_REALM_DIRS = [
    "Brain",
    "Memory-Tiers",
    "Predictions",
    "Handoff",
    "Rituals",
    "Creative",
    "Research",
    "Skills",
    "Memento",
]


def vault_root() -> Path:
    paths = load_paths()
    if paths.vault_path:
        return paths.vault_path
    return Path("C:/Users/joshu/Josh Obsidian")


def otto_realm_root(root: Path | None = None) -> Path:
    return (root or vault_root()) / ".Otto-Realm"


def allowed_base_paths(root: Path | None = None) -> list[Path]:
    realm = otto_realm_root(root).resolve()
    return [(realm / name).resolve() for name in DEFAULT_ALLOWED_REALM_DIRS]


def is_allowed_otto_realm_target(target_path: str | Path, *, root: Path | None = None) -> bool:
    target = Path(target_path).expanduser().resolve()
    for base in allowed_base_paths(root):
        try:
            target.relative_to(base)
            return True
        except ValueError:
            continue
    return False


def classify_target(target_path: str | Path, *, root: Path | None = None) -> dict[str, Any]:
    target = Path(target_path).expanduser().resolve()
    allowed = is_allowed_otto_realm_target(target, root=root)
    return {
        "ok": allowed,
        "target_path": str(target),
        "allowed_base_paths": [str(path) for path in allowed_base_paths(root)],
        "reason": "allowed-otto-realm-target" if allowed else "target-outside-allowed-otto-realm-paths",
    }


def default_target_path(kind: str, *, root: Path | None = None) -> Path:
    realm = otto_realm_root(root)
    if kind in {"handoff", "handoff_note"}:
        from datetime import date

        return realm / "Handoff" / f"{date.today().isoformat()}.md"
    if kind in {"runtime_checkpoint", "context_pack_summary"}:
        return realm / "Brain" / "Runtime Checkpoints.md"
    if kind in {"reviewed_memory", "gold_memory", "gold_profile"}:
        return realm / "Memory-Tiers" / "01-Facts" / "Gold Memory.md"
    return realm / "Brain" / f"{kind}.md"
