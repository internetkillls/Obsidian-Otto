from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

from .config import load_kairos_config, load_paths
from .logging_utils import get_logger
from .orchestration.dream import run_dream_once
from .orchestration.kairos import run_kairos_once
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


MAX_CONSECUTIVE_FAILURES = 3
KAIROS_RETRY_SECONDS = 30


def run_loop() -> None:
    logger = get_logger("otto.runtime")
    state = OttoState.load()
    state.ensure()
    cfg = load_kairos_config()
    kairos_minutes = int(cfg.get("kairos", {}).get("heartbeat_minutes", 15))
    dream_minutes = max(15, kairos_minutes * 2)

    write_pid()
    logger.info(f"[runtime] started pid={os.getpid()} kairos_minutes={kairos_minutes}")
    last_dream = 0.0
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
                run_kairos_once()
                consecutive_failures = 0
            except Exception as exc:
                consecutive_failures += 1
                logger.error(f"[runtime] kairos failed ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {exc}")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.error("[runtime] max consecutive kairos failures reached, exiting")
                    break
                logger.info(f"[runtime] retrying kairos in {KAIROS_RETRY_SECONDS}s")
                time.sleep(KAIROS_RETRY_SECONDS)
                continue

            now = time.time()
            if now - last_dream >= dream_minutes * 60:
                try:
                    run_dream_once()
                    last_dream = now
                except Exception as exc:
                    logger.warning(f"[runtime] dream failed: {exc}, continuing loop")

            time.sleep(kairos_minutes * 60)
    finally:
        clear_pid()
        logger.info("[runtime] stopped")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Otto background runtime")
    parser.add_argument("--once", action="store_true", help="Run one kairos + dream cycle and exit")
    args = parser.parse_args(argv)

    if args.once:
        run_kairos_once()
        run_dream_once()
        return 0

    run_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
