from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from otto.app.system_audit import run_system_audit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Obsidian-Otto and vault runtime loop surfaces")
    parser.add_argument("--scope", choices=["repo", "vault", "both"], default="both")
    parser.add_argument("--format", choices=["text", "json", "markdown"], default="markdown")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--include-tests", action="store_true", default=False)
    parser.add_argument("--include-packages", action="store_true", default=False)
    args = parser.parse_args(argv)

    report = run_system_audit(
        root=REPO_ROOT,
        scope=args.scope,
        include_tests=args.include_tests,
        include_packages=args.include_packages,
        strict=args.strict,
    )

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        markdown_path = Path(report["outputs"]["markdown"])
        print(markdown_path.read_text(encoding="utf-8"))
    return 1 if report.get("strict_failure") else 0


if __name__ == "__main__":
    raise SystemExit(main())
