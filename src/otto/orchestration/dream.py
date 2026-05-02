from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..events import Event, EventBus, EVENT_DREAM, EVENT_MORPHEUS_ENRICHED, EVENT_MORPHEUS_MEMORY_CANDIDATES
from ..logging_utils import get_logger
from ..models import choose_model
from ..retrieval.rag_context import build_rag_context, LongContextLimiter
from ..state import OttoState, now_iso, read_json, write_json
from .brain import run_brain_self_model
from .vault_telemetry import run_vault_telemetry
from .dream_ingredients import VaultDreamSource
from .morpheus import MorpheusEngine
from .morpheus_openclaw_bridge import build_morpheus_openclaw_bridge
from .vault_signal_tools import VaultSignalTools


def _tail(path: Path, limit: int = 20) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def run_dream_once() -> dict[str, Any]:
    logger = get_logger("otto.dream")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()
    model = choose_model("dream_consolidation")
    handoff = read_json(state.handoff_latest, default={}) or {}
    checkpoint = read_json(state.checkpoints, default={}) or {}

    log_tail = _tail(paths.logs_root / "app" / "otto.log", limit=12)
    event_tail = _tail(paths.state_root / "run_journal" / "events.jsonl", limit=12)

    stable_facts = []
    if checkpoint:
        stable_facts.append(f"Last pipeline scope: {checkpoint.get('scope', '.')}")
        stable_facts.append(f"Training ready: {checkpoint.get('training_ready', False)}")
    if handoff.get("goal"):
        stable_facts.append(f"Goal: {handoff['goal']}")
    if handoff.get("graph_demotion_hotspot_family"):
        stable_facts.append(f"Graph hotspot: {handoff['graph_demotion_hotspot_family']}")
    if handoff.get("graph_demotion_next_apply_mode"):
        stable_facts.append(f"Graph next mode: {handoff['graph_demotion_next_apply_mode']}")

    unresolved = handoff.get("next_actions") or ["No explicit next action captured yet"]
    repeated_failures = []
    if not checkpoint:
        repeated_failures.append("Pipeline has not yet produced a checkpoint")

    # ── RAG context (all 3 DBs + vault signals) ───────────────────────────────
    query = "vault consolidation dream memory signals chaos"
    rag_slices = build_rag_context(goal="dream consolidation", query=query)
    rag_summary = {
        "slice_count": len(rag_slices),
        "total_tokens": sum(s.tokens for s in rag_slices),
        "sources": list({s.source for s in rag_slices}),
    }
    logger.info(f"[dream] RAG context: {rag_summary['sources']}, {rag_summary['total_tokens']} tokens")

    # Build formatted RAG block
    rag_block = "\n".join(
        f"## {s.label} [{s.source}, ~{s.tokens} tokens]\n{s.content}"
        for s in rag_slices
    )

    report_lines = [
        "# Dream Summary",
        "",
        f"- timestamp: {now_iso()}",
        f"- model_hint: {model.model}",
        f"- rag_context_tokens: {rag_summary['total_tokens']}",
        f"- rag_sources: {', '.join(rag_summary['sources'])}",
        "",
        "# RAG Context (from SQLite + ChromaDB + Postgres + Vault)",
        rag_block,
        "",
        "## Stable facts",
    ]
    report_lines.extend([f"- {item}" for item in stable_facts] or ["- none"])
    report_lines.extend(["", "## Unresolved"])
    report_lines.extend([f"- {item}" for item in unresolved] or ["- none"])
    report_lines.extend(["", "## Repeated operational failures"])
    report_lines.extend([f"- {item}" for item in repeated_failures] or ["- none"])
    report_lines.extend(["", "## Recent log tail"])
    report_lines.extend([f"- {item}" for item in log_tail] or ["- no logs yet"])
    report_lines.extend(["", "## Recent event tail"])
    report_lines.extend([f"- {item}" for item in event_tail] or ["- no events yet"])

    # --- vault telemetry (for dream context awareness) ---
    telemetry = None
    try:
        telemetry = run_vault_telemetry()
        report_lines.extend([
            "",
            "## Vault Telemetry (for dream context)",
            f"- overall_training_worth: {telemetry.overall_training_worth} (higher=better)",
            f"- dead_zones: {', '.join(telemetry.dead_zones[:3]) or 'none'}",
            f"- train_targets: {len(telemetry.train_targets)} areas",
        ])
        if telemetry.train_targets:
            report_lines.append("### High signal areas (worth consolidating)")
            for t in telemetry.train_targets[:3]:
                report_lines.append(f"- {t['area']} worth={t['training_worth']:.2f}")
    except Exception:
        pass  # non-fatal in dream

    # --- vault dream ingredients ---
    vault_materials: list[Any] = []
    try:
        vds = VaultDreamSource()
        vault_materials = vds.ingest_since_last()
        if vault_materials:
            corpus_path = vds.append_to_dreams_corpus(vault_materials)
            logger.info(f"[dream] vault materials appended to {corpus_path}")
            by_area: dict[str, list[Any]] = {}
            for m in vault_materials:
                by_area.setdefault(m.area, []).append(m)
            report_lines.extend(["", "## Vault Dream Materials (since last cycle)"])
            for area_name, mats in by_area.items():
                report_lines.append(f"### {area_name}")
                for m in mats[:5]:
                    report_lines.append(
                        f"- {m.mtime[:10]} — {m.content_excerpt[:150]} — [[{m.source_path}]]"
                    )
                if len(mats) > 5:
                    report_lines.append(f"  _(and {len(mats) - 5} more)_")
        else:
            report_lines.extend(["", "## Vault Dream Materials (since last cycle)"])
            report_lines.append("- no new materials since last cycle")
    except Exception:
        logger.warning(f"[dream] vault ingestion skipped: {traceback.format_exc()}")
        report_lines.extend(["", "## Vault Dream Materials (since last cycle)"])
        report_lines.append("- vault ingestion failed (non-fatal)")

    # --- vault-wide signal scan ---
    try:
        vst = VaultSignalTools()
        chaos = vst.list_chaos_to_order(limit=5, focus="all")
        top_signals = vst.search_signals("scarcity", limit=5)
        report_lines.extend(["", "## Vault-Wide Signals (full vault)"])
        if chaos:
            report_lines.append("### Chaos-to-Order (needs attention)")
            for c in chaos[:5]:
                report_lines.append(
                    f"- score={c.score:.1f} {list(c.factors.keys())} — [[{c.path}]]"
                )
        if top_signals:
            report_lines.append("### Top Scarcity Signals")
            for h in top_signals[:5]:
                report_lines.append(
                    f"- [{h.signal_type}] {h.signal_value} — [[{h.path}]]"
                )
        if not chaos and not top_signals:
            report_lines.append("- no strong signals detected")
    except Exception:
        logger.warning(f"[dream] vault signal scan skipped: {traceback.format_exc()}")

    morpheus = MorpheusEngine()
    enrichment = morpheus.enrich(
        stable_facts=stable_facts,
        unresolved=unresolved,
        vault_materials=vault_materials,
        telemetry=telemetry,
    )
    report_lines.extend(["", "## MORPHEUS Continuity"])
    report_lines.extend([f"- {item}" for item in enrichment.continuity_threads] or ["- none"])
    report_lines.extend(["", "## MORPHEUS Change Vectors"])
    if enrichment.resolved_this_cycle:
        report_lines.append("### Resolved this cycle")
        report_lines.extend([f"- {item}" for item in enrichment.resolved_this_cycle] or ["- none"])
    if enrichment.new_pressures:
        report_lines.append("### New pressures")
        report_lines.extend([f"- {item}" for item in enrichment.new_pressures] or ["- none"])
    if enrichment.persisting_pressures:
        report_lines.append("### Persisting pressures")
        report_lines.extend([f"- {item}" for item in enrichment.persisting_pressures] or ["- none"])
    report_lines.extend(["", f"**Quality indicator**: `{enrichment.quality_indicator}`"])
    report_lines.extend(["", "## MORPHEUS Topology", "### Holes (dead zones)"])
    report_lines.extend([f"- {item}" for item in enrichment.holes] or ["- none"])
    report_lines.extend(["### Ridges (high-value areas)"])
    report_lines.extend([f"- {item}" for item in enrichment.ridges] or ["- none"])
    report_lines.extend(["### Valleys (recurring failures)"])
    report_lines.extend([f"- {item}" for item in enrichment.valleys] or ["- none"])
    report_lines.extend(["### Fault lines (critical tensions)"])
    report_lines.extend([f"- {item}" for item in enrichment.fault_lines] or ["- none"])
    report_lines.extend([
        "",
        "## MORPHEUS Embodiment",
        f"**Mode**: `{enrichment.embodiment_mode}`",
        f"- {enrichment.embodiment_protocol or 'none'}",
    ])
    if enrichment.grounding_active:
        report_lines.append("Grounding protocol active")
    if enrichment.protection_active:
        report_lines.append("Protection protocol active")
    report_lines.extend(["", "## MORPHEUS Emotional Depth"])
    report_lines.extend(["### Suffering surface (what Joshua grinds against)"])
    report_lines.extend([f"- {item}" for item in enrichment.suffering_surface] or ["- none"])
    if enrichment.suffering_prompt:
        report_lines.append(f"\n> {enrichment.suffering_prompt}")
    report_lines.extend(["### Love surface (what draws Joshua back)"])
    report_lines.extend([f"- {item}" for item in enrichment.love_surface] or ["- none"])
    if enrichment.love_prompt:
        report_lines.append(f"\n> {enrichment.love_prompt}")
    report_lines.extend(["", "## MORPHEUS Expressive Outlets"])
    report_lines.extend([f"- {item}" for item in enrichment.expressive_outlets] or ["- none"])
    if enrichment.outlet_map:
        report_lines.append("### Outlet map")
        for area, expressions in enrichment.outlet_map.items():
            report_lines.append(f"- *{area}*: {', '.join(expressions)}")

    # ── Long Context: bound total prompt size ────────────────────────────────
    full_content = "\n".join(report_lines)
    limiter = LongContextLimiter()
    char_budget = limiter.max_tokens * 4
    if len(full_content) > char_budget:
        report_lines = report_lines[:120]
        report_lines.append(f"\n[... context truncated from {len(full_content)} to {char_budget} chars ...]")
        logger.warning(f"[dream] report truncated: {len(full_content)} → {char_budget} chars")

    report_path = paths.artifacts_root / "reports" / "dream_summary.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    write_json(paths.state_root / "dream" / "morpheus_latest.json", enrichment.as_dict())
    bridge_payload = build_morpheus_openclaw_bridge(
        enrichment=enrichment,
        stable_facts=stable_facts,
        unresolved=[str(item) for item in unresolved],
        rag_summary=rag_summary,
        vault_materials=vault_materials,
    )

    dream_state = {
        "ts": now_iso(),
        "model_hint": model.model,
        "stable_fact_count": len(stable_facts),
        "unresolved_count": len(unresolved),
        "vault_material_count": len(vault_materials),
        "rag_tokens": rag_summary["total_tokens"],
        "rag_sources": rag_summary["sources"],
        "morpheus_layer": enrichment.layer,
        "embodiment_mode": enrichment.embodiment_mode,
        "continuity_thread_count": len(enrichment.continuity_threads),
        "fault_line_count": len(enrichment.fault_lines),
        "resolved_this_cycle_count": len(enrichment.resolved_this_cycle),
        "expressive_outlet_count": len(enrichment.expressive_outlets),
        "morpheus_candidate_count": int(bridge_payload.get("candidate_count", 0) or 0),
        "ready_for_openclaw_dreaming": bool(bridge_payload.get("ready_for_openclaw_dreaming", False)),
    }
    write_json(state.dream, dream_state)
    bus = EventBus()
    bus.publish(Event(type=EVENT_DREAM, source="dream", payload=dream_state))
    bus.publish(Event(type=EVENT_MORPHEUS_ENRICHED, source="dream", payload=enrichment.as_dict()))
    bus.publish(Event(type=EVENT_MORPHEUS_MEMORY_CANDIDATES, source="dream", payload=bridge_payload))

    # ── Emit telemetry record (spec §6.2: every cycle must write to events.jsonl) ──
    from ..logging_utils import append_jsonl
    append_jsonl(
        state.run_journal / "events.jsonl",
        {
            "ts": now_iso(),
            "cycle_id": f"dream-{now_iso()}",
            "phase": "B",
            "source": "dream",
            "morpheus_layer": enrichment.layer,
            "continuity_thread_count": len(enrichment.continuity_threads),
            "fault_line_count": len(enrichment.fault_lines),
            "embodiment_mode": enrichment.embodiment_mode,
            "grounding_active": enrichment.grounding_active,
            "protection_active": enrichment.protection_active,
            "suffering_surface_count": len(enrichment.suffering_surface),
            "love_surface_count": len(enrichment.love_surface),
            "expressive_outlet_count": len(enrichment.expressive_outlets),
            "vault_material_count": len(vault_materials),
            "unresolved_count": len(unresolved),
        },
    )

    run_brain_self_model()
    logger.info("[dream] summary written")
    return dream_state
