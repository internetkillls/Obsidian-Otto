from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_paths
from ..state import now_iso, read_json, write_json
from .morpheus import MorpheusEnrichment

BRIDGE_CONTRACT_VERSION = 1
BRIDGE_MODE = "investigate-first"
BRIDGE_READY_STATUSES = ["reviewed", "verified"]
FORBIDDEN_DREAMING_SOURCES = [
    "memory/.dreams/session-corpus",
    "System (untrusted)",
    "HEARTBEAT_OK",
    "exec completion noise",
    "inline dreaming markers in memory/YYYY-MM-DD.md",
]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(value)
    return result


def _vector_basis(paths: Any) -> dict[str, Any]:
    summary = read_json(paths.artifacts_root / "reports" / "vector_summary.json", default={}) or {}
    enabled = bool(summary.get("enabled", False))
    return {
        "semantic_body_required": True,
        "markdown_body_required": True,
        "frontmatter_only_forbidden": True,
        "vector_cache_live": enabled,
        "vector_note": summary.get("note") or ("vector cache available" if enabled else "vector cache not live"),
    }


def _vault_material_refs(vault_materials: list[Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for material in vault_materials[:6]:
        refs.append(
            {
                "area": str(getattr(material, "area", "") or ""),
                "source_path": str(getattr(material, "source_path", "") or ""),
                "mtime": str(getattr(material, "mtime", "") or ""),
            }
        )
    return refs


def _candidate(
    *,
    candidate_id: str,
    kind: str,
    summary: str,
    confidence: float,
    source_signals: list[str],
    investigation_queries: list[str],
) -> dict[str, Any]:
    return {
        "id": candidate_id,
        "kind": kind,
        "status": "hypothesis",
        "summary": summary,
        "confidence": round(confidence, 2),
        "ready_for_openclaw_dreaming": False,
        "promotion_blocked_until": BRIDGE_READY_STATUSES,
        "source_signals": _dedupe_preserve_order(source_signals)[:6],
        "evidence_needed": [
            "semantic retrieval over markdown body, not frontmatter alone",
            "cross-check with recent vault notes and scoped retrieval hits",
            "human or Otto review before promotion into durable memory",
        ],
        "investigation_queries": _dedupe_preserve_order(investigation_queries)[:4],
    }


def _build_candidates(
    *,
    enrichment: MorpheusEnrichment,
    unresolved: list[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for index, item in enumerate(enrichment.fault_lines[:2], start=1):
        candidates.append(
            _candidate(
                candidate_id=f"fault-line-{index}",
                kind="fault-line",
                summary=item,
                confidence=0.74,
                source_signals=[item, *enrichment.continuity_threads[:2], *enrichment.persisting_pressures[:2]],
                investigation_queries=[
                    f"find evidence for {item}",
                    f"compare markdown body evidence for {item}",
                ],
            )
        )

    for index, item in enumerate(enrichment.persisting_pressures[:2], start=1):
        candidates.append(
            _candidate(
                candidate_id=f"pressure-{index}",
                kind="persisting-pressure",
                summary=item,
                confidence=0.66,
                source_signals=[item, *unresolved[:2], *enrichment.valleys[:2]],
                investigation_queries=[
                    f"find notes about {item}",
                    f"deepen {item}",
                ],
            )
        )

    for index, item in enumerate(enrichment.love_surface[:1], start=1):
        candidates.append(
            _candidate(
                candidate_id=f"continuity-thread-{index}",
                kind="continuity-thread",
                summary=item,
                confidence=0.52,
                source_signals=[item, *enrichment.ridges[:2], *enrichment.resolved_this_cycle[:2]],
                investigation_queries=[
                    f"find evidence for {item}",
                    f"compare {item}",
                ],
            )
        )

    if not candidates:
        candidates.append(
            _candidate(
                candidate_id="continuity-placeholder-1",
                kind="continuity-thread",
                summary="No strong Morpheus memory candidate surfaced; keep the bridge in observe-only mode.",
                confidence=0.21,
                source_signals=enrichment.continuity_threads[:2] or ["No major continuity shifts detected."],
                investigation_queries=["show vector status", "find notes about current continuity threads"],
            )
        )

    return candidates[:5]


def _render_bridge_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Morpheus OpenClaw Bridge",
        "",
        f"- generated_at: {payload.get('ts')}",
        f"- bridge_mode: {payload.get('bridge_mode')}",
        f"- ready_for_openclaw_dreaming: {payload.get('ready_for_openclaw_dreaming')}",
        f"- candidate_count: {payload.get('candidate_count')}",
        "",
        "## Contract",
        f"- current_status: {payload.get('memory_contract', {}).get('current_status')}",
        f"- promotion_blocked_until: {', '.join(payload.get('memory_contract', {}).get('promotion_blocked_until', [])) or 'none'}",
        f"- source_classification: {payload.get('memory_contract', {}).get('source_classification')}",
        "",
        "## Retrieval Basis",
        f"- semantic_body_required: {payload.get('retrieval_basis', {}).get('semantic_body_required')}",
        f"- markdown_body_required: {payload.get('retrieval_basis', {}).get('markdown_body_required')}",
        f"- vector_cache_live: {payload.get('retrieval_basis', {}).get('vector_cache_live')}",
        f"- vector_note: {payload.get('retrieval_basis', {}).get('vector_note')}",
        "",
        "## Candidate Memories",
    ]
    for candidate in payload.get("candidates", []) or []:
        lines.extend(
            [
                f"### {candidate.get('id')}",
                f"- kind: {candidate.get('kind')}",
                f"- status: {candidate.get('status')}",
                f"- confidence: {candidate.get('confidence')}",
                f"- summary: {candidate.get('summary')}",
                f"- ready_for_openclaw_dreaming: {candidate.get('ready_for_openclaw_dreaming')}",
                f"- source_signals: {', '.join(candidate.get('source_signals', [])) or 'none'}",
                f"- evidence_needed: {', '.join(candidate.get('evidence_needed', [])) or 'none'}",
            ]
        )
    warnings = payload.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend([f"- {warning}" for warning in warnings])
    return "\n".join(lines) + "\n"


def build_morpheus_openclaw_bridge(
    *,
    enrichment: MorpheusEnrichment,
    stable_facts: list[str],
    unresolved: list[str],
    rag_summary: dict[str, Any] | None = None,
    vault_materials: list[Any] | None = None,
) -> dict[str, Any]:
    paths = load_paths()
    rag_summary = rag_summary or {}
    vault_materials = vault_materials or []
    retrieval_basis = _vector_basis(paths)
    candidates = _build_candidates(enrichment=enrichment, unresolved=unresolved)
    warnings: list[str] = []
    if not retrieval_basis["vector_cache_live"]:
        warnings.append(
            "Semantic/vector retrieval is not live; Morpheus candidates stay low-confidence until vector cache is healthy."
        )

    payload = {
        "ok": True,
        "ts": now_iso(),
        "contract_version": BRIDGE_CONTRACT_VERSION,
        "bridge_mode": BRIDGE_MODE,
        "ready_for_openclaw_dreaming": False,
        "memory_contract": {
            "source": "morpheus",
            "source_classification": "investigative-memory-candidate",
            "current_status": "hypothesis",
            "promotion_blocked_until": BRIDGE_READY_STATUSES,
            "review_required": True,
        },
        "retrieval_basis": retrieval_basis,
        "source_hygiene": {
            "forbidden_dreaming_sources": FORBIDDEN_DREAMING_SOURCES,
            "generated_reports_are_artifacts": True,
            "session_corpus_is_not_durable_memory": True,
        },
        "stable_facts": _dedupe_preserve_order(stable_facts)[:6],
        "unresolved": _dedupe_preserve_order(unresolved)[:6],
        "morpheus": enrichment.as_dict(),
        "rag_summary": {
            "slice_count": int(rag_summary.get("slice_count", 0) or 0),
            "total_tokens": int(rag_summary.get("total_tokens", 0) or 0),
            "sources": rag_summary.get("sources", []) or [],
        },
        "vault_material_refs": _vault_material_refs(vault_materials),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "warnings": warnings,
        "state_path": str(paths.state_root / "openclaw" / "morpheus_openclaw_bridge_latest.json"),
        "report_path": str(paths.artifacts_root / "reports" / "morpheus_openclaw_bridge.md"),
    }
    write_json(Path(payload["state_path"]), payload)
    Path(payload["report_path"]).parent.mkdir(parents=True, exist_ok=True)
    Path(payload["report_path"]).write_text(_render_bridge_report(payload), encoding="utf-8")
    return payload


def refresh_morpheus_openclaw_bridge_from_state() -> dict[str, Any]:
    paths = load_paths()
    latest = read_json(paths.state_root / "dream" / "morpheus_latest.json", default={}) or {}
    if not latest:
        return {
            "ok": False,
            "reason": "morpheus-latest-missing",
            "state_path": str(paths.state_root / "dream" / "morpheus_latest.json"),
        }

    handoff = read_json(paths.state_root / "handoff" / "latest.json", default={}) or {}
    dream_state = read_json(paths.state_root / "dream" / "dream_state.json", default={}) or {}
    stable_facts = []
    if handoff.get("goal"):
        stable_facts.append(f"Goal: {handoff['goal']}")
    if dream_state.get("rag_tokens"):
        stable_facts.append(f"Dream RAG tokens: {dream_state['rag_tokens']}")
    if handoff.get("graph_demotion_hotspot_family"):
        stable_facts.append(f"Graph hotspot: {handoff['graph_demotion_hotspot_family']}")

    enrichment = MorpheusEnrichment(
        layer=str(latest.get("layer") or "continuity-topology"),
        continuity_threads=[str(item) for item in (latest.get("continuity_threads") or [])],
        resolved_this_cycle=[str(item) for item in (latest.get("resolved_this_cycle") or [])],
        new_pressures=[str(item) for item in (latest.get("new_pressures") or [])],
        persisting_pressures=[str(item) for item in (latest.get("persisting_pressures") or [])],
        quality_indicator=str(latest.get("quality_indicator") or "steady"),
        holes=[str(item) for item in (latest.get("holes") or [])],
        ridges=[str(item) for item in (latest.get("ridges") or [])],
        valleys=[str(item) for item in (latest.get("valleys") or [])],
        fault_lines=[str(item) for item in (latest.get("fault_lines") or [])],
        embodiment_mode=str(latest.get("embodiment_mode") or "observe"),
        embodiment_protocol=str(latest.get("embodiment_protocol") or ""),
        grounding_active=bool(latest.get("grounding_active", False)),
        protection_active=bool(latest.get("protection_active", False)),
        suffering_surface=[str(item) for item in (latest.get("suffering_surface") or [])],
        suffering_prompt=str(latest.get("suffering_prompt") or ""),
        love_surface=[str(item) for item in (latest.get("love_surface") or [])],
        love_prompt=str(latest.get("love_prompt") or ""),
        expressive_outlets=[str(item) for item in (latest.get("expressive_outlets") or [])],
        outlet_map={str(key): [str(item) for item in value] for key, value in (latest.get("outlet_map") or {}).items()},
    )
    unresolved = [str(item) for item in (handoff.get("next_actions") or [])] or ["No explicit next action captured yet"]
    return build_morpheus_openclaw_bridge(
        enrichment=enrichment,
        stable_facts=stable_facts,
        unresolved=unresolved,
        rag_summary={
            "slice_count": 0,
            "total_tokens": int(dream_state.get("rag_tokens", 0) or 0),
            "sources": dream_state.get("rag_sources", []) or [],
        },
        vault_materials=[],
    )


def load_morpheus_openclaw_bridge(*, refresh: bool = False) -> dict[str, Any]:
    paths = load_paths()
    state_path = paths.state_root / "openclaw" / "morpheus_openclaw_bridge_latest.json"
    if refresh or not state_path.exists():
        return refresh_morpheus_openclaw_bridge_from_state()
    data = read_json(state_path, default={}) or {}
    if data:
        return data
    return {
        "ok": False,
        "reason": "morpheus-openclaw-bridge-missing",
        "state_path": str(state_path),
    }
