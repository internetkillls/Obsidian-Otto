from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TrainingCandidate:
    training_item_id: str
    from_gold_id: str
    task_type: str
    input: dict[str, Any]
    output: dict[str, Any]
    risk: dict[str, bool]
    export_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "training_item_id": self.training_item_id,
            "from_gold_id": self.from_gold_id,
            "task_type": self.task_type,
            "input": self.input,
            "output": self.output,
            "risk": self.risk,
            "export_allowed": self.export_allowed,
        }
