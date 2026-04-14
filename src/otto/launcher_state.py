from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_docker_config, load_env_file, load_paths, repo_root
from .docker_utils import docker_available
from .state import now_iso, write_json


def venv_python_path(root: Path | None = None) -> Path:
    base = root or repo_root()
    windows = base / ".venv" / "Scripts" / "python.exe"
    posix = base / ".venv" / "bin" / "python"
    return windows if windows.exists() or not posix.exists() else posix


def venv_ready(root: Path | None = None) -> bool:
    return venv_python_path(root).exists()


def mcp_configured() -> bool:
    env = load_env_file(repo_root() / ".env")
    cfg = load_docker_config()
    services = cfg.get("services") or []
    return bool(cfg.get("enabled", False)) and "obsidian-mcp" in services and bool(env.get("OBSIDIAN_VAULT_HOST"))


def recommend_next_actions(
    runtime_status: str,
    *,
    screen: str,
    venv_is_ready: bool,
    docker_cli_is_available: bool,
    mcp_is_configured: bool,
) -> list[str]:
    actions: list[str] = []
    if not venv_is_ready:
        return ["Run initial.bat to bootstrap the virtual environment."]

    if runtime_status == "RUNNING":
        actions.extend(
            [
                "Open TUI for live monitoring.",
                "Run doctor checks if you want a quick health pass.",
                "Use reindex only for scoped refreshes.",
            ]
        )
    elif runtime_status == "STALE":
        actions.extend(
            [
                "Stop runtime to clear the stale PID file.",
                "Start runtime again after the stale PID is cleared.",
            ]
        )
    else:
        actions.extend(
            [
                "Start the background runtime.",
                "Check status before running heavier actions.",
            ]
        )

    if screen == "advanced":
        actions.append("Use sync-openclaw before debugging gateway behavior.")

    if docker_cli_is_available and mcp_is_configured:
        actions.append("Launch MCP when you need direct Obsidian tool access.")
    elif docker_cli_is_available:
        actions.append("MCP stays disabled until docker.yaml deployment is enabled.")
    else:
        actions.append("Start Docker Desktop before using docker or MCP actions.")

    return actions[:4]


class LauncherStateStore:
    def __init__(self, state_root: Path | None = None) -> None:
        self.paths = load_paths()
        self.state_root = state_root or self.paths.state_root
        self.launcher_root = self.state_root / "launcher"

    @property
    def current_path(self) -> Path:
        return self.launcher_root / "current.json"

    @property
    def last_action_path(self) -> Path:
        return self.launcher_root / "last_action.json"

    @property
    def mcp_last_run_path(self) -> Path:
        return self.launcher_root / "mcp_last_run.json"

    def write_current(
        self,
        *,
        screen: str,
        runtime_status: str,
        runtime_pid: int | None,
        venv_is_ready: bool | None = None,
        docker_cli_is_available: bool | None = None,
        mcp_is_configured: bool | None = None,
        recommended_next_actions: list[str] | None = None,
        vault_host_path: str | None = None,
    ) -> Path:
        if venv_is_ready is None:
            venv_is_ready = venv_ready(self.paths.repo_root)
        if docker_cli_is_available is None:
            docker_cli_is_available = docker_available()
        if mcp_is_configured is None:
            mcp_is_configured = mcp_configured()
        if recommended_next_actions is None:
            recommended_next_actions = recommend_next_actions(
                runtime_status,
                screen=screen,
                venv_is_ready=venv_is_ready,
                docker_cli_is_available=docker_cli_is_available,
                mcp_is_configured=mcp_is_configured,
            )
        if vault_host_path is None:
            vault_host_path = str(self.paths.vault_path) if self.paths.vault_path else None

        payload: dict[str, Any] = {
            "ts": now_iso(),
            "screen": screen,
            "runtime_status": runtime_status,
            "runtime_pid": runtime_pid,
            "venv_ready": venv_is_ready,
            "vault_host_path": vault_host_path,
            "docker_cli_available": docker_cli_is_available,
            "mcp_configured": mcp_is_configured,
            "recommended_next_actions": recommended_next_actions,
        }
        return write_json(self.current_path, payload)

    def record_action(
        self,
        *,
        action: str,
        screen: str,
        status: str,
        exit_code: int,
        duration_ms: int,
        details: dict[str, Any] | None = None,
    ) -> Path:
        payload = {
            "ts": now_iso(),
            "action": action,
            "screen": screen,
            "status": status,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "details": details or {},
        }
        return write_json(self.last_action_path, payload)

    def record_mcp_run(
        self,
        *,
        mode: str,
        vault_host: str | None,
        vault_path: str | None,
        build_exit: int | None,
        run_exit: int | None,
        notes: list[str] | None = None,
    ) -> Path:
        payload = {
            "ts": now_iso(),
            "mode": mode,
            "vault_host": vault_host,
            "vault_path": vault_path,
            "build_exit": build_exit,
            "run_exit": run_exit,
            "notes": notes or [],
        }
        return write_json(self.mcp_last_run_path, payload)
