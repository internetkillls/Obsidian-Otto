from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

from .config import load_docker_config, load_kairos_config, load_paths
from .db import init_pg_schema
from .infra import build_infra_result
from .logging_utils import get_logger
from .app.loop import run_loop as run_control_loop
from .state import OttoState


def _pid_file() -> Path:
    return load_paths().state_root / "pids" / "runtime.pid"


def write_pid() -> Path:
    path = _pid_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")
    return path


def clear_pid() -> None:
    path = _pid_file()
    if path.exists():
        path.unlink()


def _runtime_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src = str(root / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not existing else f"{src}{os.pathsep}{existing}"
    return env


MAX_CONSECUTIVE_FAILURES = 3
KAIROS_RETRY_SECONDS = 30

DOCKER_COMPOSE_FILE = "docker-compose.yml"


def bootstrap_docker_services(logger) -> dict[str, bool]:
    cfg = load_docker_config()
    infra = build_infra_result()
    if not cfg.get("enabled", False):
        logger.info("[runtime] Docker disabled in config/docker.yaml, skipping")
        return {}

    if not infra.docker_available:
        logger.warning("[runtime] Docker not available, skipping service bootstrap")
        return {}

    if not infra.daemon_running:
        logger.warning("[runtime] Docker daemon not running, skipping service bootstrap")
        return {}
    if infra.running_services:
        logger.info("[runtime] infra handler reports running services: %s", ",".join(infra.running_services))
    return {"infra_checked": True}


def run_loop() -> None:
    logger = get_logger("otto.runtime")
    paths = load_paths()
    state = OttoState.load()
    state.ensure()
    cfg = load_kairos_config()
    kairos_minutes = int(cfg.get("kairos", {}).get("heartbeat_minutes", 15))
    runtime_env = _runtime_env(paths.repo_root)

    write_pid()
    bootstrap_docker_services(logger)
    init_pg_schema()  # wire events to Postgres
    logger.info(f"[runtime] started pid={os.getpid()} kairos_minutes={kairos_minutes}")
    consecutive_failures = 0
    running = True

    def _sigterm_handler(signum, frame):
        nonlocal running
        logger.info("[runtime] SIGTERM received, shutting down gracefully")
        running = False

    signal.signal(signal.SIGTERM, _sigterm_handler)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    try:
        while running:
            try:
                result = run_control_loop(root=paths.repo_root, runtime_env=runtime_env, mode="heartbeat")
                consecutive_failures = 0
                executed_actions = [
                    str(item.get("action"))
                    for item in (result.get("executed") or [])
                    if isinstance(item, dict) and item.get("action")
                ]
                logger.info(
                    "[runtime] heartbeat decisions=%s executed=%s",
                    ",".join(result.get("decisions") or []) or "none",
                    ",".join(executed_actions) or "none",
                )
            except Exception as exc:
                consecutive_failures += 1
                logger.error(f"[runtime] heartbeat failed ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {exc}")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error("[runtime] max consecutive heartbeat failures reached, exiting")
                    break
                logger.info(f"[runtime] retrying heartbeat in {KAIROS_RETRY_SECONDS}s")
                time.sleep(KAIROS_RETRY_SECONDS)
                continue

            time.sleep(kairos_minutes * 60)
    finally:
        clear_pid()
        logger.info("[runtime] stopped")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Otto background runtime")
    parser.add_argument("--once", action="store_true", help="Run one kairos + dream cycle and exit")
    args = parser.parse_args(argv)

    if args.once:
        # Bootstrap Docker services even for one-shot runs
        _bootstrap_once()
        paths = load_paths()
        run_control_loop(root=paths.repo_root, runtime_env=_runtime_env(paths.repo_root), mode="heartbeat")
        return 0

    run_loop()
    return 0


def _bootstrap_once() -> None:
    """Run Docker + Postgres bootstrap without the full loop."""
    logger = get_logger("otto.runtime")
    bootstrap_docker_services(logger)
    init_pg_schema()


if __name__ == "__main__":
    raise SystemExit(main())
