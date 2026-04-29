from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .app.status import build_status
from .app.kairos_tui import run_kairos_tui
from .docker_utils import docker_probe_diagnostics
from .adapters.openclaw.context_pack import write_openclaw_context_pack
from .adapters.openclaw.tool_payloads import write_openclaw_tool_manifest
from .adapters.qmd.manifest import build_qmd_manifest, write_qmd_manifest
from .adapters.qmd.retrieval import qmd_search
from .memory.source_registry import validate_source_registry, write_default_source_registry
from .orchestration.cron_control import build_cron_status, clear_essay_control, steer_essay_control
from .orchestration.runtime_owner import write_runtime_owner, write_single_owner_lock
from .orchestration.runtime_smoke import build_runtime_smoke
from .orchestration.wsl_live_migration import (
    build_wsl_live_preflight,
    build_wsl_live_status,
    promote_wsl_live,
    rollback_wsl_live,
)
from .orchestration.kairos_chat import KAIROSChatHandler
from .openclaw_shadow import write_ubuntu_shadow_config
from .openclaw_support import (
    build_openclaw_health,
    build_qmd_index_health,
    decide_openclaw_fallback,
    probe_openclaw_gateway,
    reload_openclaw_plugin_surface,
    restart_openclaw_gateway,
    run_qmd_index_refresh,
    sync_openclaw_config,
)
from .operator_control import (
    fallback_to_native,
    operator_doctor,
    operator_status,
    operator_update,
    restart_wsl_gateway,
    start_wsl_gateway,
    stop_wsl_gateway,
)
from .app.tui import run_tui
from .orchestration.dream import run_dream_once
from .orchestration.kairos import run_kairos_once
from .orchestration.morpheus_openclaw_bridge import load_morpheus_openclaw_bridge
from .orchestration.qmd_fanout import run_qmd_seed_fanout
from .pipeline import run_pipeline
from .retrieval.evaluate import evaluate_retrieval
from .retrieval.memory import retrieve
from .wsl_support import build_wsl_health


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
    p_source_registry = sub.add_parser("source-registry", help="Validate the canonical Otto source registry")
    p_source_registry.add_argument("--write-default", action="store_true", help="Write the default registry if it does not exist")
    p_qmd_manifest = sub.add_parser("qmd-manifest", help="Generate the Otto-managed QMD source manifest from the source registry")
    p_qmd_manifest.add_argument("--write", action="store_true", help="Write state/qmd/qmd_manifest.json")
    p_qmd_manifest.add_argument("--runtime", default="wsl_shadow")
    p_qmd_manifest.add_argument("--qmd-command", default="/usr/bin/qmd")
    sub.add_parser("wsl-health", help="Print WSL-first QMD/Docker/Python health JSON")
    sub.add_parser("docker-probe", help="Probe Docker CLI, daemon, and visible containers")
    sub.add_parser("cron-status", help="Print cron steering and job status JSON")
    p_cron_steer = sub.add_parser("cron-steer", help="Steer essay cron focus")
    p_cron_steer.add_argument("--mode", choices=["normal", "paper_topics", "paper_now"], default="paper_topics")
    p_cron_steer.add_argument("--topic", default="")
    p_cron_steer.add_argument("--days", type=int, default=2)
    p_cron_steer.add_argument("--reason", default="")
    p_cron_steer.add_argument("--source", default="cli")
    p_cron_steer.add_argument("--clear", action="store_true")
    sub.add_parser("openclaw-health", help="Print OpenClaw boundary health JSON")
    sub.add_parser("qmd-index-health", help="Print QMD index health JSON")
    p_qmd_refresh = sub.add_parser("qmd-reindex", help="Force a QMD memory reindex")
    p_qmd_refresh.add_argument("--timeout-seconds", type=int, default=60)
    p_qmd_search = sub.add_parser("qmd-search", help="Search QMD/OpenClaw memory and normalize results into Otto evidence hits")
    p_qmd_search.add_argument("query", nargs="+")
    p_qmd_search.add_argument("-n", "--max-results", type=int, default=5)
    p_qmd_search.add_argument("--timeout-seconds", type=int, default=60)
    p_qmd_fanout = sub.add_parser("qmd-fanout", help="Fan out one seed into 50 ranked paper outlines")
    p_qmd_fanout.add_argument("--seed", required=True)
    p_qmd_fanout.add_argument("--count", type=int, default=50)
    p_qmd_fanout.add_argument("--journal-first", action=argparse.BooleanOptionalAction, default=True)
    p_qmd_fanout.add_argument("--force-now", action="store_true")
    p_oc_probe = sub.add_parser("openclaw-gateway-probe", help="Probe the local OpenClaw gateway over HTTP without using the OpenClaw CLI")
    p_oc_probe.add_argument("--port", type=int, default=None)
    p_oc_probe.add_argument("--host", default="127.0.0.1")
    p_oc_probe.add_argument("--runtime", default="windows-live")
    p_oc_probe.add_argument("--timeout-seconds", type=float, default=5.0)
    p_oc_context = sub.add_parser("openclaw-context-pack", help="Write and print the Otto context pack for OpenClaw")
    p_oc_context.add_argument("--task", default=None)
    sub.add_parser("openclaw-tool-manifest", help="Write and print the Otto read-only tool manifest for OpenClaw")
    sub.add_parser("runtime-owner", help="Write and print runtime owner state")
    sub.add_parser("single-owner-lock", help="Write and print gateway/Telegram single-owner lock")
    p_runtime_smoke = sub.add_parser("runtime-smoke", help="Run WSL shadow runtime smoke gates")
    p_runtime_smoke.add_argument("--gateway-port", type=int, default=18790)
    p_runtime_smoke.add_argument("--strict", action="store_true")
    p_wsl_live_preflight = sub.add_parser("wsl-live-preflight", help="Verify the Ubuntu OpenClaw/QMD corridor is ready for WSL live promote")
    p_wsl_live_preflight.add_argument("--gateway-port", type=int, default=18790)
    p_wsl_live_promote = sub.add_parser("wsl-live-promote", help="Promote Ubuntu OpenClaw from shadow to live owner")
    p_wsl_live_promote.add_argument("--gateway-port", type=int, default=18790)
    p_wsl_live_promote.add_argument("--dry-run", action="store_true")
    p_wsl_live_promote.add_argument("--write", action="store_true")
    p_wsl_live_rollback = sub.add_parser("wsl-live-rollback", help="Rollback WSL live ownership back to Windows")
    p_wsl_live_rollback.add_argument("--gateway-port", type=int, default=18790)
    p_wsl_live_rollback.add_argument("--write", action="store_true")
    p_wsl_live_status = sub.add_parser("wsl-live-status", help="Summarize current WSL live owner and gateway status")
    p_wsl_live_status.add_argument("--gateway-port", type=int, default=18790)
    sub.add_parser("openclaw-sync", help="Report OpenClaw boundary status without mutating live config")
    sub.add_parser("operator-status", help="Check native/WSL OpenClaw, QMD, cron, and heartbeat parity")
    sub.add_parser("operator-doctor", help="Repair/sync operator config and report native/WSL parity")
    sub.add_parser("operator-update", help="Regenerate OpenClaw/QMD payloads and resync operator state")
    p_wsl_start = sub.add_parser("wsl-gateway-start", help="Start the WSL OpenClaw shadow gateway")
    p_wsl_start.add_argument("--port", type=int, default=18790)
    p_wsl_start.add_argument("--wait-seconds", type=int, default=60)
    p_wsl_stop = sub.add_parser("wsl-gateway-stop", help="Stop the WSL OpenClaw shadow gateway")
    p_wsl_stop.add_argument("--port", type=int, default=18790)
    p_wsl_restart = sub.add_parser("wsl-gateway-restart", help="Restart the WSL OpenClaw shadow gateway")
    p_wsl_restart.add_argument("--port", type=int, default=18790)
    sub.add_parser("native-fallback", help="Switch back to native OpenClaw gateway if WSL shadow fails")
    p_oc_restart = sub.add_parser("openclaw-gateway-restart", help="Force-restart the local OpenClaw gateway without using the OpenClaw CLI")
    p_oc_restart.add_argument("--wait-seconds", type=int, default=30)
    p_oc_reload = sub.add_parser("openclaw-plugin-reload", help="Force a plugin-surface reload by touching live config; optionally hard-restart the gateway")
    p_oc_reload.add_argument("--wait-seconds", type=int, default=30)
    p_oc_reload.add_argument("--hard-restart", action="store_true")
    p_oc_fb = sub.add_parser("openclaw-fallback", help="Simulate OpenClaw fallback handling for provider errors")
    p_oc_fb.add_argument("--status-code", type=int, required=True)
    p_oc_fb.add_argument("--attempted-backend", default="claude-cli")
    p_oc_fb.add_argument("--attempted-model", default="claude-cli/claude-sonnet-4-6")
    p_oc_shadow = sub.add_parser("openclaw-shadow-config", help="Write a WSL Ubuntu shadow OpenClaw config without cutting over live Windows")
    p_oc_shadow.add_argument("--port", type=int, default=18790)
    p_oc_shadow.add_argument("--output", default=None)
    p_oc_shadow.add_argument("--install-path", default=None)
    p_oc_shadow.add_argument("--write", action="store_true", help="Also write the generated config to ~/.openclaw/openclaw.json in the current environment")
    sub.add_parser("kairos", help="Run one KAIROS heartbeat")
    sub.add_parser("dream", help="Run one Dream consolidation")
    p_bridge = sub.add_parser("morpheus-bridge", help="Show the latest Morpheus -> OpenClaw memory-candidate bridge payload")
    p_bridge.add_argument("--refresh", action="store_true")
    p_tui = sub.add_parser("tui", help="Run live TUI")
    p_tui.add_argument("--refresh-seconds", type=float, default=2.0)
    sub.add_parser("kairos-tui", help="Run KAIROS deep-dive TUI (dig/train commands)")
    p_chat = sub.add_parser("kairos-chat", help="KAIROS chat: pass a natural language command")
    p_chat.add_argument("message", nargs="*", help="Natural language command to KAIROS")
    p_wb_candidate = sub.add_parser("vault-writeback-candidate", help="Create a reviewed-path Vault writeback candidate")
    p_wb_candidate.add_argument("--kind", default="handoff")
    p_wb_candidate.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_wb_preview = sub.add_parser("vault-writeback-preview", help="Render markdown preview for a writeback item")
    p_wb_preview.add_argument("--id", required=True)
    p_wb_reviewed = sub.add_parser("vault-writeback-reviewed", help="Write a reviewed or Gold item to Otto-Realm")
    p_wb_reviewed.add_argument("--id", default=None)
    p_wb_reviewed.add_argument("--gold-id", default=None)
    p_wb_reviewed.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    sub.add_parser("memory-policy", help="Show memory policy")
    p_mem_candidate = sub.add_parser("memory-candidate", help="Create a memory candidate")
    p_mem_candidate.add_argument("--kind", default="handoff")
    p_mem_candidate.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_mem_promote = sub.add_parser("memory-promote", help="Dry-run memory candidate promotion")
    p_mem_promote.add_argument("--candidate-id", required=True)
    p_mem_promote.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    sub.add_parser("review-queue", help="Show review queue counts")
    p_review_show = sub.add_parser("review-show", help="Show a review item")
    p_review_show.add_argument("--id", required=True)
    p_review_approve = sub.add_parser("review-approve", help="Approve a review item")
    p_review_approve.add_argument("--id", required=True)
    p_review_approve.add_argument("--note", default="")
    p_review_approve.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_review_reject = sub.add_parser("review-reject", help="Reject a review item")
    p_review_reject.add_argument("--id", required=True)
    p_review_reject.add_argument("--note", default="")
    p_review_reject.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_review_more = sub.add_parser("review-needs-more-evidence", help="Mark a review item as needing more evidence")
    p_review_more.add_argument("--id", required=True)
    p_review_more.add_argument("--note", default="")
    p_review_more.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_mem_promote_reviewed = sub.add_parser("memory-promote-reviewed", help="Promote an approved review to Gold")
    p_mem_promote_reviewed.add_argument("--review-id", required=True)
    p_mem_promote_reviewed.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    sub.add_parser("profile-policy", help="Show profile governance policy")
    sub.add_parser("council-policy", help="Show council governance policy")
    p_daily = sub.add_parser("daily-loop", help="Run dry-run daily human loop")
    p_daily.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    sub.add_parser("daily-handoff", help="Write daily handoff")
    sub.add_parser("action-queue", help="Write/list action queue")
    sub.add_parser("session-state", help="Write session state")
    sub.add_parser("ritual-prompt", help="Write ritual prompt")
    p_action_select = sub.add_parser("action-select", help="Select an action")
    p_action_select.add_argument("--id", required=True)
    p_action_outcome = sub.add_parser("action-outcome", help="Capture action outcome")
    p_action_outcome.add_argument("--id", required=True)
    p_action_outcome.add_argument("--result", choices=["completed", "failed", "skipped", "deferred"], required=True)
    p_action_outcome.add_argument("--note", default="")
    p_reflection = sub.add_parser("reflection-candidate", help="Create a reflection candidate from an outcome")
    p_reflection.add_argument("--from-outcome", required=True)
    p_close = sub.add_parser("close-human-loop", help="Close selected action -> outcome -> reflection")
    p_close.add_argument("--action-id", required=True)
    p_close.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_artifact_capture = sub.add_parser("artifact-capture", help="Capture a raw private idea")
    p_artifact_capture.add_argument("--text", required=True)
    p_artifact_triage = sub.add_parser("artifact-triage", help="Route private ideas into artifact candidates")
    p_artifact_triage.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_artifact_brief = sub.add_parser("artifact-brief", help="Create production brief from idea")
    p_artifact_brief.add_argument("--idea-id", required=True)
    p_artifact_brief.add_argument("--type", default=None)
    sub.add_parser("skill-map", help="Show skill hierarchy and blocker map")
    p_skill_review = sub.add_parser("skill-review", help="Generate bounded skill training tasks")
    p_skill_review.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    sub.add_parser("production-cron-plan", help="Show safe production cron plan")
    p_song_seed = sub.add_parser("song-seed-parse", help="Parse # anchors and @ atoms")
    p_song_seed.add_argument("--text", required=True)
    p_song_seed.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_song_skeleton = sub.add_parser("song-skeleton", help="Generate one SongForge skeleton candidate")
    p_song_skeleton.add_argument("--text", default="# Cinta Fana\n@ Penderitaan dan cinta tak kenal waktu.")
    p_song_skeleton.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_chord_cycle = sub.add_parser("chord-cycle", help="Generate a chord cycle for an atom")
    p_chord_cycle.add_argument("--seed-id", default=None)
    p_chord_cycle.add_argument("--atom-id", default=None)
    p_lyrics_translate = sub.add_parser("lyrics-translate", help="Generate phenomenological lyric translation")
    p_lyrics_translate.add_argument("--atom-id", required=True)
    p_lyrics_translate.add_argument("--cycle-id", required=True)
    p_midi_spec = sub.add_parser("midi-spec", help="Generate MIDI spec")
    p_midi_spec.add_argument("--cycle-id", required=True)
    p_song_feedback = sub.add_parser("song-feedback", help="Record SongForge feedback")
    p_song_feedback.add_argument("--song-id", required=True)
    p_song_feedback.add_argument("--decision", choices=["promote_for_work", "park", "reject", "needs_lyrics", "needs_chord", "needs_vocal_chop"], required=True)
    p_song_feedback.add_argument("--note", default="")
    p_paper = sub.add_parser("paper-onboarding", help="Create a research onboarding pack candidate")
    p_paper.add_argument("--topic", default="HCI value-sensitive design and interface constraints")
    p_paper.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_mem_ingest = sub.add_parser("memento-ingest-gold", help="Ingest a quizworthy Gold block")
    p_mem_ingest.add_argument("--gold-id", required=True)
    sub.add_parser("memento-due", help="Build Memento due queue")
    p_blocker = sub.add_parser("blocker-experiment", help="Generate bounded blocker experiment")
    p_blocker.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_visual = sub.add_parser("visual-inspo-query", help="Generate visual inspiration query")
    p_visual.add_argument("--artifact-id", default="manual")
    p_visual.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_creative_hb = sub.add_parser("creative-heartbeat", help="Run creative heartbeat dry-run")
    p_creative_hb.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    p_sanity_scan = sub.add_parser("sanity-scan", help="Run SAN1 dead-end/silent-failure/ambiguity/noisy-memory scan")
    p_sanity_scan.add_argument("--strict", action="store_true")
    sub.add_parser("sanity-index", help="Build state index for all Otto/OpenClaw/QMD state surfaces")
    sub.add_parser("dead-end-scan", help="Scan for dead-end state records")
    sub.add_parser("silent-failure-scan", help="Scan for successful commands with missing promised outputs")
    sub.add_parser("ambiguity-scan", help="Scan duplicate/conflicting/ambiguous state")
    sub.add_parser("noisy-memory-scan", help="Scan stale or low-signal candidate memory")
    sub.add_parser("sanity-quarantine", help="Show quarantine summary")
    sub.add_parser("sanity-repair-plan", help="Generate manual repair plan")

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
    if args.command == "source-registry":
        if args.write_default:
            write_default_source_registry()
        result = validate_source_registry()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "qmd-manifest":
        if args.write:
            result = write_qmd_manifest(runtime=args.runtime, qmd_command=args.qmd_command)
        else:
            manifest = build_qmd_manifest(runtime=args.runtime, qmd_command=args.qmd_command)
            result = {"ok": bool(manifest.get("ok")), "manifest": manifest}
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "wsl-health":
        result = build_wsl_health()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "docker-probe":
        result = docker_probe_diagnostics()
        _print(result)
        return 0 if result.get("daemon_running") else 1
    if args.command == "cron-status":
        _print(build_cron_status())
        return 0
    if args.command == "cron-steer":
        if args.clear or args.mode == "normal":
            result = clear_essay_control(reason=args.reason, source=args.source)
        else:
            result = steer_essay_control(
                mode=args.mode,
                topic=args.topic,
                days=args.days,
                reason=args.reason,
                source=args.source,
            )
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "openclaw-health":
        _print(build_openclaw_health())
        return 0
    if args.command == "qmd-index-health":
        _print(build_qmd_index_health())
        return 0
    if args.command == "qmd-reindex":
        result = run_qmd_index_refresh(timeout_seconds=args.timeout_seconds)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "qmd-search":
        result = qmd_search(" ".join(args.query), max_results=args.max_results, timeout_seconds=args.timeout_seconds)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "qmd-fanout":
        result = run_qmd_seed_fanout(
            args.seed,
            count=args.count,
            journal_first=args.journal_first,
            force_now=args.force_now,
        )
        _print(result)
        return 0 if result.get("status") == "ok" else 1
    if args.command == "openclaw-gateway-probe":
        result = probe_openclaw_gateway(
            port=args.port,
            host=args.host,
            runtime=args.runtime,
            timeout_seconds=args.timeout_seconds,
        )
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "openclaw-context-pack":
        result = write_openclaw_context_pack(task=args.task)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "openclaw-tool-manifest":
        result = write_openclaw_tool_manifest()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "runtime-owner":
        result = write_runtime_owner()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "single-owner-lock":
        result = write_single_owner_lock()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "runtime-smoke":
        result = build_runtime_smoke(gateway_port=args.gateway_port, strict=args.strict)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "wsl-live-preflight":
        result = build_wsl_live_preflight(gateway_port=args.gateway_port)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "wsl-live-promote":
        if args.write == args.dry_run:
            _print({"ok": False, "reason": "choose-exactly-one-of---dry-run-or---write"})
            return 1
        result = promote_wsl_live(gateway_port=args.gateway_port, write=args.write)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "wsl-live-rollback":
        result = rollback_wsl_live(gateway_port=args.gateway_port, write=args.write)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "wsl-live-status":
        result = build_wsl_live_status(gateway_port=args.gateway_port)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "openclaw-sync":
        _print(sync_openclaw_config())
        return 0
    if args.command == "operator-status":
        result = operator_status()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "operator-doctor":
        result = operator_doctor()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "operator-update":
        result = operator_update()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "wsl-gateway-start":
        result = start_wsl_gateway(port=args.port, wait_seconds=args.wait_seconds)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "wsl-gateway-stop":
        result = stop_wsl_gateway(port=args.port)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "wsl-gateway-restart":
        result = restart_wsl_gateway(port=args.port)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "native-fallback":
        result = fallback_to_native()
        _print(result)
        return 0 if result.get("ok") else 1
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
    if args.command == "openclaw-shadow-config":
        from pathlib import Path

        result = write_ubuntu_shadow_config(
            output=Path(args.output) if args.output else None,
            port=args.port,
            install=args.write,
            install_path=Path(args.install_path) if args.install_path else None,
        )
        _print(result)
        return 0 if result.get("ok") else 1
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
    if args.command == "vault-writeback-candidate":
        from .adapters.obsidian.writeback import create_writeback_candidate

        _print(create_writeback_candidate(kind=args.kind, dry_run=args.dry_run))
        return 0
    if args.command == "vault-writeback-preview":
        from .adapters.obsidian.writeback import preview_writeback

        result = preview_writeback(args.id)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "vault-writeback-reviewed":
        from .adapters.obsidian.writeback import write_gold_memory, write_reviewed_by_id
        from .memory.gold import load_gold

        if args.gold_id:
            gold = load_gold(args.gold_id)
            result = write_gold_memory(gold, dry_run=args.dry_run) if gold else {"ok": False, "reason": "gold-id-not-found"}
        else:
            result = write_reviewed_by_id(args.id, dry_run=args.dry_run)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "memory-policy":
        from .memory.memory_policy import load_memory_policy, memory_policy_health

        _print({"ok": True, "policy": load_memory_policy(), "health": memory_policy_health()})
        return 0
    if args.command == "memory-candidate":
        from .memory.promotion import create_candidate

        _print(create_candidate(kind=args.kind, dry_run=args.dry_run))
        return 0
    if args.command == "memory-promote":
        from .memory.promotion import promote_candidate

        result = promote_candidate(args.candidate_id, dry_run=args.dry_run)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "review-queue":
        from .memory.review_queue import write_review_state

        _print(write_review_state())
        return 0
    if args.command == "review-show":
        from .memory.review_queue import load_review

        result = load_review(args.id)
        _print({"ok": bool(result), "review": result})
        return 0 if result else 1
    if args.command == "review-approve":
        from .memory.review_queue import decide_review

        result = decide_review(args.id, "approved", note=args.note, dry_run=args.dry_run)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "review-reject":
        from .memory.review_queue import decide_review

        result = decide_review(args.id, "rejected", note=args.note, dry_run=args.dry_run)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "review-needs-more-evidence":
        from .memory.review_queue import decide_review

        result = decide_review(args.id, "needs_more_evidence", note=args.note, dry_run=args.dry_run)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "memory-promote-reviewed":
        from .memory.gold import promote_review_to_gold

        result = promote_review_to_gold(args.review_id, dry_run=args.dry_run)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "profile-policy":
        from .profile.profile_policy import load_functional_dimensions, load_profile_policy, profile_policy_health
        from .profile.support_context import load_support_context

        _print({"ok": True, "policy": load_profile_policy(), "dimensions": load_functional_dimensions(), "support_context": load_support_context(), "health": profile_policy_health()})
        return 0
    if args.command == "council-policy":
        from .council.policy import council_policy_health, load_council_policy

        _print({"ok": True, "policy": load_council_policy(), "health": council_policy_health()})
        return 0
    if args.command == "daily-loop":
        from .orchestration.daily_loop import run_daily_loop

        _print(run_daily_loop(dry_run=args.dry_run))
        return 0
    if args.command == "daily-handoff":
        from .orchestration.handoff import write_daily_handoff

        _print(write_daily_handoff())
        return 0
    if args.command == "action-queue":
        from .orchestration.action_queue import write_action_queue

        _print(write_action_queue())
        return 0
    if args.command == "session-state":
        from .session.session_state import write_active_memory_lens, write_session_state

        _print({"ok": True, "session": write_session_state(), "active_memory_lens": write_active_memory_lens()})
        return 0
    if args.command == "ritual-prompt":
        from .session.session_state import write_ritual_prompt

        _print(write_ritual_prompt())
        return 0
    if args.command == "action-select":
        from .orchestration.action_state import select_action

        result = select_action(args.id)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "action-outcome":
        from .orchestration.outcome_capture import capture_outcome

        result = capture_outcome(args.id, result=args.result, note=args.note)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "reflection-candidate":
        from .orchestration.reflection import create_reflection_candidate

        result = create_reflection_candidate(args.from_outcome)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "close-human-loop":
        from .orchestration.human_loop_closure import close_human_loop

        result = close_human_loop(args.action_id, dry_run=args.dry_run)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "artifact-capture":
        from .artifacts.idea_capture import capture_idea

        _print(capture_idea(args.text))
        return 0
    if args.command == "artifact-triage":
        from .artifacts.artifact_router import triage_ideas

        _print(triage_ideas(dry_run=args.dry_run))
        return 0
    if args.command == "artifact-brief":
        from .artifacts.production_brief import create_production_brief

        result = create_production_brief(args.idea_id, artifact_type=args.type)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "skill-map":
        from .skills.blocker_map import load_blocker_map
        from .skills.skill_graph import load_skill_hierarchy

        _print({"ok": True, "skill_hierarchy": load_skill_hierarchy(), "blocker_map": load_blocker_map()})
        return 0
    if args.command == "skill-review":
        from .skills.blocker_map import skill_review

        _print(skill_review(dry_run=args.dry_run))
        return 0
    if args.command == "production-cron-plan":
        from .orchestration.creative_cron import production_cron_plan

        _print(production_cron_plan())
        return 0
    if args.command == "song-seed-parse":
        from .creative.song_seed import persist_song_seed

        result = persist_song_seed(args.text, dry_run=args.dry_run)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "song-skeleton":
        from .creative.songforge import build_song_skeleton

        result = build_song_skeleton(args.text, dry_run=args.dry_run)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "chord-cycle":
        from .creative.songforge import chord_cycle_for_atom

        atom_id = args.atom_id or args.seed_id or "atom_manual"
        _print({"ok": True, "cycle": chord_cycle_for_atom(atom_id)})
        return 0
    if args.command == "lyrics-translate":
        from .creative.songforge import translate_atom

        result = translate_atom({"atom_id": args.atom_id, "candidate_images": []}, {"chord_cycle_id": args.cycle_id})
        _print({"ok": True, "lyric": result})
        return 0
    if args.command == "midi-spec":
        from .creative.songforge import build_midi_spec

        _print({"ok": True, "midi_spec": build_midi_spec({"chord_cycle_id": args.cycle_id, "tempo": 82, "meter": "4/4"})})
        return 0
    if args.command == "song-feedback":
        from .creative.songforge import record_song_feedback

        _print(record_song_feedback(args.song_id, args.decision, notes=args.note))
        return 0
    if args.command == "paper-onboarding":
        from .research.paper_onboarding import create_onboarding_pack

        _print(create_onboarding_pack(args.topic, dry_run=args.dry_run))
        return 0
    if args.command == "memento-ingest-gold":
        from .memory.gold import load_gold
        from .memento.quizworthy import ingest_gold

        gold = load_gold(args.gold_id)
        result = ingest_gold(gold) if gold else {"ok": False, "reason": "gold-id-not-found"}
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "memento-due":
        from .memento.scheduler_bridge import build_due_queue

        _print(build_due_queue())
        return 0
    if args.command == "blocker-experiment":
        from .skills.blocker_map import skill_review

        _print(skill_review(dry_run=args.dry_run))
        return 0
    if args.command == "visual-inspo-query":
        from .creative.inspo import build_visual_inspo_query

        _print(build_visual_inspo_query(args.artifact_id))
        return 0
    if args.command == "creative-heartbeat":
        from .orchestration.creative_heartbeat import run_creative_heartbeat

        _print(run_creative_heartbeat(dry_run=args.dry_run))
        return 0
    if args.command == "sanity-scan":
        from .sanity.repair_plan import run_sanity_scan

        result = run_sanity_scan(strict=args.strict)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "sanity-index":
        from .sanity.state_index import build_state_index

        _print({"ok": True, **build_state_index()})
        return 0
    if args.command == "dead-end-scan":
        from .sanity.dead_end_scan import scan_dead_ends

        result = scan_dead_ends()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "silent-failure-scan":
        from .sanity.silent_failure_scan import scan_silent_failures

        result = scan_silent_failures()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "ambiguity-scan":
        from .sanity.ambiguity_scan import scan_ambiguities

        result = scan_ambiguities()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "noisy-memory-scan":
        from .sanity.noisy_memory_scan import scan_noisy_memory

        result = scan_noisy_memory()
        _print(result)
        return 0 if result.get("ok") else 1
    if args.command == "sanity-quarantine":
        from .sanity.quarantine import quarantine_summary

        _print({"ok": True, "state_changed": False, "created_ids": [], "updated_ids": [], "warnings": [], "blockers": [], "quarantined": [], "next_required_action": None, "quarantine": quarantine_summary()})
        return 0
    if args.command == "sanity-repair-plan":
        from .sanity.repair_plan import generate_repair_plan

        plan = generate_repair_plan()
        _print({"ok": True, "state_changed": True, "created_ids": [], "updated_ids": [], "warnings": [], "blockers": [], "quarantined": [], "next_required_action": None, "repair_plan": plan})
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
