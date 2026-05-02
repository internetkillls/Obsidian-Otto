from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Relation:
    subject: str
    predicate: str
    object: str
