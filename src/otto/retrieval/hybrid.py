from __future__ import annotations

from typing import Any


def reciprocal_rank_fusion(results_lists: list[list[dict[str, Any]]], k: int = 60) -> list[dict[str, Any]]:
    fused: dict[str, dict[str, Any]] = {}
    for results in results_lists:
        for rank, item in enumerate(results):
            doc_id = str(item.get("path") or item.get("id") or "")
            if not doc_id:
                continue
            current = fused.setdefault(doc_id, {**item, "rrf_score": 0.0, "sources": [], "source_rrf": {}})
            contribution = 1.0 / (k + rank + 1)
            current["rrf_score"] += contribution
            source = item.get("source")
            if source and source not in current["sources"]:
                current["sources"].append(source)
            if source:
                normalized_source = str(source).strip().lower()
                current["source_rrf"][normalized_source] = float(current["source_rrf"].get(normalized_source, 0.0) or 0.0) + contribution
    return sorted(fused.values(), key=lambda item: (-item["rrf_score"], str(item.get("path", ""))))
