from __future__ import annotations

from pathlib import Path

from ..corridor import ensure_jsonl_row
from ..governance_utils import make_id, public_result, read_jsonl, state_root
from ..state import write_json
from .training_candidate import TrainingCandidate
from .training_redaction import contains_secret_like_text
from .training_task_builder import build_task_shape


def training_candidates_path() -> Path:
    return state_root() / "training" / "training_candidates.jsonl"


def training_export_queue_path() -> Path:
    return state_root() / "training" / "training_export_queue.jsonl"


def rejected_training_items_path() -> Path:
    return state_root() / "training" / "rejected_training_items.jsonl"


def training_dataset_manifest_path() -> Path:
    return state_root() / "training" / "training_dataset_manifest.json"


def build_training_candidates() -> dict[str, object]:
    items: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    for gold in read_jsonl(state_root() / "gold" / "gold_index.jsonl"):
        text = str(gold.get("claim") or gold.get("why_it_matters") or "")
        if not gold.get("training_export_allowed"):
            rejected.append({"gold_id": gold.get("gold_id"), "reason": "training_export_not_allowed"})
            continue
        if contains_secret_like_text(text):
            rejected.append({"gold_id": gold.get("gold_id"), "reason": "contains_secret_like_text"})
            continue
        task_type, output = build_task_shape(gold)
        candidate = TrainingCandidate(
            training_item_id=make_id("train"),
            from_gold_id=str(gold.get("gold_id")),
            task_type=task_type,
            input={
                "user_need": str(gold.get("claim") or ""),
                "topic": str(gold.get("kind") or ""),
            },
            output=output,
            risk={
                "contains_private_raw": False,
                "contains_clinical_claim": False,
                "contains_secret": False,
            },
            export_allowed=True,
        )
        items.append(candidate.to_dict())
    for item in items:
        ensure_jsonl_row(training_candidates_path(), item)
        ensure_jsonl_row(training_export_queue_path(), item)
    for item in rejected:
        ensure_jsonl_row(rejected_training_items_path(), item)
    return public_result(True, training_candidates=items, rejected=rejected)


def build_training_manifest() -> dict[str, object]:
    queue = read_jsonl(training_export_queue_path())
    manifest = {
        "generated_at": __import__("otto.state", fromlist=["now_iso"]).now_iso(),
        "item_count": len(queue),
        "items": queue,
    }
    write_json(training_dataset_manifest_path(), manifest)
    return public_result(True, manifest=manifest)
