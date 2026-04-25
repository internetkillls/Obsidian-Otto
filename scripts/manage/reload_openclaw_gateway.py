from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.openclaw_support import restart_openclaw_gateway  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Force-restart the local OpenClaw gateway")
    parser.add_argument("--wait-seconds", type=int, default=30)
    args = parser.parse_args(argv)

    result = restart_openclaw_gateway(wait_seconds=args.wait_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
