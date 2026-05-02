from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from rich.logging import RichHandler
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    class RichHandler(logging.StreamHandler):  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            super().__init__()

from .config import load_paths


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, Path)):
        return str(value)
    return repr(value)


def get_logger(name: str) -> logging.Logger:
    paths = load_paths()
    log_dir = paths.logs_root / "app"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    rich_handler = RichHandler(rich_tracebacks=True, show_path=False)
    rich_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(rich_handler)

    from logging.handlers import RotatingFileHandler

    file_handler = RotatingFileHandler(
        log_dir / "otto.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(file_handler)

    return logger


MAX_JSONL_LINES = 10000


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=_json_default) + "\n")

    # Rotate if file exceeds MAX_JSONL_LINES — keep the most recent lines
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) > MAX_JSONL_LINES:
            trimmed = lines[-MAX_JSONL_LINES:]
            path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
    except OSError:
        pass  # Best-effort rotation — don't fail writes due to rotation errors
