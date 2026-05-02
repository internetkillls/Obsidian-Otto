from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ..config import load_docker_config, load_env_file, load_paths
from ..docker_utils import cleanup_ephemeral_mcp_containers, docker_available, docker_daemon_running, docker_probe_diagnostics
from ..launcher_state import LauncherStateStore, mcp_configured
from ..openclaw_support import probe_openclaw_gateway, reload_openclaw_plugin_surface, restart_openclaw_gateway
from ..operator_control import (
    fallback_to_native,
    operator_doctor,
    operator_status,
    operator_update,
    restart_wsl_gateway,
    start_wsl_gateway,
    stop_wsl_gateway,
)
from ..orchestration.runtime_owner import decide_gateway_owner
from ..orchestration.wsl_live_migration import (
    build_wsl_live_preflight,
    build_wsl_live_status,
    promote_wsl_live,
    rollback_wsl_live,
)
from ..orchestration.graph_demotion import run_graph_demotion_followup
from ..orchestration.mentor import MentoringEngine
from ..state import read_json
from .janitor import run_janitor
from .health_repair import run_health_repair
from .loop import run_loop
from .repair import run_repair
from .runtime_support import RuntimeSnapshot, classify_runtime, clear_stale_runtime_pid, runtime_pid_file


RUNTIME_SCRIPT = Path("scripts/manage/runtime_loop.py")
SANITY_SCRIPT = Path("scripts/manage/sanity_check.py")
STATUS_SCRIPT = Path("scripts/manage/status_report.py")
TUI_SCRIPT = Path("scripts/manage/run_tui.py")
PIPELINE_SCRIPT = Path("scripts/manage/run_pipeline.py")
QUERY_SCRIPT = Path("scripts/manage/query_memory.py")
DREAM_SCRIPT = Path("scripts/manage/run_dream.py")
KAIROS_SCRIPT = Path("scripts/manage/run_kairos.py")
SYNC_OPENCLAW_SCRIPT = Path("scripts/manage/sync_openclaw_config.py")
INSTALL_HEALTH_AUTOMATION_SCRIPT = Path("scripts/manage/install_health_automation.py")
INSTALL_OPERATOR_SHORTCUTS_SCRIPT = Path("scripts/manage/install_operator_shortcuts.ps1")
METADATA_ENRICHMENT_SCRIPT = Path("scripts/manage/run_metadata_enrichment.py")
NOTION_EXPORT_HYGIENE_SCRIPT = Path("scripts/manage/run_notion_export_hygiene.py")


@dataclass
class ActionResult:
    status: str
    exit_code: int
    details: dict[str, object]
    next_screen: str | None = None


@dataclass(frozen=True)
class LauncherActionSpec:
    name: str
    label: str
    summary: str
    wrappers: tuple[str, ...]
    screen: str
    aliases: tuple[str, ...] = ()
    menu_key: str | None = None


def normalize_action_name(action: str) -> str:
    return action.strip().lower().replace("_", "-")


