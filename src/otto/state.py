from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .config import load_paths


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return str(value)


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    return path


@dataclass
class OttoState:
    paths: Any

    @classmethod
    def load(cls) -> "OttoState":
        return cls(paths=load_paths())

    @property
    def handoff_latest(self) -> Path:
        return self.paths.state_root / "handoff" / "latest.json"

    @property
    def checkpoints(self) -> Path:
        return self.paths.state_root / "checkpoints" / "pipeline.json"

    @property
    def run_journal(self) -> Path:
        return self.paths.state_root / "run_journal"

    @property
    def kairos(self) -> Path:
        return self.paths.state_root / "kairos" / "heartbeat.jsonl"

    @property
    def dream(self) -> Path:
        return self.paths.state_root / "dream" / "dream_state.json"

    def ensure(self) -> None:
        for path in [
            self.paths.state_root / "handoff",
            self.paths.state_root / "retrieval_state",
            self.paths.state_root / "retrieval",
            self.paths.state_root / "run_journal",
            self.paths.state_root / "checkpoints",
            self.paths.state_root / "pids",
            self.paths.state_root / "kairos",
            self.paths.state_root / "dream",
            self.paths.state_root / "bootstrap",
            self.paths.state_root / "openclaw",
        ]:
            path.mkdir(parents=True, exist_ok=True)
