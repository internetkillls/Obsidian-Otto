from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityRef:
    raw: str

    @property
    def value(self) -> str:
        return self.raw.strip()
