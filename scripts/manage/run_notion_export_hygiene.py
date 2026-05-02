from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.orchestration.notion_export_hygiene import run_notion_export_hygiene  # noqa: E402
from otto.state import json_default  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Notion export hygiene")
    parser.add_argument("--mode", choices=["review", "apply", "verify"], default="review")
    parser.add_argument("--scope", default="active")
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--no-rewrite-links", action="store_true")
    parser.add_argument("--reindex-after", action="store_true")
    args = parser.parse_args(argv)

    result = run_notion_export_hygiene(
        mode=args.mode,
        scope=args.scope,
        notes=args.note,
        confirm=args.confirm,
        rewrite_links=not args.no_rewrite_links,
        reindex_after=args.reindex_after,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=json_default))
    return 0 if result.get("status") in {"ok", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
