from __future__ import annotations

import argparse
import json
from typing import Any

from .app.status import build_status
from .app.tui import run_tui
from .orchestration.dream import run_dream_once
from .orchestration.kairos import run_kairos_once
from .pipeline import run_pipeline
from .retrieval.memory import retrieve


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="otto.cli", description="Obsidian-Otto control plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pipe = sub.add_parser("pipeline", help="Run Bronze -> Silver -> Gold pipeline")
    p_pipe.add_argument("--scope", default=None)
    p_pipe.add_argument("--full", action="store_true")

    p_ret = sub.add_parser("retrieve", help="Run retrieval package")
    p_ret.add_argument("--mode", choices=["fast", "deep"], default="fast")
    p_ret.add_argument("--query", required=True)

    sub.add_parser("status", help="Print status JSON")
    sub.add_parser("kairos", help="Run one KAIROS heartbeat")
    sub.add_parser("dream", help="Run one Dream consolidation")
    p_tui = sub.add_parser("tui", help="Run live TUI")
    p_tui.add_argument("--refresh-seconds", type=float, default=2.0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "pipeline":
        _print(run_pipeline(scope=args.scope, full=args.full))
        return 0
    if args.command == "retrieve":
        _print(retrieve(query=args.query, mode=args.mode))
        return 0
    if args.command == "status":
        _print(build_status())
        return 0
    if args.command == "kairos":
        _print(run_kairos_once())
        return 0
    if args.command == "dream":
        _print(run_dream_once())
        return 0
    if args.command == "tui":
        run_tui(refresh_seconds=args.refresh_seconds)
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