ACTION_SPECS: tuple[LauncherActionSpec, ...] = (
    LauncherActionSpec("initial", "Run initial setup", "Bootstrap the repo and Python environment.", ("scripts/shell/initial.bat",), "home", aliases=("init",), menu_key="1"),
    LauncherActionSpec("start", "Start runtime loop", "Launch the background Otto runtime loop.", ("scripts/shell/start.bat",), "home", aliases=("run",), menu_key="2"),
    LauncherActionSpec("stop", "Stop runtime loop", "Stop the background Otto runtime loop.", ("scripts/shell/stop.bat",), "home", menu_key="3"),
    LauncherActionSpec("tui", "Open live TUI", "Watch runtime health, handoff, and Gold state live.", ("scripts/shell/tui.bat",), "home", menu_key="4"),
    LauncherActionSpec("status", "Show status report", "Print an operator summary of runtime, handoff, and OpenClaw state.", ("scripts/shell/status.bat",), "home", menu_key="5"),
    LauncherActionSpec("reindex", "Run reindex pipeline", "Rebuild the scoped pipeline and refresh Gold/Silver state.", ("scripts/shell/reindex.bat",), "home", menu_key="6"),
    LauncherActionSpec("doctor", "Doctor checks", "Run status plus sanity checks and surface next fixes.", ("scripts/shell/doctor.bat",), "home", menu_key="7"),
    LauncherActionSpec("training-queue", "Training Queue", "Show active probes, pending tasks, and recent mentor resolutions.", ("scripts/shell/main.bat",), "home", aliases=("training",), menu_key="8"),
    LauncherActionSpec("resolve-training-task", "Resolve Training Task", "Mark one pending mentor task as done or skipped.", ("scripts/shell/main.bat",), "home", aliases=("resolve-training",), menu_key="9"),
    LauncherActionSpec("kairos", "Run KAIROS once", "Execute one KAIROS controller cycle.", ("scripts/shell/kairos.bat",), "advanced", menu_key="1"),
    LauncherActionSpec("dream", "Run Dream once", "Execute one dream consolidation cycle.", ("scripts/shell/dream.bat",), "advanced", menu_key="2"),
    LauncherActionSpec("query", "Query memory", "Run a fast retrieval query against the control-plane memory surfaces.", ("scripts/shell/query.bat",), "advanced", menu_key="3"),
    LauncherActionSpec("sync-openclaw", "Sync OpenClaw config", "Push repo OpenClaw config into the live gateway surface.", ("scripts/shell/sync-openclaw.bat",), "advanced", aliases=("openclaw-sync",), menu_key="4"),
    LauncherActionSpec("openclaw-gateway-probe", "Probe OpenClaw gateway", "Check the local OpenClaw HTTP gateway health.", ("scripts/shell/probe-openclaw-gateway.bat",), "advanced", aliases=("probe-openclaw-gateway",), menu_key="5"),
    LauncherActionSpec("openclaw-plugin-reload", "Reload OpenClaw plugin surface", "Soft-reload the plugin surface without a full gateway restart.", ("scripts/shell/reload-openclaw-plugin.bat",), "advanced", aliases=("reload-openclaw-plugin",), menu_key="6"),
    LauncherActionSpec("graph-demotion-followup", "Graph demotion follow-up", "Run the reviewed ALLO-only ALLOCATION-FAMILY follow-up with gateway preflight.", ("scripts/shell/graph-demotion-followup.bat",), "advanced", menu_key="7"),
    LauncherActionSpec("mcp-ready", "Prepare obsidian-mcp container", "Build and warm the MCP container without attaching stdio.", ("scripts/shell/launch-mcp.bat",), "advanced", aliases=("prepare-mcp",), menu_key="8"),
    LauncherActionSpec("kairos-tui", "KAIROS deep-dive TUI", "Open the KAIROS analysis console.", ("otto.bat",), "advanced", menu_key="9"),
    LauncherActionSpec("brain", "Run Brain CLI", "Run Otto brain subcommands such as self-model or predictions.", ("scripts/shell/brain.bat",), "advanced", menu_key="10"),
    LauncherActionSpec("docker-up", "Bring up Docker stack", "Start the configured Docker services for Otto.", ("scripts/shell/docker-up.bat",), "advanced", menu_key="11"),
    LauncherActionSpec("docker-clean", "Clean Docker stack", "Stop and clean the configured Docker services.", ("scripts/shell/docker-clean.bat",), "advanced", menu_key="12"),
    LauncherActionSpec("mcp-clean", "Clean stale MCP runs", "Remove leftover obsidian-mcp run containers without stopping the main stack.", ("scripts/shell/mcp-clean.bat",), "advanced", menu_key="13"),
    LauncherActionSpec("postgres-repair", "Repair Postgres", "Start and restart the configured Postgres service when it is unreachable.", ("scripts/shell/postgres-repair.bat",), "advanced", aliases=("repair-postgres",), menu_key="14"),
    LauncherActionSpec("health-repair", "Health repair", "Run safe health cleanup, Docker/Postgres repair, OpenClaw check, and runtime ensure.", ("scripts/shell/health-repair.bat",), "advanced", aliases=("repair-health",), menu_key="15"),
    LauncherActionSpec("fresh-everything", "Fresh everything", "Recreate the Docker stack, clean stale MCP runs, restart OpenClaw gateway, and ensure runtime.", ("scripts/shell/fresh-everything.bat",), "advanced", aliases=("fresh-start", "restart-fresh"), menu_key="16"),
    LauncherActionSpec("install-health-automation", "Install health automation", "Install Windows scheduled tasks for 3-hour health repair and login fresh start.", ("scripts/shell/install-health-automation.bat",), "advanced", aliases=("install-automation",), menu_key="17"),
    LauncherActionSpec("uninstall-health-automation", "Uninstall health automation", "Remove the Windows scheduled health/startup tasks.", ("scripts/shell/uninstall-health-automation.bat",), "advanced", aliases=("uninstall-automation",), menu_key="18"),
    LauncherActionSpec("metadata-enrich", "Metadata enrichment", "Normalize frontmatter, tags, wikilinks, and optional entity metadata.", ("scripts/shell/metadata-enrich.bat",), "advanced", aliases=("metadata-enrichment",), menu_key="19"),
    LauncherActionSpec("notion-export-hygiene", "Notion export hygiene", "Rename hash-suffixed notes, normalize frontmatter, and optionally reindex.", ("scripts/shell/notion-export-hygiene.bat",), "advanced", aliases=("notion-hygiene", "hash-cleanup", "path-cleanup"), menu_key="20"),
    LauncherActionSpec("operator-status", "Operator parity status", "Check native/WSL OpenClaw, QMD, cron, and heartbeat parity.", ("scripts/shell/operator-status.bat",), "advanced", aliases=("oo-status",), menu_key="21"),
    LauncherActionSpec("operator-doctor", "Operator doctor", "Sync operator config and report native/WSL parity without unsafe cutover.", ("scripts/shell/operator-doctor.bat",), "advanced", aliases=("oo-doctor",), menu_key="22"),
    LauncherActionSpec("operator-update", "Operator update", "Regenerate OpenClaw tool/context/QMD payloads and resync operator state.", ("scripts/shell/operator-update.bat",), "advanced", aliases=("oo-update",), menu_key="23"),
    LauncherActionSpec("gateway-owner", "Gateway owner decision", "Show whether WSL, native, or conflict is currently active.", ("scripts/shell/gateway-owner.bat", "scripts/shell/operator-decision.bat"), "home", aliases=("operator-decision",), menu_key="0"),
    LauncherActionSpec("wsl-live-preflight", "WSL live preflight", "Verify Ubuntu OpenClaw/QMD is safe to promote as live owner.", ("scripts/shell/wsl-live-preflight.bat",), "advanced", aliases=("preflight-wsl-live",), menu_key="25"),
    LauncherActionSpec("wsl-live-promote", "Promote WSL live", "Promote Ubuntu OpenClaw to live gateway and Telegram owner.", ("scripts/shell/wsl-live-promote.bat",), "advanced", aliases=("promote-wsl-live",), menu_key="26"),
    LauncherActionSpec("wsl-live-status", "WSL live status", "Summarize current WSL live owner, gateway, and rollback readiness.", ("scripts/shell/wsl-live-status.bat",), "advanced", aliases=("status-wsl-live",), menu_key="27"),
    LauncherActionSpec("wsl-live-rollback", "Rollback to Windows", "Disable Ubuntu Telegram and return gateway ownership to Windows.", ("scripts/shell/wsl-live-rollback.bat",), "advanced", aliases=("rollback-wsl-live",), menu_key="28"),
    LauncherActionSpec("wsl-gateway-start", "Start WSL gateway", "Start the WSL OpenClaw gateway using the current promoted config.", ("scripts/shell/wsl-gateway-start.bat",), "advanced", aliases=("start-wsl-gateway",), menu_key="29"),
    LauncherActionSpec("wsl-gateway-stop", "Stop WSL gateway", "Stop the WSL OpenClaw gateway.", ("scripts/shell/wsl-gateway-stop.bat",), "advanced", aliases=("stop-wsl-gateway",), menu_key="30"),
    LauncherActionSpec("wsl-gateway-restart", "Restart WSL gateway", "Restart and probe the current WSL OpenClaw gateway.", ("scripts/shell/wsl-gateway-restart.bat",), "advanced", aliases=("restart-wsl-gateway",), menu_key="31"),
    LauncherActionSpec("native-fallback", "Fallback to native gateway", "Restart native Windows OpenClaw only when WSL is not active.", ("scripts/shell/native-fallback.bat",), "advanced", aliases=("switch-native", "windows-fallback"), menu_key="32"),
    LauncherActionSpec("install-operator-shortcuts", "Install desktop/startup shortcuts", "Create desktop launcher shortcuts and login startup task for WSL gateway.", ("scripts/shell/install-operator-shortcuts.bat",), "advanced", aliases=("install-shortcuts",), menu_key="33"),
    LauncherActionSpec("docker-probe", "Probe Docker bridge", "Diagnose direct vs PowerShell-backed Docker access used by status and infra checks.", ("scripts/shell/docker-probe.bat", "otto.bat"), "advanced", aliases=("docker-diagnostics",)),
    LauncherActionSpec("openclaw-gateway-restart", "Restart OpenClaw gateway", "Force-restart the OpenClaw gateway process.", ("scripts/shell/reload-openclaw-gateway.bat",), "advanced", aliases=("reload-openclaw-gateway",)),
    LauncherActionSpec("launch-mcp", "Attach obsidian-mcp stdio", "Attach stdio to the running obsidian-mcp container.", ("scripts/shell/launch-mcp.bat",), "advanced", aliases=("mcp",)),
    LauncherActionSpec("sanity-check", "Run sanity check", "Run the repo sanity audit and write a report.", ("scripts/shell/sanity-check.bat",), "advanced"),
)

