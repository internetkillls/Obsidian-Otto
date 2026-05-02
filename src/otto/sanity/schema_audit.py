from __future__ import annotations

from typing import Any

from .invariants import load_invariant_registry, load_sanity_policy, result_shape


def run_schema_audit() -> dict[str, Any]:
    policy = load_sanity_policy()
    registry = load_invariant_registry()
    blockers = []
    if policy.get("mode") != "fail_closed":
        blockers.append({"problem": "sanity_policy_not_fail_closed"})
    if registry.get("version") != 1 or not registry.get("invariants"):
        blockers.append({"problem": "invariant_registry_missing"})
    return result_shape(
        ok=not blockers,
        state_changed=False,
        blockers=blockers,
        next_required_action="fix_sanity_policy_or_registry" if blockers else None,
        policy=policy,
        invariant_registry=registry,
    )
