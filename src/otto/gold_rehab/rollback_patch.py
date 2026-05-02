from __future__ import annotations

from ..governance_utils import public_result
from .patch_ledger import load_patch


def rollback_patch_dry_run(patch_id: str) -> dict[str, object]:
    patch = load_patch(patch_id)
    if not patch:
        return public_result(False, reason="patch-id-not-found", patch_id=patch_id)
    return public_result(
        True,
        dry_run=True,
        reversible=bool(patch.get("reversible")),
        path=patch.get("path"),
        rollback_hint=patch.get("rollback_hint"),
    )