ACTION_SPEC_BY_NAME = {spec.name: spec for spec in ACTION_SPECS}
ACTION_ALIAS_MAP: dict[str, str] = {}
for _spec in ACTION_SPECS:
    ACTION_ALIAS_MAP[normalize_action_name(_spec.name)] = _spec.name
    for _alias in _spec.aliases:
        ACTION_ALIAS_MAP[normalize_action_name(_alias)] = _spec.name
    for _wrapper in _spec.wrappers:
        ACTION_ALIAS_MAP[normalize_action_name(_wrapper.removesuffix(".bat"))] = _spec.name


def action_specs_for_screen(screen: str | None = None) -> list[LauncherActionSpec]:
    specs = list(ACTION_SPECS)
    if screen:
        specs = [spec for spec in specs if spec.screen == screen]
    return sorted(specs, key=lambda spec: (spec.screen, int(spec.menu_key or "999"), spec.name))


def resolve_action_spec(action: str) -> LauncherActionSpec | None:
    canonical = ACTION_ALIAS_MAP.get(normalize_action_name(action))
    if not canonical:
        return None
    return ACTION_SPEC_BY_NAME.get(canonical)


def render_action_catalog(screen: str | None = None) -> str:
    groups = ("home", "advanced") if screen is None else (screen,)
    lines = ["Obsidian-Otto Command Surface", ""]
    for group in groups:
        specs = action_specs_for_screen(group)
        if not specs:
            continue
        lines.append(group.upper())
        for spec in specs:
            wrappers = ", ".join(spec.wrappers)
            lines.append(f"- {spec.name}: {spec.summary}")
            lines.append(f"  wrappers: {wrappers}")
        lines.append("")
    lines.append("Use `otto.bat describe <action>` for one command.")
    return "\n".join(lines).rstrip() + "\n"


def render_action_description(action: str) -> tuple[int, str]:
    spec = resolve_action_spec(action)
    if spec is None:
        return 1, f"Unknown Otto action: {action}\n"
    wrappers = ", ".join(spec.wrappers)
    aliases = ", ".join(spec.aliases) if spec.aliases else "none"
    text = [
        f"Action: {spec.name}",
        f"Label: {spec.label}",
        f"Screen: {spec.screen}",
        f"Wrappers: {wrappers}",
        f"Aliases: {aliases}",
        f"Summary: {spec.summary}",
    ]
    return 0, "\n".join(text) + "\n"


