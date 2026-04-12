from __future__ import annotations

import shutil
import subprocess
from typing import Any

from .config import load_docker_config, repo_root


def docker_available() -> bool:
    return shutil.which("docker") is not None


def docker_compose_status() -> dict[str, Any]:
    if not docker_available():
        return {"available": False, "status": "docker-not-found", "services": []}
    cfg = load_docker_config()
    compose_file = repo_root() / str(cfg.get("compose_file", "docker-compose.yml"))
    if not compose_file.exists():
        return {"available": True, "status": "compose-file-missing", "services": []}

    # Try docker compose v2 first, then docker-compose v1 as fallback
    for cmd in (["docker", "compose", "-f", str(compose_file), "ps", "--format", "json"],
                ["docker-compose", "-f", str(compose_file), "ps", "--format", "json"]):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            continue
        if result.returncode != 0:
            continue
        services: list[dict[str, Any]] = []
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                try:
                    import json
                    services.append(json.loads(line))
                except Exception:
                    services.append({"raw": line})
        return {"available": True, "status": "ok", "services": services}

    return {"available": True, "status": "command-not-found", "services": []}
