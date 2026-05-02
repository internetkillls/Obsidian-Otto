from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from .config import load_docker_config, load_postgres_config
from .docker_utils import classify_docker_probe_error, docker_available, docker_daemon_running, run_docker_command


@dataclass
class InfraResult:
    docker_available: bool
    daemon_running: bool
    running_services_known: bool
    configured_services: list[str]
    running_services: list[str]
    docker_probe_status: str
    docker_probe_transport: str
    docker_probe_error: str | None
    postgres_reachable: bool
    mcp_reachable: bool
    next_safe_action: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _running_container_names() -> tuple[set[str] | None, str | None, str]:
    probe = run_docker_command(["ps", "--format", "{{.Names}}"], timeout=5)
    if not probe.get("ok"):
        error = (probe.get("stderr") or probe.get("stdout") or "").strip() or None
        return None, error, str(probe.get("transport") or "none")
    names = {line.strip() for line in str(probe.get("stdout") or "").splitlines() if line.strip()}
    return names, None, str(probe.get("transport") or "direct")


def _container_name_for_service(service: str) -> str:
    if service.startswith("otto-"):
        return f"ob-{service}"
    return f"ob-otto-{service}"


def _postgres_reachable() -> bool:
    cfg = load_postgres_config()
    try:
        result = subprocess.run(
            [
                "python",
                "-c",
                "import socket,sys; s=socket.socket(); s.settimeout(1); s.connect((sys.argv[1], int(sys.argv[2]))); s.close()",
                str(cfg.get("host", "localhost")),
                str(cfg.get("port", 54329)),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def build_infra_result() -> InfraResult:
    cfg = load_docker_config()
    services = list(cfg.get("services") or [])
    docker_ok = docker_available()
    daemon_ok = docker_daemon_running()
    running_names: set[str] | None = None
    probe_error: str | None = None
    probe_transport = "none"
    if docker_ok:
        running_names, probe_error, probe_transport = _running_container_names()
        if running_names is not None:
            daemon_ok = True

    running_known = running_names is not None
    probe_status = "ok" if running_known else classify_docker_probe_error(probe_error)
    running = [
        svc
        for svc in services
        if running_names is not None and _container_name_for_service(svc) in running_names
    ]
    postgres_ok = _postgres_reachable()
    mcp_ok = "obsidian-mcp" in running
    if docker_ok and daemon_ok and running_known and not postgres_ok and "postgres" in services:
        next_action = "postgres-repair"
    elif docker_ok and daemon_ok and running_known and len(running) < len(services):
        next_action = "docker-up"
    else:
        next_action = "status"
    return InfraResult(
        docker_available=docker_ok,
        daemon_running=daemon_ok,
        running_services_known=running_known,
        configured_services=services,
        running_services=running,
        docker_probe_status=probe_status,
        docker_probe_transport=probe_transport,
        docker_probe_error=probe_error,
        postgres_reachable=postgres_ok,
        mcp_reachable=mcp_ok,
        next_safe_action=next_action,
    )
