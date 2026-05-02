from __future__ import annotations

from pathlib import Path
from typing import Any

from ..governance_utils import ensure_json, state_root


DEFAULT_SUPPORT_CONTEXT: dict[str, Any] = {
    "context_id": "ctx_audhd_bd_001",
    "state": "DECLARED_CONTEXT",
    "labels": ["AuDHD", "BD"],
    "source": "user_declared",
    "clinical_verification": "not_stored",
    "use_as": "support_context_not_diagnosis",
    "allowed_uses": [
        "prompt design",
        "scope guardrails",
        "reentry anchors",
        "overload prevention",
        "energy rhythm awareness",
    ],
    "blocked_uses": ["diagnosis", "medical advice", "automatic risk scoring", "identity reduction"],
}


def support_context_path() -> Path:
    return state_root() / "profile" / "support_context.json"


def load_support_context() -> dict[str, Any]:
    return ensure_json(support_context_path(), DEFAULT_SUPPORT_CONTEXT)
