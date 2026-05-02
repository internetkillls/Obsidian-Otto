from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.orchestration.graph_demotion import run_graph_demotion_followup  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the reviewed ALLO-only graph-demotion follow-up")
    parser.add_argument("--max-demotion-writes", type=int, default=6)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = parser.parse_args(argv)

    result = run_graph_demotion_followup(
        max_demotion_writes=args.max_demotion_writes,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "applied" else 1


if __name__ == "__main__":
    raise SystemExit(main())
