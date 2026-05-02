from __future__ import annotations

from typing import Any


def evaluate_training_export_gate(gold: dict[str, Any]) -> dict[str, Any]:
    blocked: list[str] = []
    if gold.get("state") != "GOLD":
        blocked.append("training_requires_gold_state")
    if not gold.get("training_eligible"):
        blocked.append("training_eligible_false")
    if not gold.get("contains_no_secret", True):
        blocked.append("contains_secret")
    if not gold.get("contains_no_unreviewed_profile_claim", True):
        blocked.append("contains_unreviewed_profile_claim")
    if not gold.get("contains_no_clinical_claim", True):
        blocked.append("contains_clinical_claim")
    if not gold.get("has_clear_instruction_output_shape", True):
        blocked.append("missing_instruction_output_shape")
    if not gold.get("has_artifact_or_decision_value", True):
        blocked.append("missing_artifact_or_decision_value")
    if not gold.get("not_overfit_to_raw_private_context", True):
        blocked.append("overfit_to_raw_private_context")
    return {"ok": not blocked, "export_allowed": not blocked, "blocked_reasons": blocked}
