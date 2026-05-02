from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.app.status import build_status  # noqa: E402
from otto.pipeline import run_pipeline  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Otto pipeline")
    parser.add_argument("--scope", default=None)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(build_status(), ensure_ascii=False, indent=2))
        return 0

    result = run_pipeline(scope=args.scope, full=args.full)
    print(json.dumps(result["checkpoint"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
