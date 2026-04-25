from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any


@dataclass(frozen=True)
class SchemaTarget:
    name: str
    backend: str
    tables: tuple[str, ...]


SCHEMA_TARGETS: tuple[SchemaTarget, ...] = (
    SchemaTarget("silver_notes", "sqlite", ("notes", "attachments", "folder_risk", "notes_fts")),
    SchemaTarget("events", "postgres", ("events", "vault_signals", "profiles")),
)


def schema_registry() -> list[dict[str, Any]]:
    return [
        {
            "name": target.name,
            "backend": target.backend,
            "tables": list(target.tables),
        }
        for target in SCHEMA_TARGETS
    ]


def schema_fingerprint() -> str:
    payload = json.dumps(schema_registry(), ensure_ascii=False, sort_keys=True)
    return sha256(payload.encode("utf-8")).hexdigest()
