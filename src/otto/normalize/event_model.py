from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SilverEvent:
    event_id: str
    state: str
    source_id: str
    source_ref: str
    kind: str
    time: dict[str, Any]
    actor: str
    content_unit: dict[str, Any]
    entities: list[str] = field(default_factory=list)
    relations: list[dict[str, str]] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    privacy: str = "private"
    qmd_index_allowed: bool = False
    vault_writeback_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "state": self.state,
            "source_id": self.source_id,
            "source_ref": self.source_ref,
            "kind": self.kind,
            "time": self.time,
            "actor": self.actor,
            "content_unit": self.content_unit,
            "entities": self.entities,
            "relations": self.relations,
            "evidence_refs": self.evidence_refs,
            "privacy": self.privacy,
            "qmd_index_allowed": self.qmd_index_allowed,
            "vault_writeback_allowed": self.vault_writeback_allowed,
        }
