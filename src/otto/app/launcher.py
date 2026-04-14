from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from ..config import load_docker_config, load_env_file, load_paths, repo_root
from ..docker_utils import docker_available, docker_daemon_running
from ..launcher_state import LauncherStateStore, mcp_configured
from ..state import read_json


RUNTIME_SCRIPT = Path("scripts/manage/runtime_loop.py")
SANITY_SCRIPT = Path("scripts/manage/sanity_check.py")
STATUS_SCRIPT = Path("scripts/manage/status_report.py")
TUI_SCRIPT = Path("scripts/manage/run_tui.py")
PIPELINE_SCRIPT = Path("scripts/manage/run_pipeline.py")
QUERY_SCRIPT = Path("scripts/manage/query_memory.py")
DREAM_SCRIPT = Path("scripts/manage/run_dream.py")
KAIROS_SCRIPT = Path("scripts/manage/run_kairos.py")
SYNC_OPENCLAW_SCRIPT = Path("scripts/manage/sync_openclaw_config.py")


@dataclass
class RuntimeSnapshot:
    status: str
    pid: int | None


@dataclass
class ActionResult:
    status: str
    exit_code: int
    details: dict[str, object]
    next_screen: str | None = None


def runtime_pid_file(root: Path | None = None) -> Path:
    base = root or repo_root()
    return base / "state" / "pids" / "runtime.pid"


def _windows_process_running(pid: int) -> bool:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty ProcessName",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    output = result.stdout.lower().strip()
    if result.returncode != 0 or not output:
        return False
    return output in {"python", "pythonw", "python.exe", "pythonw.exe"}


def _generic_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def classify_runtime(
    pid_path: Path | None = None,
    *,
    process_checker: Callable[[int], bool] | None = None,
) -> RuntimeSnapshot:
    path = pid_path or runtime_pid_file()
    if not path.exists():
        return RuntimeSnapshot(status="STOPPED", pid=None)

    raw_pid = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw_pid:
        return RuntimeSnapshot(status="STALE", pid=None)

    try:
        pid = int(raw_pid)
    except ValueError:
        return RuntimeSnapshot(status="STALE", pid=None)

    checker = process_checker
    if checker is None:
        checker = _windows_process_running if os.name == "nt" else _generic_process_running
    return RuntimeSnapshot(status="RUNNING" if checker(pid) else "STALE", pid=pid)


