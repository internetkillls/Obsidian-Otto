from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..config import load_paths, repo_root
from ..state import write_json
from .memory import retrieve


def _fixture_path(path: Path | None = None) -> Path:
    return path or (repo_root() / "tests" / "fixtures" / "retrieval_eval.yaml")


def _load_queries(path: Path | None = None) -> list[dict[str, Any]]:
    fixture = _fixture_path(path)
    if not fixture.exists():
        return []
    payload = yaml.safe_load(fixture.read_text(encoding="utf-8")) or {}
    return payload.get("test_queries", [])


def _normalize_eval_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lower()


def evaluate_retrieval(path: Path | None = None) -> dict[str, Any]:
    queries = _load_queries(path)
    paths = load_paths()
    report_path = paths.artifacts_root / "reports" / "retrieval_eval.json"
    if not queries:
        result = {"query_count": 0, "hit_rate_at_8": 0.0, "mrr": 0.0, "recall_at_8": 0.0}
        write_json(report_path, result)
        return result

    hit_count = 0
    recall_sum = 0.0
    reciprocal_rank_sum = 0.0
    details: list[dict[str, Any]] = []
    for query_case in queries:
        query = str(query_case.get("query", ""))
        relevant = [str(item) for item in query_case.get("relevant_paths", [])]
        relevant_normalized = {_normalize_eval_path(item) for item in relevant}
        package = retrieve(query=query, mode="fast")
        hits = [str(item.get("path", "")) for item in package.get("note_hits", [])[:8]]
        relevant_hits = [hit for hit in hits if _normalize_eval_path(hit) in relevant_normalized]
        if relevant_hits:
            hit_count += 1
            reciprocal_rank_sum += 1.0 / (hits.index(relevant_hits[0]) + 1)
        recall_sum += (len(relevant_hits) / len(relevant)) if relevant else 0.0
        details.append({
            "query": query,
            "hits": hits,
            "relevant_hits": relevant_hits,
        })

    result = {
        "query_count": len(queries),
        "hit_rate_at_8": hit_count / len(queries),
        "mrr": reciprocal_rank_sum / len(queries),
        "recall_at_8": recall_sum / len(queries),
        "details": details,
    }
    write_json(report_path, result)
    return result
