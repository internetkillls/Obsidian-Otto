from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.orchestration.metadata_enrichment import run_metadata_enrichment  # noqa: E402
from otto.state import json_default  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Otto metadata enrichment")
    parser.add_argument("--mode", choices=["review", "apply", "entity", "verify"], default="review")
    parser.add_argument("--scope", default="active")
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--backend", default="auto")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--no-verify-after", action="store_true")
    parser.add_argument("--dispatch-command", action="store_true")
    args = parser.parse_args(argv)

    result = run_metadata_enrichment(
        mode=args.mode,
        scope=args.scope,
        notes=args.note,
        backend=args.backend,
        confirm=args.confirm,
        verify_after=not args.no_verify_after,
        dispatch_command=args.dispatch_command,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=json_default))
    return 0 if result.get("status") in {"ok", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
