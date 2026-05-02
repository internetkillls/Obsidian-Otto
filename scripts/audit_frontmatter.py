from __future__ import annotations

import argparse
import json
from pathlib import Path

from _active_scope import is_active_scope
from _scarcity_common import now_iso, read_note_metadata, resolve_vault_path, write_json


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit scarcity frontmatter readiness (sandbox-safe)")
    parser.add_argument("--vault", default="")
    parser.add_argument("--check-scarcity-field", action="store_true")
    parser.add_argument(
        "--scope",
        default="active",
        choices=["full", "active"],
        help="'active' uses shared scope filter (B2/Phase C aligned). "
        "'full' walks all notes except system dirs. Default: active",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    vault = Path(args.vault).expanduser().resolve() if args.vault else resolve_vault_path(repo_root)
    missing: list[str] = []
    note_count = 0

    if not vault.exists() or not vault.is_dir():
        raise SystemExit(f"Vault path is not a directory: {vault}")

    if args.scope == "active":
        for note_path in vault.rglob("*.md"):
            if is_active_scope(note_path, vault):
                note_count += 1
                metadata = read_note_metadata(note_path, vault)
                if not metadata["has_frontmatter_scarcity"]:
                    missing.append(metadata["note_path"])
    else:
        for note_path in vault.rglob("*.md"):
            if not any(part in {"state", "tests", ".obsidian", ".git", ".trash", ".venv"} for part in note_path.parts):
                note_count += 1
                metadata = read_note_metadata(note_path, vault)
                if not metadata["has_frontmatter_scarcity"]:
                    missing.append(metadata["note_path"])

    report = {
        "ts": now_iso(),
        "vault": str(vault),
        "note_count": note_count,
        "scope": args.scope,
        "scarcity_field_notes": note_count - len(missing),
        "missing_scarcity_field_count": len(missing),
        "missing_scarcity_field_examples": missing[:50],
        "ok": len(missing) == 0,
    }

    out_path = repo_root / "state" / "scarcity_preflight.json"
    write_json(out_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.check_scarcity_field and missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

