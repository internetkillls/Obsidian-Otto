from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ...config import load_paths
from ...core.evidence import EvidenceRef, RetrievalHit
from ...memory.source_registry import iter_sources
from ...state import now_iso


def _resolve_result_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    vault_path = load_paths().vault_path
    if vault_path is not None:
        return vault_path / raw_path
    return load_paths().repo_root / raw_path


def _infer_source_id(path: Path, fallback: str | None = None) -> str:
    path_text = str(path).replace("\\", "/")
    best: tuple[int, str] | None = None
    for source in iter_sources():
        for candidate in (source.path_wsl, source.path_windows):
            normalized = candidate.replace("\\", "/")
            if path_text.startswith(normalized):
                score = len(normalized)
                if best is None or score > best[0]:
                    best = (score, source.id)
    return best[1] if best else (fallback or "qmd")


def _hit_id(query: str, path: str, snippet: str) -> str:
    digest = hashlib.sha256(f"{query}\n{path}\n{snippet}".encode("utf-8", errors="replace")).hexdigest()
    return f"qmd_{digest[:16]}"


def normalize_openclaw_memory_results(query: str, payload: dict[str, Any]) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    captured_at = now_iso()
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "")
        snippet = str(item.get("snippet") or "")
        if not raw_path and not snippet:
            continue
        resolved_path = _resolve_result_path(raw_path)
        source_id = _infer_source_id(resolved_path, str(item.get("source") or "qmd"))
        evidence = EvidenceRef(
            evidence_id=_hit_id(query, str(resolved_path), snippet),
            source_id=source_id,
            uri=f"file://{str(resolved_path).replace(chr(92), '/')}",
            captured_at=captured_at,
            privacy_class="private",
            confidence=1.0,
        )
        title = resolved_path.stem if resolved_path.name else None
        score: float | None
        try:
            score = float(item["score"]) if item.get("score") is not None else None
        except (TypeError, ValueError):
            score = None
        hits.append(
            RetrievalHit(
                hit_id=evidence.evidence_id,
                source_id=source_id,
                path=str(resolved_path),
                title=title,
                snippet=snippet,
                score=score,
                evidence=evidence,
            )
        )
    return hits


def qmd_search(query: str, *, max_results: int = 5, timeout_seconds: int = 60) -> dict[str, Any]:
    openclaw = shutil.which("openclaw")
    if not openclaw:
        return {
            "ok": False,
            "query": query,
            "reason": "openclaw-missing",
            "hits": [],
        }
    try:
        proc = subprocess.run(
            [openclaw, "memory", "search", query, "--max-results", str(max_results), "--json"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "query": query,
            "reason": "timeout",
            "hits": [],
            "timeout_seconds": timeout_seconds,
        }
    if proc.returncode != 0:
        return {
            "ok": False,
            "query": query,
            "reason": "command-failed",
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
            "hits": [],
        }
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "query": query,
            "reason": "json-parse-failed",
            "error": str(exc),
            "stdout": (proc.stdout or "").strip(),
            "hits": [],
        }
    hits = normalize_openclaw_memory_results(query, payload if isinstance(payload, dict) else {})
    return {
        "ok": True,
        "query": query,
        "hit_count": len(hits),
        "hits": [hit.to_dict() for hit in hits],
    }
