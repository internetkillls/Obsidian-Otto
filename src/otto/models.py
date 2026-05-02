from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import load_models


@dataclass
class ModelChoice:
    task_class: str
    model: str
    effort: str
    reason: str


def choose_model(task_class: str) -> ModelChoice:
    cfg = load_models()
    tasks: dict[str, Any] = cfg.get("tasks", {})
    item = tasks.get(task_class) or tasks.get("first_query_handler", {})
    model_name = item.get("model") if item else None
    if model_name is None:
        get_logger("otto.models").warning(
            f"choose_model('{task_class}'): no config found, falling back to gpt-5.4-mini. "
            "Check config/models.yaml"
        )
    return ModelChoice(
        task_class=task_class,
        model=str(model_name or "gpt-5.4-mini"),
        effort=str(item.get("effort", "low") if item else "low"),
        reason=str(item.get("reason", "default route") if item else "default route"),
    )


def model_matrix() -> list[dict[str, str]]:
    cfg = load_models()
    rows: list[dict[str, str]] = []
    for task, item in (cfg.get("tasks") or {}).items():
        rows.append(
            {
                "task": task,
                "model": str(item.get("model", "")),
                "effort": str(item.get("effort", "")),
                "reason": str(item.get("reason", "")),
            }
        )
    return rows
