from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.app.status import build_status, render_status_summary  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Status report")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)

    status = build_status()
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    print(render_status_summary(status), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
