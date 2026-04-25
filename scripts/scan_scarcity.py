from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _active_scope import is_active_scope
from _scarcity_common import now_iso, read_note_metadata, resolve_vault_path, write_json


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan scarcity metadata across the vault (sandbox-safe)")
    parser.add_argument("--vault", default="")
    parser.add_argument("--output", default="state/scarcity_index.json")
    parser.add_argument(
        "--scope",
        default="active",
        choices=["full", "active"],
        help="'active' uses shared scope filter (B2/Phase C aligned). Default: active",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    vault = Path(args.vault).expanduser().resolve() if args.vault else resolve_vault_path(repo_root)
    if not vault.exists() or not vault.is_dir():
        raise SystemExit(f"Vault path is not a directory: {vault}")

    output_path = (repo_root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    records: list[dict[str, object]] = []
    orphans: list[dict[str, object]] = []

    if args.scope == "active":
        notes_iter = (p for p in vault.rglob("*.md") if is_active_scope(p, vault))
    else:
        notes_iter = (
            p
            for p in vault.rglob("*.md")
            if not any(part in {"state", "tests", ".obsidian", ".git", ".trash", ".venv"} for part in p.parts)
        )

    for note_path in notes_iter:
        metadata = read_note_metadata(note_path, vault)
        record = {
            "note_path": metadata["note_path"],
            "scarcity": metadata["scarcity"],
            "necessity": metadata["necessity"],
            "artificial": metadata["artificial"],
            "orientation": metadata["orientation"],
            "allocation": metadata["allocation"],
            "cluster_membership": metadata["cluster_membership"],
        }
        records.append(record)
        if not metadata["has_frontmatter_scarcity"]:
            orphans.append(
                {
                    "note_path": metadata["note_path"],
                    "fallback_scarcity": metadata["scarcity"],
                    "orientation": metadata["orientation"],
                    "allocation": metadata["allocation"],
                }
            )

    payload = {
        "ts": now_iso(),
        "vault": str(vault),
        "note_count": len(records),
        "scope": args.scope,
        "orphan_count": len(orphans),
        "records": records,
    }

    write_json(output_path, payload)
    write_json(repo_root / "state" / "orphan_log.json", {"ts": now_iso(), "orphans": orphans})
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    summary = {
        "ts": payload["ts"],
        "vault": payload["vault"],
        "note_count": payload["note_count"],
        "scope": payload["scope"],
        "orphan_count": payload["orphan_count"],
        "output": str(output_path),
        "orphans_example": [o["note_path"] for o in orphans[:10]],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