def _runtime_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src = str(root / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not existing else f"{src}{os.pathsep}{existing}"
    return env


class LauncherApp:
    def __init__(self) -> None:
        self.paths = load_paths()
        self.root = self.paths.repo_root
        self.state = LauncherStateStore()

    def runtime_snapshot(self) -> RuntimeSnapshot:
        return classify_runtime(runtime_pid_file(self.root))

    def write_current(self, screen: str) -> RuntimeSnapshot:
        snapshot = self.runtime_snapshot()
        self.state.write_current(
            screen=screen,
            runtime_status=snapshot.status,
            runtime_pid=snapshot.pid,
        )
        return snapshot

    def list_actions(self, screen: str | None = None) -> list[LauncherActionSpec]:
        return action_specs_for_screen(screen)

    def describe_action(self, action: str) -> LauncherActionSpec | None:
        return resolve_action_spec(action)

    def run(self, screen: str = "home") -> int:
        current_screen = screen
        while True:
            snapshot = self.write_current(current_screen)
            self._render_screen(current_screen, snapshot)
            choice = input("Select option: ").strip()
            action = self._resolve_choice(current_screen, choice)
            if action is None:
                print("[WARN] Invalid selection.")
                time.sleep(1)
                continue
            if action == "exit":
                return 0
            if action == "back":
                current_screen = "home"
                continue
            if action == "advanced":
                current_screen = "advanced"
                continue

            result = self.run_action(action, screen=current_screen, interactive=True)
            if result.next_screen is not None:
                current_screen = result.next_screen
            if action not in {"tui", "launch-mcp"}:
                input("Press Enter to return to launcher...")

    def run_action(self, action: str, *, screen: str, interactive: bool, extra_args: Sequence[str] | None = None) -> ActionResult:
        started = time.time()
        spec = self.describe_action(action)
        action_name = spec.name if spec else self._normalize_action_name(action)
        args = list(extra_args or [])

        if action_name == "advanced":
            return ActionResult(status="ok", exit_code=0, details={}, next_screen="advanced")

        handlers = {
            "initial": self._action_initial,
            "init": self._action_initial,
            "start": self._action_start,
            "stop": self._action_stop,
            "status": self._action_status,
            "doctor": self._action_doctor,
            "training-queue": self._action_training_queue,
            "resolve-training-task": self._action_resolve_training_task,
            "repair": self._action_repair,
            "janitor": self._action_janitor,
            "loop": self._action_loop,
            "tui": self._action_tui,
            "kairos-tui": self._action_kairos_tui,
            "reindex": self._action_reindex,
            "query": self._action_query,
            "kairos": self._action_kairos,
            "dream": self._action_dream,
            "sync-openclaw": self._action_sync_openclaw,
            "openclaw-sync": self._action_sync_openclaw,
            "operator-status": self._action_operator_status,
            "oo-status": self._action_operator_status,
            "operator-doctor": self._action_operator_doctor,
            "oo-doctor": self._action_operator_doctor,
            "operator-update": self._action_operator_update,
            "oo-update": self._action_operator_update,
            "gateway-owner": self._action_gateway_owner,
            "operator-decision": self._action_gateway_owner,
            "wsl-live-preflight": self._action_wsl_live_preflight,
            "preflight-wsl-live": self._action_wsl_live_preflight,
            "wsl-live-promote": self._action_wsl_live_promote,
            "promote-wsl-live": self._action_wsl_live_promote,
            "wsl-live-status": self._action_wsl_live_status,
            "status-wsl-live": self._action_wsl_live_status,
            "wsl-live-rollback": self._action_wsl_live_rollback,
            "rollback-wsl-live": self._action_wsl_live_rollback,
            "wsl-gateway-start": self._action_wsl_gateway_start,
            "start-wsl-gateway": self._action_wsl_gateway_start,
            "wsl-gateway-stop": self._action_wsl_gateway_stop,
            "stop-wsl-gateway": self._action_wsl_gateway_stop,
            "wsl-gateway-restart": self._action_wsl_gateway_restart,
            "restart-wsl-gateway": self._action_wsl_gateway_restart,
            "native-fallback": self._action_native_fallback,
            "switch-native": self._action_native_fallback,
            "windows-fallback": self._action_native_fallback,
            "install-operator-shortcuts": self._action_install_operator_shortcuts,
            "install-shortcuts": self._action_install_operator_shortcuts,
            "openclaw-gateway-probe": self._action_openclaw_gateway_probe,
            "openclaw-gateway-restart": self._action_openclaw_gateway_restart,
            "openclaw-plugin-reload": self._action_openclaw_plugin_reload,
            "graph-demotion-followup": self._action_graph_demotion_followup,
            "mcp-ready": self._action_mcp_ready,
            "prepare-mcp": self._action_mcp_ready,
            "mcp": self._action_launch_mcp,
            "launch-mcp": self._action_launch_mcp,
            "brain": self._action_brain,
            "docker-up": self._action_docker_up,
            "docker-clean": self._action_docker_clean,
            "mcp-clean": self._action_mcp_clean,
            "postgres-repair": self._action_postgres_repair,
            "repair-postgres": self._action_postgres_repair,
            "health-repair": self._action_health_repair,
            "repair-health": self._action_health_repair,
            "fresh-everything": self._action_fresh_everything,
            "fresh-start": self._action_fresh_everything,
            "restart-fresh": self._action_fresh_everything,
            "install-health-automation": self._action_install_health_automation,
            "install-automation": self._action_install_health_automation,
            "uninstall-health-automation": self._action_uninstall_health_automation,
            "uninstall-automation": self._action_uninstall_health_automation,
            "metadata-enrich": self._action_metadata_enrich,
            "metadata-enrichment": self._action_metadata_enrich,
            "notion-export-hygiene": self._action_notion_export_hygiene,
            "notion-hygiene": self._action_notion_export_hygiene,
            "hash-cleanup": self._action_notion_export_hygiene,
            "path-cleanup": self._action_notion_export_hygiene,
            "docker-probe": self._action_docker_probe,
            "docker-diagnostics": self._action_docker_probe,
            "sanity-check": self._action_sanity_check,
            "run": self._action_start,
        }
        handler = handlers.get(action_name)
        if handler is None:
            raise ValueError(f"Unknown launcher action: {action}")

        result = handler(args=args, interactive=interactive)
        duration_ms = int((time.time() - started) * 1000)
        self.state.record_action(
            action=action_name,
            screen=screen,
            status=result.status,
            exit_code=result.exit_code,
            duration_ms=duration_ms,
            details=result.details,
        )
        self.write_current(screen if result.next_screen is None else result.next_screen)
        return result

    def _render_screen(self, screen: str, snapshot: RuntimeSnapshot) -> None:
        os.system("cls" if os.name == "nt" else "clear")
        print("========================================================")
        print(f"Obsidian-Otto Control Launcher [{screen.upper()}]")
        print("========================================================")
        print(f"Repo:    {self.root}")
        print(f"Vault:   {self.paths.vault_path or '(not configured)'}")
        print(f"Task:    {self._active_task_summary()}")
        print(f"Runtime: {snapshot.status}" + (f" (PID {snapshot.pid})" if snapshot.pid else ""))
        print(f"MCP:     {self._mcp_summary()}")
        current = read_json(self.state.current_path, default={}) or {}
        recommendations = current.get("recommended_next_actions") or []
        if recommendations:
            print()
            print("Recommended next:")
            for item in recommendations:
                print(f"- {item}")
        print()

        menu = self._screen_menu(screen)
        print("Actions:")
        for key, label in menu:
            print(f"[{key}] {label}")
        print()

    def _active_task_summary(self) -> str:
        task_dir = self.root / "tasks" / "active"
        if not task_dir.exists():
            return "none"
        names = sorted(path.name for path in task_dir.iterdir() if path.is_file())
        if not names:
            return "none"
        if len(names) == 1:
            return names[0]
        return f"{names[0]} (+{len(names) - 1} more)"

    def _mcp_summary(self) -> str:
        cfg = load_docker_config()
        services = cfg.get("services") or []
        if "obsidian-mcp" not in services:
            return "not declared in docker.yaml"
        if not cfg.get("enabled", False):
            return "disabled in docker.yaml"
        env = load_env_file(self.root / ".env")
        vault_host = env.get("OBSIDIAN_VAULT_HOST") or str(self.paths.vault_path or "")
        if not vault_host:
            return "enabled, but vault host is not configured"
        return "enabled for obsidian-mcp"

    def _mentor_snapshot(self) -> dict[str, Any]:
        try:
            return MentoringEngine().load_state_snapshot()
        except RuntimeError:
            return {
                "active_probes": [],
                "pending_tasks": [],
                "completed_tasks": [],
                "skipped_tasks": [],
                "weakness_registry": {},
                "feedback_loop_ready": False,
            }

    def _screen_menu(self, screen: str) -> list[tuple[str, str]]:
        if screen == "advanced":
            menu = [(spec.menu_key or "", f"{spec.label} - {spec.summary}") for spec in self.list_actions("advanced") if spec.menu_key]
            menu.append(("0", "Back to home"))
            return menu
        menu = [(spec.menu_key or "", f"{spec.label} - {spec.summary}") for spec in self.list_actions("home") if spec.menu_key]
        menu.extend([("a", "Open advanced tools"), ("q", "Exit launcher")])
        return menu

    def _resolve_choice(self, screen: str, choice: str) -> str | None:
        normalized_choice = choice.lower()
        if screen == "advanced":
            mapping = {spec.menu_key: spec.name for spec in self.list_actions("advanced") if spec.menu_key}
            mapping["0"] = "back"
        else:
            mapping = {spec.menu_key: spec.name for spec in self.list_actions("home") if spec.menu_key}
            mapping["a"] = "advanced"
            mapping["q"] = "exit"
        return mapping.get(normalized_choice)

    def _normalize_action_name(self, action: str) -> str:
        return normalize_action_name(action)

    def _run_python_script(self, script: Path, args: Sequence[str] | None = None) -> int:
        command = [sys.executable, str(self.root / script), *(args or [])]
        result = subprocess.run(command, cwd=self.root, env=_runtime_env(self.root), check=False)
        return result.returncode

    def _run_batch_script(self, name: str, args: Sequence[str] | None = None) -> int:
        command = ["cmd", "/c", name, *(args or [])]
        result = subprocess.run(command, cwd=self.root, check=False)
        return result.returncode

    def _compose_profile_args(self) -> list[str]:
        cfg = load_docker_config()
        services = set(cfg.get("services") or [])
        profiles: list[str] = []

        if "chromadb" in services:
            profiles.append("vector")
        if "otto-indexer" in services:
            profiles.append("worker")
        if "obsidian-mcp" in services:
            profiles.extend(list((cfg.get("mcp") or {}).get("profiles") or []))

        unique_profiles: list[str] = []
        for profile in profiles:
            if profile and profile not in unique_profiles:
                unique_profiles.append(profile)

        args: list[str] = []
        for profile in unique_profiles:
            args.extend(["--profile", profile])
        return args

    def _action_initial(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_batch_script("initial.bat", args=args)
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={})

    def _action_start(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        snapshot = self.runtime_snapshot()
        if snapshot.status == "RUNNING":
            print(f"[Otto] Runtime already running with PID {snapshot.pid}.")
            return ActionResult(status="ok", exit_code=0, details={"runtime_status": "already-running", "runtime_pid": snapshot.pid})
        if snapshot.status == "STALE":
            clear_stale_runtime_pid(runtime_pid_file(self.root))
            print("[Otto] Cleared stale runtime PID file.")

        runtime_script = self.root / RUNTIME_SCRIPT
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            [sys.executable, str(runtime_script)],
            cwd=self.root,
            env=_runtime_env(self.root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

        confirmed = RuntimeSnapshot(status="STOPPED", pid=None)
        for _ in range(20):
            time.sleep(0.25)
            confirmed = self.runtime_snapshot()
            if confirmed.status == "RUNNING":
                break
        if confirmed.status == "RUNNING":
            print(f"[Otto] Runtime started in background via .venv\\Scripts\\python.exe. PID {confirmed.pid}.")
            print("[Otto] Monitor it from TUI or logs\\app\\otto.log.")
            return ActionResult(status="ok", exit_code=0, details={"runtime_status": "started", "runtime_pid": confirmed.pid})

        print("[Otto] Runtime did not confirm start. Check logs\\app\\otto.log")
        return ActionResult(status="error", exit_code=1, details={"runtime_status": confirmed.status})

    def _action_stop(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        snapshot = self.runtime_snapshot()
        if snapshot.status == "STOPPED":
            print("[Otto] Runtime already stopped.")
            return ActionResult(status="ok", exit_code=0, details={"runtime_status": "already-stopped"})
        if snapshot.status == "STALE":
            clear_stale_runtime_pid(runtime_pid_file(self.root))
            print("[Otto] Runtime PID file stale. Cleaned.")
            return ActionResult(status="ok", exit_code=0, details={"runtime_status": "stale-cleaned"})

        if os.name == "nt":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Stop-Process -Id {snapshot.pid} -Force -ErrorAction Stop",
                ],
                cwd=self.root,
                check=False,
            )
            exit_code = result.returncode
        else:
            os.kill(int(snapshot.pid or 0), 15)
            exit_code = 0

        for _ in range(20):
            time.sleep(0.25)
            current = self.runtime_snapshot()
            if current.status != "RUNNING":
                break
        clear_stale_runtime_pid(runtime_pid_file(self.root))
        if exit_code == 0:
            print(f"[Otto] Runtime stopped{f' (PID {snapshot.pid})' if snapshot.pid else ''}.")
            return ActionResult(status="ok", exit_code=0, details={"runtime_status": "stopped", "runtime_pid": snapshot.pid})

        print(f"[Otto] Failed to stop runtime PID {snapshot.pid}.")
        return ActionResult(status="error", exit_code=exit_code, details={"runtime_status": "stop-failed", "runtime_pid": snapshot.pid})

    def _action_status(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        script_args = list(args) if args else ["--summary"]
        exit_code = self._run_python_script(STATUS_SCRIPT, args=script_args)
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={})

    def _action_doctor(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        snapshot = self.runtime_snapshot()
        print("=== Obsidian-Otto Doctor ===")
        print("Runtime: " + snapshot.status + (f" (PID {snapshot.pid})" if snapshot.pid else ""))
        print()
        status_exit = self._run_python_script(STATUS_SCRIPT, args=["--summary"])
        print()
        sanity_exit = self._run_python_script(SANITY_SCRIPT, args=["--write-report"])
        print()
        print("To clean Docker services, run docker-clean.bat")
        print("To rerun the data pipeline, run reindex.bat")
        exit_code = status_exit if status_exit != 0 else sanity_exit
        return ActionResult(
            status="ok" if exit_code == 0 else "error",
            exit_code=exit_code,
            details={"status_exit": status_exit, "sanity_exit": sanity_exit},
        )

    def _action_training_queue(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        snapshot = self._mentor_snapshot()
        active_probes = snapshot.get("active_probes") or []
        pending_tasks = snapshot.get("pending_tasks") or []
        completed_tasks = snapshot.get("completed_tasks") or []
        skipped_tasks = snapshot.get("skipped_tasks") or []
        weakness_registry = snapshot.get("weakness_registry") or {}

        print("=== Training Queue ===")
        print(f"Feedback loop ready: {snapshot.get('feedback_loop_ready', False)}")
        print(f"Active probes: {len(active_probes)}")
        print(f"Pending tasks: {len(pending_tasks)}")
        print(f"Done: {len(completed_tasks)}")
        print(f"Skipped: {len(skipped_tasks)}")
        print()
        print("Active probes:")
        if active_probes:
            for item in active_probes[:5]:
                print(f"- {item['title']} | probe_id={item['probe_id']} | weakness={item['weakness_key']}")
        else:
            print("- (none)")
        print()
        print("Pending tasks:")
        if pending_tasks:
            for item in pending_tasks[:5]:
                print(f"- {item['title']} | task_id={item['task_id']} | gap={item.get('gap_type', 'unknown')}")
        else:
            print("- (none)")
        print()
        print("Latest classified gaps:")
        if weakness_registry:
            for weakness_key, entry in list(weakness_registry.items())[:5]:
                print(
                    f"- {weakness_key} | gap={entry.get('latest_gap_type', 'unknown')} | "
                    f"last={entry.get('last_resolution_outcome') or 'none'}"
                )
        else:
            print("- (none)")
        print()
        print("Recently resolved:")
        recent_resolved = [*completed_tasks[:3], *skipped_tasks[:3]]
        if recent_resolved:
            for item in recent_resolved:
                print(f"- [{item['status']}] {item['title']} | task_id={item['task_id']}")
        else:
            print("- (none)")
        return ActionResult(
            status="ok",
            exit_code=0,
            details={
                "active_probes": len(active_probes),
                "pending_tasks": len(pending_tasks),
            },
        )

    def _action_resolve_training_task(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        engine = MentoringEngine()
        pending_tasks = engine.list_pending_tasks()
        if not pending_tasks:
            print("[Otto] No pending training tasks.")
            return ActionResult(status="ok", exit_code=0, details={"resolved": False, "reason": "no-pending-tasks"})

        task_id = ""
        outcome = ""
        if len(args) >= 2:
            task_id = args[0]
            outcome = args[1]
        elif interactive:
            print("Pending mentor tasks:")
            for index, item in enumerate(pending_tasks, start=1):
                print(f"[{index}] {item.title} | task_id={item.task_id} | gap={item.gap_type}")
            selected = input("Choose task number: ").strip()
            if not selected.isdigit():
                print("[ERROR] Task selection must be a number.")
                return ActionResult(status="error", exit_code=1, details={"reason": "invalid-selection"})
            index = int(selected) - 1
            if index < 0 or index >= len(pending_tasks):
                print("[ERROR] Task selection out of range.")
                return ActionResult(status="error", exit_code=1, details={"reason": "selection-out-of-range"})
            task_id = pending_tasks[index].task_id
            outcome = input("Outcome [done/skipped]: ").strip().lower()
        else:
            print("[ERROR] task_id and outcome are required.")
            return ActionResult(status="error", exit_code=1, details={"reason": "missing-args"})

        resolved = engine.resolve_pending_task(task_id=task_id, outcome=outcome)
        if resolved is None:
            print(f"[ERROR] Could not resolve pending task: {task_id}")
            return ActionResult(status="error", exit_code=1, details={"reason": "task-not-found", "task_id": task_id})
        print(f"[Otto] Marked '{resolved.title}' as {resolved.status}.")
        return ActionResult(
            status="ok",
            exit_code=0,
            details={
                "resolved": True,
                "task_id": resolved.task_id,
                "status": resolved.status,
                "path": resolved.path,
            },
        )

    def _action_repair(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        scope: str | None = None
        dry_run = False
        extra = list(args)
        index = 0
        while index < len(extra):
            token = extra[index]
            if token == "--dry-run":
                dry_run = True
            elif token == "--scope" and index + 1 < len(extra):
                scope = extra[index + 1]
                index += 1
            elif scope is None:
                scope = token
            index += 1
        result = run_repair(root=self.root, runtime_env=_runtime_env(self.root), scope=scope, dry_run=dry_run)
        if result["issues"]:
            status = "error"
            exit_code = 1
        elif result["warnings"]:
            status = "warn"
            exit_code = 0
        else:
            status = "ok"
            exit_code = 0
        print(result)
        return ActionResult(status=status, exit_code=exit_code, details=result)

    def _action_janitor(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        dry_run = "--dry-run" in args or not args
        compact = "--compact" in args
        otto_realm_staging_only = "--otto-realm-staging-only" in args
        result = run_janitor(
            root=self.root,
            dry_run=dry_run,
            compact=compact,
            otto_realm_staging_only=otto_realm_staging_only,
        )
        print(result)
        return ActionResult(status="ok", exit_code=0, details=result)

    def _action_loop(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        mode = "pulse"
        extra = list(args)
        if "--mode" in extra:
            idx = extra.index("--mode")
            if idx + 1 < len(extra):
                mode = extra[idx + 1]
        result = run_loop(root=self.root, runtime_env=_runtime_env(self.root), mode=mode)
        print(result)
        return ActionResult(status="ok", exit_code=0, details=result)

    def _action_tui(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_python_script(TUI_SCRIPT, args=["--refresh-seconds", "2"])
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={})

    def _action_kairos_tui(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        """Launch KAIROS deep-dive TUI: dig/train commands."""
        console_cmds = [
            sys.executable, "-c",
            "import sys; sys.path.insert(0, 'src'); "
            "from otto.app.kairos_tui import run_kairos_tui; run_kairos_tui()",
        ]
        result = subprocess.run(console_cmds, cwd=self.root, check=False)
        return ActionResult(status="ok" if result.returncode == 0 else "error", exit_code=result.returncode, details={})

    def _action_reindex(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        scope = ""
        extra = list(args)
        if extra:
            if extra[0] == "--scope" and len(extra) >= 2:
                scope = extra[1]
            else:
                scope = " ".join(extra)
        elif interactive:
            scope = input("Optional scope (blank for full vault): ").strip()
        script_args = ["--full"]
        if scope:
            script_args.extend(["--scope", scope])
        exit_code = self._run_python_script(PIPELINE_SCRIPT, args=script_args)
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={"scope": scope or None})

    def _action_query(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        query = " ".join(args).strip()
        if not query and interactive:
            query = input("Enter query: ").strip()
        if not query:
            print("[ERROR] Query is required.")
            return ActionResult(status="error", exit_code=1, details={"reason": "missing-query"})
        exit_code = self._run_python_script(QUERY_SCRIPT, args=["--mode", "fast", "--query", query])
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={"query": query})

    def _action_kairos(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_python_script(KAIROS_SCRIPT, args=["--once"])
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={})

    def _action_dream(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_python_script(DREAM_SCRIPT, args=["--once"])
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={})

    def _action_sync_openclaw(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_python_script(SYNC_OPENCLAW_SCRIPT)
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={})

    def _action_operator_status(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = operator_status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_operator_doctor(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = operator_doctor()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_operator_update(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = operator_update()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_gateway_owner(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = decide_gateway_owner()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(status="ok", exit_code=0, details=result)

    def _action_wsl_live_preflight(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = build_wsl_live_preflight()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_wsl_live_promote(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        write = "--write" in args or interactive
        result = promote_wsl_live(write=write)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_wsl_live_status(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = build_wsl_live_status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_wsl_live_rollback(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = rollback_wsl_live(write=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_wsl_gateway_start(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = start_wsl_gateway()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_wsl_gateway_stop(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = stop_wsl_gateway()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_wsl_gateway_restart(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = restart_wsl_gateway()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_native_fallback(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = fallback_to_native()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_install_operator_shortcuts(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        script = self.root / INSTALL_OPERATOR_SHORTCUTS_SCRIPT
        if not script.exists():
            print(f"[ERROR] Missing shortcut installer: {script}")
            return ActionResult(status="error", exit_code=1, details={"reason": "missing-installer"})
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                *args,
            ],
            cwd=self.root,
            check=False,
        )
        return ActionResult(
            status="ok" if result.returncode == 0 else "error",
            exit_code=result.returncode,
            details={"script": str(script), "args": list(args)},
        )

    def _action_openclaw_gateway_probe(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = probe_openclaw_gateway(timeout_seconds=5.0)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_openclaw_gateway_restart(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = restart_openclaw_gateway(wait_seconds=30)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_openclaw_plugin_reload(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = reload_openclaw_plugin_surface(wait_seconds=30, hard_restart="--hard-restart" in args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_graph_demotion_followup(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        max_writes = 6
        timeout_seconds = 60
        for item in args:
            if item.startswith("--max-demotion-writes="):
                try:
                    max_writes = int(item.split("=", 1)[1])
                except ValueError:
                    pass
            elif item == "--max-demotion-writes":
                continue
            elif item.startswith("--timeout-seconds="):
                try:
                    timeout_seconds = int(item.split("=", 1)[1])
                except ValueError:
                    pass
        result = run_graph_demotion_followup(max_demotion_writes=max_writes, timeout_seconds=timeout_seconds)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("status") == "applied" else "error",
            exit_code=0 if result.get("status") == "applied" else 1,
            details=result,
        )

    def _action_mcp_ready(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        return self._action_launch_mcp(args=[*args, "--ready-only"], interactive=interactive)

    def _action_launch_mcp(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        normalized = list(args)
        if "--help" in normalized:
            print("Usage: launch-mcp.bat [--build-only] [--no-build] [--ready-only]")
            print("  --build-only  Build obsidian-mcp image and exit.")
            print("  --no-build    Skip docker compose build and run directly.")
            print("  --ready-only  Build and start the container, but do not attach stdio.")
            return ActionResult(status="ok", exit_code=0, details={"help_shown": True})

        do_build = "--no-build" not in normalized
        build_only = "--build-only" in normalized
        ready_only = "--ready-only" in normalized
        env = load_env_file(self.root / ".env")
        vault_host = env.get("OBSIDIAN_VAULT_HOST") or str(self.paths.vault_path or "")
        vault_path = env.get("OBSIDIAN_VAULT_PATH") or "/vault"
        notes: list[str] = []
        if not mcp_configured():
            notes.append("disabled in config/docker.yaml")
            if not build_only:
                print("[ERROR] obsidian-mcp is disabled in config/docker.yaml.")
                print("        Use --build-only for manual preflight, or enable docker.enabled when ready.")
                self.state.record_mcp_run(
                    mode="build_only" if build_only else ("container_ready" if ready_only else "stdio_run"),
                    vault_host=vault_host or None,
                    vault_path=vault_path,
                    build_exit=None,
                    run_exit=1,
                    notes=notes,
                )
                return ActionResult(status="error", exit_code=1, details={"reason": "mcp-disabled"})
            print("[WARN] obsidian-mcp is disabled in config/docker.yaml. Running build-only preflight.")

        if not docker_available():
            print("[ERROR] Docker is not installed or not on PATH.")
            self.state.record_mcp_run(
                mode="build_only" if build_only else ("container_ready" if ready_only else "stdio_run"),
                vault_host=vault_host or None,
                vault_path=vault_path,
                build_exit=None,
                run_exit=1,
                notes=notes + ["docker not available"],
            )
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-found"})

        if not docker_daemon_running():
            print("[ERROR] Docker is not running. Start Docker Desktop first.")
            self.state.record_mcp_run(
                mode="build_only" if build_only else ("container_ready" if ready_only else "stdio_run"),
                vault_host=vault_host or None,
                vault_path=vault_path,
                build_exit=None,
                run_exit=1,
                notes=notes + ["docker daemon unavailable"],
            )
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-running"})

        if not vault_host:
            print("[ERROR] OBSIDIAN_VAULT_HOST is not configured in .env.")
            self.state.record_mcp_run(
                mode="build_only" if build_only else ("container_ready" if ready_only else "stdio_run"),
                vault_host=None,
                vault_path=vault_path,
                build_exit=None,
                run_exit=1,
                notes=notes + ["missing OBSIDIAN_VAULT_HOST"],
            )
            return ActionResult(status="error", exit_code=1, details={"reason": "missing-vault-host"})

        if not Path(vault_host).exists():
            print(f"[ERROR] OBSIDIAN_VAULT_HOST does not exist: {vault_host}")
            self.state.record_mcp_run(
                mode="build_only" if build_only else ("container_ready" if ready_only else "stdio_run"),
                vault_host=vault_host,
                vault_path=vault_path,
                build_exit=None,
                run_exit=1,
                notes=notes + ["vault host path missing"],
            )
            return ActionResult(status="error", exit_code=1, details={"reason": "missing-vault-path"})

        build_exit: int | None = None
        run_exit: int | None = None
        stale_cleanup = cleanup_ephemeral_mcp_containers()
        if stale_cleanup.get("removed"):
            count = len(stale_cleanup["removed"])
            notes.append(f"cleaned {count} stale obsidian-mcp run container(s)")
            print(f"[OTTO] Cleaned {count} stale obsidian-mcp run container(s).")
        if do_build:
            print("[OTTO] Building MCP containers...")
            build_result = subprocess.run(
                ["docker", "compose", "-f", "docker-compose.yml", "build", "obsidian-mcp"],
                cwd=self.root,
                check=False,
            )
            build_exit = build_result.returncode
            if build_exit != 0:
                print("[ERROR] MCP container build failed.")
                self.state.record_mcp_run(
                    mode="build_only" if build_only else ("container_ready" if ready_only else "stdio_run"),
                    vault_host=vault_host,
                    vault_path=vault_path,
                    build_exit=build_exit,
                    run_exit=build_exit,
                    notes=notes + ["build failed"],
                )
                return ActionResult(status="error", exit_code=build_exit, details={"build_exit": build_exit})

        if build_only:
            notes.append("build only")
            self.state.record_mcp_run(
                mode="build_only",
                vault_host=vault_host,
                vault_path=vault_path,
                build_exit=build_exit,
                run_exit=None,
                notes=notes,
            )
            print("[OTTO] Build complete. Exiting by --build-only.")
            return ActionResult(status="ok", exit_code=0, details={"build_exit": build_exit, "mode": "build_only"})

        CONTAINER_NAME = "ob-otto-obsidian-mcp"

        def _get_container_id(name: str) -> str | None:
            result = subprocess.run(
                ["docker", "ps", "-q", "-f", f"name={name}"],
                capture_output=True, text=True, check=False,
            )
            cid = result.stdout.strip()
            return cid if cid else None

        container_id = _get_container_id(CONTAINER_NAME)
        if not container_id:
            print("[OTTO] Starting detached obsidian-mcp container...")
            subprocess.run(
                ["docker", "compose", "-f", "docker-compose.yml", "--profile", "mcp", "up", "-d", "--no-recreate", "obsidian-mcp"],
                cwd=self.root, check=False,
            )
            container_id = _get_container_id(CONTAINER_NAME)
            if not container_id:
                print("[ERROR] Failed to start obsidian-mcp container.")
                return ActionResult(status="error", exit_code=1, details={"reason": "container-start-failed"})

        if ready_only:
            notes.append("container ready")
            self.state.record_mcp_run(
                mode="container_ready",
                vault_host=vault_host,
                vault_path=vault_path,
                build_exit=build_exit,
                run_exit=0,
                notes=notes,
            )
            print(f"[OTTO] {CONTAINER_NAME} is ready in Docker.")
            print("[OTTO] Use launch-mcp.bat only when an external client needs stdio attach.")
            return ActionResult(
                status="ok",
                exit_code=0,
                details={"build_exit": build_exit, "run_exit": 0, "mode": "container_ready"},
            )

        print(f"[OTTO] Attaching to {CONTAINER_NAME} via docker exec (stdio mode)...")
        # Use docker exec -i so OpenClaw can pipe stdio to the MCP server
        run_result = subprocess.Popen(
            ["docker", "exec", "-i", container_id, "node", "dist/index.js"],
            cwd=self.root,
        )
        run_exit = run_result.wait()
        self.state.record_mcp_run(
            mode="stdio_exec",
            vault_host=vault_host,
            vault_path=vault_path,
            build_exit=build_exit,
            run_exit=run_exit,
            notes=notes,
        )
        return ActionResult(
            status="ok" if run_exit == 0 else "error",
            exit_code=run_exit,
            details={"build_exit": build_exit, "run_exit": run_exit, "mode": "stdio_exec"},
        )

    def _action_brain(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        brain_args = list(args)
        if not brain_args and interactive:
            choice = input("Brain command [self-model/predictions/ritual/all]: ").strip()
            if choice:
                brain_args = [choice]
        if not brain_args:
            print("Usage: brain.bat [self-model | predictions | ritual | all]")
            return ActionResult(status="error", exit_code=1, details={"reason": "missing-brain-command"})
        if brain_args[0] in {"ritual", "all"}:
            print("[Otto] Brain ritual includes a full vault scan and can pause for 30-60s before the next log line.", flush=True)
            print("[Otto] That is expected unless it exceeds a couple of minutes.", flush=True)
        command = [sys.executable, "-m", "otto.brain_cli", *brain_args]
        result = subprocess.run(command, cwd=self.root, env=_runtime_env(self.root), check=False)
        print(f"[Otto] Brain command finished with exit code {result.returncode}.", flush=True)
        return ActionResult(
            status="ok" if result.returncode == 0 else "error",
            exit_code=result.returncode,
            details={"brain_args": brain_args},
        )

    def _action_sanity_check(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        script_args = list(args) if args else ["--write-report"]
        exit_code = self._run_python_script(SANITY_SCRIPT, args=script_args)
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={"args": script_args})

    def _action_metadata_enrich(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_python_script(METADATA_ENRICHMENT_SCRIPT, args=list(args))
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={"args": list(args)})

    def _action_notion_export_hygiene(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_python_script(NOTION_EXPORT_HYGIENE_SCRIPT, args=list(args))
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={"args": list(args)})

    def _action_docker_up(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        if not docker_available():
            print("[ERROR] Docker is not installed or not on PATH.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-found"})
        if not docker_daemon_running():
            print("[ERROR] Docker daemon is not running. Start Docker Desktop first.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-running"})
        compose_profiles = self._compose_profile_args()
        command = ["docker", "compose", "-f", "docker-compose.yml", *compose_profiles, "up", "-d"]
        result = subprocess.run(command, cwd=self.root, check=False)
        return ActionResult(
            status="ok" if result.returncode == 0 else "error",
            exit_code=result.returncode,
            details={"profiles": compose_profiles},
        )

    def _action_docker_clean(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        if not docker_available():
            print("[ERROR] Docker is not installed or not on PATH.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-found"})
        if not docker_daemon_running():
            print("[ERROR] Docker daemon is not running. Start Docker Desktop first.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-running"})
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.yml", "down", "-v", "--remove-orphans"],
            cwd=self.root,
            check=False,
        )
        stale_cleanup = cleanup_ephemeral_mcp_containers()
        if stale_cleanup.get("removed"):
            print(f"[Otto] Removed {len(stale_cleanup['removed'])} stale obsidian-mcp run container(s).")
        return ActionResult(
            status="ok" if result.returncode == 0 and stale_cleanup.get("ok", True) else "error",
            exit_code=result.returncode if result.returncode != 0 else (0 if stale_cleanup.get("ok", True) else 1),
            details={"ephemeral_mcp_cleanup": stale_cleanup},
        )

    def _action_mcp_clean(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        if not docker_available():
            print("[ERROR] Docker is not installed or not on PATH.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-found"})
        if not docker_daemon_running():
            print("[ERROR] Docker daemon is not running. Start Docker Desktop first.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-running"})
        result = cleanup_ephemeral_mcp_containers()
        removed = result.get("removed") or []
        if removed:
            print(f"[Otto] Removed {len(removed)} stale obsidian-mcp run container(s).")
        else:
            print("[Otto] No stale obsidian-mcp run containers found.")
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_postgres_repair(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        if not docker_available():
            print("[ERROR] Docker is not installed or not on PATH.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-found"})
        if not docker_daemon_running():
            print("[ERROR] Docker daemon is not running. Start Docker Desktop first.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-running"})
        up_result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.yml", "up", "-d", "postgres"],
            cwd=self.root,
            check=False,
        )
        if up_result.returncode != 0:
            return ActionResult(status="error", exit_code=up_result.returncode, details={"up_exit": up_result.returncode})
        restart_result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.yml", "restart", "postgres"],
            cwd=self.root,
            check=False,
        )
        status = "ok" if restart_result.returncode == 0 else "error"
        if status == "ok":
            print("[Otto] Postgres service restarted. Run `otto.bat status` to confirm reachability.")
        return ActionResult(
            status=status,
            exit_code=restart_result.returncode,
            details={"up_exit": up_result.returncode, "restart_exit": restart_result.returncode},
        )

    def _action_health_repair(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = run_health_repair(
            root=self.root,
            runtime_env=_runtime_env(self.root),
            fresh=False,
            scheduled="--scheduled" in args,
            ensure_runtime="--no-runtime" not in args,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_fresh_everything(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = run_health_repair(
            root=self.root,
            runtime_env=_runtime_env(self.root),
            fresh=True,
            scheduled="--scheduled" in args,
            ensure_runtime="--no-runtime" not in args,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("ok") else "error",
            exit_code=0 if result.get("ok") else 1,
            details=result,
        )

    def _action_install_health_automation(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_python_script(INSTALL_HEALTH_AUTOMATION_SCRIPT, args=args)
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={"args": list(args)})

    def _action_uninstall_health_automation(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_python_script(INSTALL_HEALTH_AUTOMATION_SCRIPT, args=["--uninstall", *args])
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={"args": list(args)})

    def _action_docker_probe(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        result = docker_probe_diagnostics()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return ActionResult(
            status="ok" if result.get("daemon_running") else "error",
            exit_code=0 if result.get("daemon_running") else 1,
            details=result,
        )


def run_launcher(screen: str = "home", *, once: str | None = None, extra_args: Sequence[str] | None = None) -> int:
    app = LauncherApp()
    if once:
        normalized = once.strip().lower().replace("_", "-")
        if normalized == "advanced":
            return app.run("advanced")
        result = app.run_action(normalized, screen=screen, interactive=True, extra_args=extra_args)
        return result.exit_code
    return app.run(screen)