def clear_stale_runtime_pid(pid_path: Path | None = None) -> None:
    path = pid_path or runtime_pid_file()
    if path.exists():
        path.unlink()


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

    def run(self, screen: str = "home") -> int:
        current_screen = screen
        while True:
            snapshot = self.write_current(current_screen)
            self._render_screen(current_screen, snapshot)
            choice = input("Select [1-9]: ").strip()
            action = self._resolve_choice(current_screen, choice)
            if action is None:
                print("[WARN] Invalid selection. Use 1-9.")
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
        action_name = self._normalize_action_name(action)
        args = list(extra_args or [])

        if action_name == "advanced":
            return ActionResult(status="ok", exit_code=0, details={}, next_screen="advanced")

        handlers = {
            "initial": self._action_initial,
            "start": self._action_start,
            "stop": self._action_stop,
            "status": self._action_status,
            "doctor": self._action_doctor,
            "tui": self._action_tui,
            "reindex": self._action_reindex,
            "query": self._action_query,
            "kairos": self._action_kairos,
            "dream": self._action_dream,
            "sync-openclaw": self._action_sync_openclaw,
            "launch-mcp": self._action_launch_mcp,
            "brain": self._action_brain,
            "docker-up": self._action_docker_up,
            "docker-clean": self._action_docker_clean,
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

    def _screen_menu(self, screen: str) -> list[tuple[str, str]]:
        if screen == "advanced":
            return [
                ("1", "Run KAIROS once"),
                ("2", "Run Dream once"),
                ("3", "Query memory"),
                ("4", "Sync OpenClaw config"),
                ("5", "Launch obsidian-mcp"),
                ("6", "Run Brain CLI"),
                ("7", "Bring up Docker stack"),
                ("8", "Clean Docker stack"),
                ("9", "Back to home"),
            ]
        return [
            ("1", "Run initial setup"),
            ("2", "Start runtime loop"),
            ("3", "Stop runtime loop"),
            ("4", "Open live TUI"),
            ("5", "Show status report"),
            ("6", "Run reindex pipeline"),
            ("7", "Doctor checks"),
            ("8", "Open advanced tools"),
            ("9", "Exit launcher"),
        ]

    def _resolve_choice(self, screen: str, choice: str) -> str | None:
        if screen == "advanced":
            mapping = {
                "1": "kairos",
                "2": "dream",
                "3": "query",
                "4": "sync-openclaw",
                "5": "launch-mcp",
                "6": "brain",
                "7": "docker-up",
                "8": "docker-clean",
                "9": "back",
            }
        else:
            mapping = {
                "1": "initial",
                "2": "start",
                "3": "stop",
                "4": "tui",
                "5": "status",
                "6": "reindex",
                "7": "doctor",
                "8": "advanced",
                "9": "exit",
            }
        return mapping.get(choice)

    def _normalize_action_name(self, action: str) -> str:
        return action.strip().lower().replace("_", "-")

    def _run_python_script(self, script: Path, args: Sequence[str] | None = None) -> int:
        command = [sys.executable, str(self.root / script), *(args or [])]
        result = subprocess.run(command, cwd=self.root, env=_runtime_env(self.root), check=False)
        return result.returncode

    def _run_batch_script(self, name: str, args: Sequence[str] | None = None) -> int:
        command = ["cmd", "/c", name, *(args or [])]
        result = subprocess.run(command, cwd=self.root, check=False)
        return result.returncode

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
            print(f"[Otto] Runtime started. PID {confirmed.pid}.")
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
        exit_code = self._run_python_script(STATUS_SCRIPT, args=["--json"])
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={})

    def _action_doctor(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        snapshot = self.runtime_snapshot()
        print("=== Obsidian-Otto Doctor ===")
        print("Runtime: " + snapshot.status + (f" (PID {snapshot.pid})" if snapshot.pid else ""))
        print()
        status_exit = self._run_python_script(STATUS_SCRIPT, args=["--json"])
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

    def _action_tui(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        exit_code = self._run_python_script(TUI_SCRIPT, args=["--refresh-seconds", "2"])
        return ActionResult(status="ok" if exit_code == 0 else "error", exit_code=exit_code, details={})

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

    def _action_launch_mcp(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        normalized = list(args)
        if "--help" in normalized:
            print("Usage: launch-mcp.bat [--build-only] [--no-build]")
            print("  --build-only  Build obsidian-mcp image and exit.")
            print("  --no-build    Skip docker compose build and run directly.")
            return ActionResult(status="ok", exit_code=0, details={"help_shown": True})

        do_build = "--no-build" not in normalized
        build_only = "--build-only" in normalized
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
                    mode="build_only" if build_only else "stdio_run",
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
                mode="build_only" if build_only else "stdio_run",
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
                mode="build_only" if build_only else "stdio_run",
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
                mode="build_only" if build_only else "stdio_run",
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
                mode="build_only" if build_only else "stdio_run",
                vault_host=vault_host,
                vault_path=vault_path,
                build_exit=None,
                run_exit=1,
                notes=notes + ["vault host path missing"],
            )
            return ActionResult(status="error", exit_code=1, details={"reason": "missing-vault-path"})

        build_exit: int | None = None
        run_exit: int | None = None
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
                    mode="build_only" if build_only else "stdio_run",
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

        print("[OTTO] Starting obsidian-mcp (foreground stdio)...")
        run_result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.yml",
                "run",
                "--rm",
                "-e",
                f"OBSIDIAN_VAULT_PATH={vault_path}",
                "-v",
                f"{vault_host}:{vault_path}:ro",
                "obsidian-mcp",
            ],
            cwd=self.root,
            check=False,
        )
        run_exit = run_result.returncode
        self.state.record_mcp_run(
            mode="stdio_run",
            vault_host=vault_host,
            vault_path=vault_path,
            build_exit=build_exit,
            run_exit=run_exit,
            notes=notes,
        )
        return ActionResult(
            status="ok" if run_exit == 0 else "error",
            exit_code=run_exit,
            details={"build_exit": build_exit, "run_exit": run_exit, "mode": "stdio_run"},
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
        command = [sys.executable, "-m", "otto.brain_cli", *brain_args]
        result = subprocess.run(command, cwd=self.root, env=_runtime_env(self.root), check=False)
        return ActionResult(
            status="ok" if result.returncode == 0 else "error",
            exit_code=result.returncode,
            details={"brain_args": brain_args},
        )

    def _action_docker_up(self, *, args: Sequence[str], interactive: bool) -> ActionResult:
        if not docker_available():
            print("[ERROR] Docker is not installed or not on PATH.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-found"})
        if not docker_daemon_running():
            print("[ERROR] Docker daemon is not running. Start Docker Desktop first.")
            return ActionResult(status="error", exit_code=1, details={"reason": "docker-not-running"})
        result = subprocess.run(["docker", "compose", "-f", "docker-compose.yml", "up", "-d"], cwd=self.root, check=False)
        return ActionResult(status="ok" if result.returncode == 0 else "error", exit_code=result.returncode, details={})

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
        return ActionResult(status="ok" if result.returncode == 0 else "error", exit_code=result.returncode, details={})


def run_launcher(screen: str = "home", *, once: str | None = None, extra_args: Sequence[str] | None = None) -> int:
    app = LauncherApp()
    if once:
        normalized = once.strip().lower().replace("_", "-")
        if normalized == "advanced":
            return app.run("advanced")
        result = app.run_action(normalized, screen=screen, interactive=True, extra_args=extra_args)
        return result.exit_code
    return app.run(screen)
