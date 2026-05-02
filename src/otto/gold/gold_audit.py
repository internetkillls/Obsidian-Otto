from __future__ import annotations

from pathlib import Path

from ..corridor import ensure_jsonl_row
from ..config import load_paths
from ..governance_utils import public_result, read_json, read_jsonl, state_root
from .gold_policy import qmd_state_allowed


def gold_audit_path() -> Path:
    return state_root() / "gold" / "gold_audit.jsonl"


def _rehab_path_active(review_needed: list[dict[str, object]], discuss_later: list[dict[str, object]]) -> bool:
    """Gold=0 is acceptable when a rehabilitation corridor can still produce reviewable value."""
    rehab_root = state_root() / "gold_rehab"
    patch_ledger_exists = (rehab_root / "patch_ledger.jsonl").exists()
    queued_review_exists = bool(review_needed) or bool(discuss_later)
    corpus_audit = read_json(rehab_root / "corpus_audit.json", default={})
    corpus_has_notes = int(corpus_audit.get("note_count") or 0) > 0 if isinstance(corpus_audit, dict) else False
    sqlite_corpus_available = load_paths().sqlite_path.exists()
    rehab_code_available = (Path(__file__).parents[1] / "gold_rehab" / "corpus_audit.py").exists()
    return any(
        [
            patch_ledger_exists,
            queued_review_exists,
            corpus_has_notes,
            sqlite_corpus_available and rehab_code_available,
        ]
    )


def build_gold_audit() -> dict[str, object]:
    gold_rows = read_jsonl(state_root() / "gold" / "gold_index.jsonl")
    feature_rows = read_jsonl(state_root() / "features" / "feature_vectors.jsonl")
    candidate_rows = read_jsonl(state_root() / "enrichment" / "candidate_insights.jsonl")
    review_needed = read_jsonl(state_root() / "gold_rehab" / "review_needed.jsonl")
    discuss_later = read_jsonl(state_root() / "gold_rehab" / "discuss_later.jsonl")
    failures: list[str] = []
    if any(bool(row.get("qmd_index_allowed")) for row in feature_rows):
        failures.append("feature_vectors_are_qmd_indexed")
    if any(bool(row.get("qmd_index_allowed")) for row in candidate_rows):
        failures.append("candidates_are_qmd_indexed")
    for row in gold_rows:
        if not row.get("evidence_refs"):
            failures.append("gold_lacks_evidence_refs")
        if not row.get("review_id"):
            failures.append("gold_lacks_review_id")
        if not qmd_state_allowed(str(row.get("state") or "")):
            failures.append("gold_state_not_qmd_allowed")
    rehab_active = _rehab_path_active(review_needed, discuss_later)
    ok = not failures and (bool(gold_rows) or rehab_active)
    result = {
        "ok": ok,
        "gold_count": len(gold_rows),
        "feature_vector_count": len(feature_rows),
        "candidate_count": len(candidate_rows),
        "rehab_active": rehab_active,
        "failures": failures,
    }
    ensure_jsonl_row(gold_audit_path(), result)
    return public_result(ok, audit=result)
