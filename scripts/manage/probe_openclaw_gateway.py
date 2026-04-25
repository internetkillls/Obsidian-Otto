from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.openclaw_support import probe_openclaw_gateway  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe the local OpenClaw gateway over HTTP")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    args = parser.parse_args(argv)

    result = probe_openclaw_gateway(timeout_seconds=args.timeout_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
