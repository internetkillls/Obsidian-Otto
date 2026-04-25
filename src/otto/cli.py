from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .app.status import build_status
from .app.kairos_tui import run_kairos_tui
from .orchestration.kairos_chat import KAIROSChatHandler
from .openclaw_support import (
    build_openclaw_health,
    decide_openclaw_fallback,
    probe_openclaw_gateway,
    reload_openclaw_plugin_surface,
    restart_openclaw_gateway,
    sync_openclaw_config,
)
from .app.tui import run_tui
from .orchestration.dream import run_dream_once
from .orchestration.kairos import run_kairos_once
from .orchestration.morpheus_openclaw_bridge import load_morpheus_openclaw_bridge
from .pipeline import run_pipeline
from .retrieval.evaluate import evaluate_retrieval
from .retrieval.memory import retrieve


def _print(data: Any) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="otto.cli", description="Obsidian-Otto control plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pipe = sub.add_parser("pipeline", help="Run Bronze -> Silver -> Gold pipeline")
    p_pipe.add_argument("--scope", default=None)
    p_pipe.add_argument("--full", action="store_true")

    p_ret = sub.add_parser("retrieve", help="Run retrieval package")
    p_ret.add_argument("--mode", choices=["fast", "deep"], default="fast")
    p_ret.add_argument("--query", required=True)
    sub.add_parser("retrieve-eval", help="Evaluate retrieval against the annotated fixture")

    sub.add_parser("status", help="Print status JSON")
    sub.add_parser("openclaw-health", help="Print OpenClaw boundary health JSON")
    sub.add_parser("openclaw-gateway-probe", help="Probe the local OpenClaw gateway over HTTP without using the OpenClaw CLI")
    sub.add_parser("openclaw-sync", help="Report OpenClaw boundary status without mutating live config")
    p_oc_restart = sub.add_parser("openclaw-gateway-restart", help="Force-restart the local OpenClaw gateway without using the OpenClaw CLI")
    p_oc_restart.add_argument("--wait-seconds", type=int, default=30)
    p_oc_reload = sub.add_parser("openclaw-plugin-reload", help="Force a plugin-surface reload by touching live config; optionally hard-restart the gateway")
    p_oc_reload.add_argument("--wait-seconds", type=int, default=30)
    p_oc_reload.add_argument("--hard-restart", action="store_true")
    p_oc_fb = sub.add_parser("openclaw-fallback", help="Simulate OpenClaw fallback handling for provider errors")
    p_oc_fb.add_argument("--status-code", type=int, required=True)
    p_oc_fb.add_argument("--attempted-backend", default="claude-cli")
    p_oc_fb.add_argument("--attempted-model", default="claude-cli/claude-sonnet-4-6")
    sub.add_parser("kairos", help="Run one KAIROS heartbeat")
    sub.add_parser("dream", help="Run one Dream consolidation")
    p_bridge = sub.add_parser("morpheus-bridge", help="Show the latest Morpheus -> OpenClaw memory-candidate bridge payload")
    p_bridge.add_argument("--refresh", action="store_true")
    p_tui = sub.add_parser("tui", help="Run live TUI")
    p_tui.add_argument("--refresh-seconds", type=float, default=2.0)
    sub.add_parser("kairos-tui", help="Run KAIROS deep-dive TUI (dig/train commands)")
    p_chat = sub.add_parser("kairos-chat", help="KAIROS chat: pass a natural language command")
    p_chat.add_argument("message", nargs="*", help="Natural language command to KAIROS")

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
    if args.command == "retrieve-eval":
        _print(evaluate_retrieval())
        return 0
    if args.command == "status":
        _print(build_status())
        return 0
    if args.command == "openclaw-health":
        _print(build_openclaw_health())
        return 0
    if args.command == "openclaw-gateway-probe":
        result = probe_openclaw_gateway()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "openclaw-sync":
        _print(sync_openclaw_config())
        return 0
    if args.command == "openclaw-gateway-restart":
        result = restart_openclaw_gateway(wait_seconds=args.wait_seconds)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "openclaw-plugin-reload":
        result = reload_openclaw_plugin_surface(wait_seconds=args.wait_seconds, hard_restart=args.hard_restart)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "openclaw-fallback":
        _print(
            decide_openclaw_fallback(
                args.status_code,
                attempted_backend=args.attempted_backend,
                attempted_model=args.attempted_model,
            )
        )
        return 0
    if args.command == "kairos":
        _print(run_kairos_once())
        return 0
    if args.command == "dream":
        _print(run_dream_once())
        return 0
    if args.command == "morpheus-bridge":
        result = load_morpheus_openclaw_bridge(refresh=args.refresh)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "tui":
        run_tui(refresh_seconds=args.refresh_seconds)
        return 0
    if args.command == "kairos-tui":
        run_kairos_tui()
        return 0
    if args.command == "kairos-chat":
        handler = KAIROSChatHandler()
        message = " ".join(args.message) if args.message else ""
        if not message:
            print("Usage: otto cli kairos-chat \"dig Projects\"")
            return 1
        result = handler.handle(message)
        if args.message and len(args.message) == 1 and args.message[0] == "--help":
            _print(handler._help())
            return 0
        _print(result)
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
