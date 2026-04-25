from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.app.launcher import render_action_catalog, render_action_description, run_launcher  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Otto launcher")
    parser.add_argument("--screen", choices=["home", "advanced"], default="home")
    parser.add_argument("--once", default=None)
    parser.add_argument("--list-actions", action="store_true")
    parser.add_argument("--describe", default=None)
    args, extra_args = parser.parse_known_args(argv)
    if args.list_actions:
        print(render_action_catalog(None if args.screen == "home" else args.screen), end="")
        return 0
    if args.describe:
        exit_code, text = render_action_description(args.describe)
        print(text, end="")
        return exit_code
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]
    if args.once and extra_args and extra_args[0].strip().lower().replace("_", "-") == args.once.strip().lower().replace("_", "-"):
        extra_args = extra_args[1:]
    return run_launcher(screen=args.screen, once=args.once, extra_args=extra_args)


if __name__ == "__main__":
    raise SystemExit(main())
