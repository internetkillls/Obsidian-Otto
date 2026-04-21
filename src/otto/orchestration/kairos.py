from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_paths
from ..db import pg_available, read_signals
from ..events import (
    Event,
    EventBus,
    EVENT_COUNCIL_DEBATE,
    EVENT_KAIROS,
    EVENT_KAIROS_CONTRADICTION,
    EVENT_KAIROS_GOLD_SCORED,
    EVENT_META_GOV_ALERT,
    EVENT_OPENCLAW_RESEARCH,
)
from ..logging_utils import append_jsonl, get_logger
from ..models import choose_model
from ..retrieval.rag_context import build_rag_context, LongContextLimiter
from ..state import OttoState, now_iso, read_json, write_json
from .brain import run_brain_predictions
from .council import CouncilEngine
from .vault_telemetry import run_vault_telemetry
from .kairos_directive import produce_kairos_directives
from .kairos_gold import GoldScoringEngine
from .meta_gov import MetaGovObserver
from .morpheus import MorpheusEngine
from .openclaw_research import OpenClawResearchEngine


def _latest_mtime(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_mtime
    mtimes = [p.stat().st_mtime for p in path.rglob("*") if p.is_file()]
    return max(mtimes, default=0.0)


def run_kairos_once() -> dict[str, Any]:
    logger = get_logger("otto.kairos")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()
    model = choose_model("kairos_daily")

    gold = read_json(paths.artifacts_root / "summaries" / "gold_summary.json", default={}) or {}
    checkpoint = read_json(state.checkpoints, default={}) or {}
    events_path = paths.state_root / "run_journal" / "events.jsonl"

    # ── RAG context (all 3 DBs + vault signals) ───────────────────────────────
    query = "metadata repair folder risk vault signals"
    rag_slices = build_rag_context(goal="kairos daily strategy", query=query)
    rag_summary = {
        "slice_count": len(rag_slices),
        "total_tokens": sum(s.tokens for s in rag_slices),
        "sources": list({s.source for s in rag_slices}),
    }
    logger.info(f"[kairos] RAG context: {rag_summary['sources']}, {rag_summary['total_tokens']} tokens")

    # Build formatted RAG block for prompt use
    rag_block = "\n".join(
        f"## {s.label} [{s.source}, ~{s.tokens} tokens]\n{s.content}"
        for s in rag_slices
    )

    # ── Postgres signals (from VaultSignalTools chaos scan) ──────────────────
    unresolved_signals: list[dict[str, Any]] = []
    if pg_available():
        try:
            unresolved_signals = read_signals(limit=20, unresolved_only=True)
        except Exception:
            logger.warning("[kairos] could not read Postgres signals")
    signal_summary = f"{len(unresolved_signals)} unresolved signals" if unresolved_signals else "none in Postgres"

    top_folders = (gold.get("top_folders") or [])[:3]
    cycle_id = f"kairos-{now_iso()}"

    gold_engine = GoldScoringEngine()
    gold_scores, contradictions = gold_engine.score_unresolved_signals(unresolved_signals)
    promoted_scores = [score for score in gold_scores if score.gold_promoted]

    # Gold-only DB filter: only Gold-tier signals enter Postgres
    gold_signals: list[dict[str, Any]] = []
    for signal, score in zip(unresolved_signals, gold_scores):
        if score.band == "gold":
            signal_copy = dict(signal)
            signal_copy["gold_band"] = "gold"
            signal_copy["gold_score"] = score.weighted_score
            gold_signals.append(signal_copy)
    if gold_signals and pg_available():
        try:
            write_signals(gold_signals)
            logger.info(f"[kairos] wrote {len(gold_signals)} gold-only signals to Postgres")
        except Exception:
            logger.warning("[kairos] could not write gold signals to Postgres")

    meta_gov = MetaGovObserver()
    meta_gov_findings = meta_gov.observe()
    morpheus = MorpheusEngine()

    strategy_lines = [
        "# KAIROS Daily Strategy",
        "",
        f"- timestamp: {now_iso()}",
        f"- model_hint: {model.model}",
        f"- rag_context_tokens: {rag_summary['total_tokens']}",
        f"- rag_sources: {', '.join(rag_summary['sources'])}",
        "",
        "# RAG Context (from SQLite + ChromaDB + Postgres + Vault)",
        rag_block,
        "",
        "## Strategy inputs",
        "",
        "## Vault Telemetry (data quality & training worth)",
    ]
    enrichment = None
    try:
        telemetry = run_vault_telemetry()
        enrichment = morpheus.enrich(
            stable_facts=[f"Last pipeline scope: {checkpoint.get('scope', '.')}", f"Training ready: {checkpoint.get('training_ready', False)}"],
            unresolved=[item.get('note_path', item.get('signal_type', 'unknown')) for item in unresolved_signals[:5]],
            vault_materials=[],
            telemetry=telemetry,
        )
        strategy_lines.extend([
            f"- overall_uselessness: {telemetry.overall_uselessness} (lower=better)",
            f"- overall_training_worth: {telemetry.overall_training_worth} (higher=better)",
            f"- high_value_areas: {', '.join(telemetry.high_value_areas[:5]) or 'none yet'}",
            f"- dead_zones: {', '.join(telemetry.dead_zones[:5]) or 'none'}",
        ])
        strategy_lines.extend([
            f"- morpheus_quality_indicator: {enrichment.quality_indicator}",
            f"- morpheus_fault_line_count: {len(enrichment.fault_lines)}",
            f"- morpheus_grounding_active: {enrichment.grounding_active}",
            f"- morpheus_protection_active: {enrichment.protection_active}",
            f"- morpheus_suffering_surface_count: {len(enrichment.suffering_surface)}",
            f"- morpheus_love_surface_count: {len(enrichment.love_surface)}",
        ])
        if telemetry.dig_targets:
            strategy_lines.append("### Dig targets (repair needed)")
            for t in telemetry.dig_targets[:5]:
                strategy_lines.append(f"- [{t['priority'].upper()}] {t['area']}: {t['reason'][:100]}")
        if telemetry.train_targets:
            strategy_lines.append("### Train targets (high signal)")
            for t in telemetry.train_targets[:3]:
                strategy_lines.append(f"- [worth={t['training_worth']:.2f}] {t['area']} ({t['note_count']} notes)")
        logger.info(f"[kairos] telemetry: uselessness={telemetry.overall_uselessness} worth={telemetry.overall_training_worth}")
    except Exception as exc:
        logger.warning(f"[kairos] telemetry skipped: {exc}")
        strategy_lines.append("- telemetry unavailable (run pipeline first)")

    # Council fires AFTER morpheus topology is enriched (spec order)
    council_engine = CouncilEngine()
    council_triggers = council_engine.detect_triggers(
        gold_scores=gold_scores,
        unresolved_signals=unresolved_signals,
        top_folders=top_folders,
        contradictions=contradictions,
        staleness_map=enrichment.staleness_map if enrichment else None,
    )
    # Inject morpheus topology into council context if available
    if enrichment and council_triggers:
        for trigger in council_triggers:
            if enrichment.fault_lines:
                trigger.evidence.append(f"Morpheus fault lines: {len(enrichment.fault_lines)}")
            if enrichment.embodiment_mode != "maintenance":
                trigger.evidence.append(f"Morpheus embodiment: {enrichment.embodiment_mode}")
    council_debates = [council_engine.run_council_debate(trigger) for trigger in council_triggers]

    research_engine = OpenClawResearchEngine()
    research_runs = [
        research_engine.execute(topic_text=trigger.weakness, priority="high" if trigger.severity == "high" else "medium")
        for trigger in council_triggers
    ]

    strategy_lines.extend([
        "",
        f"- checkpoint_scope: {checkpoint.get('scope', 'n/a')}",
        f"- recent_events_present: {events_path.exists()}",
        f"- vault_signals (Postgres): {signal_summary}",
        "",
        "## Gold scoring candidates",
    ])
    if gold_scores:
        for score in gold_scores[:5]:
            strategy_lines.append(
                f"- [{score.band.upper()}] {score.note_path} score={score.weighted_score:.2f} "
                f"(U={score.breakdown.utility}, V={score.breakdown.vault_alignment}, "
                f"I={score.breakdown.insight_density}, A={score.breakdown.actionability}, "
                f"T={score.breakdown.temporal_durability}, threshold={score.gold_threshold:.2f}) "
                f"→ {score.recommended_action}"
            )
    else:
        strategy_lines.append("- no scoreable unresolved signals in this cycle")

    strategy_lines.extend([
        "",
        "## Unresolved vault signals",
    ])
    if unresolved_signals:
        for s in unresolved_signals[:5]:
            strategy_lines.append(
                f"- [{s['signal_type']}] score={s['score']:.1f} → [[{s['note_path']}]]"
            )
    else:
        strategy_lines.append("- none")

    strategy_lines.extend(["", "## Top folder risks (from SQLite folder_risk)"])
    if top_folders:
        for item in top_folders:
            strategy_lines.append(
                f"- {item['folder']} risk={item['risk_score']} "
                f"missing_frontmatter={item['missing_frontmatter']} duplicates={item['duplicate_titles']}"
            )
    else:
        strategy_lines.append("- no Gold data yet — run pipeline first")

    strategy_lines.extend(["", "## Council"])
    if council_debates:
        for debate in council_debates:
            strategy_lines.append(debate.to_markdown())
            strategy_lines.append("")
    else:
        strategy_lines.append("- no council trigger fired in this cycle")

    strategy_lines.extend(["", "## OpenClaw research runs"])
    if research_runs:
        for run in research_runs:
            sources = ", ".join(run.topic.source_tiers)
            result_count = len(run.search_hits)
            fetched_count = len([doc for doc in run.fetched_documents if doc.ok])
            strategy_lines.append(
                f"- [{run.topic.topic_class}] approved={run.approved} "
                f"search_ok={run.search_ok} fetch_ok={run.fetch_ok} "
                f"provider={run.search_provider or 'none'} "
                f"results={result_count} fetched={fetched_count} "
                f"sources={sources} reason={run.budget_reason}"
            )
            if run.search_hits:
                top_hit = run.search_hits[0]
                strategy_lines.append(f"  - top_result: {top_hit.title} -> {top_hit.url}")
            if run.warnings:
                strategy_lines.append(f"  - warning: {run.warnings[0]}")
    else:
        strategy_lines.append("- no active research fetch required this cycle")

    strategy_lines.extend(["", "## META GOV"])
    if meta_gov_findings:
        for finding in meta_gov_findings[:5]:
            strategy_lines.append(
                f"- [{finding.level.upper()}] {finding.flag}: {finding.condition} -> {finding.action}"
            )
    else:
        strategy_lines.append("- no governance alerts")

    next_actions = []
    for item in top_folders:
        next_actions.append(f"Repair metadata in {item['folder']}")
    if unresolved_signals:
        next_actions.append(f"Address {len(unresolved_signals)} unresolved vault signals")
    if not next_actions:
        next_actions.append("Run the first pipeline or choose a vault")
    next_actions.append("Prefer fast retrieval first; escalate only when evidence is weak")
    next_actions.append("Keep training export gated behind reviewed Gold")

    strategy_lines.extend(["", "## Next actions"])
    strategy_lines.extend([f"- {line}" for line in next_actions])

    # ── Long Context: bound total prompt size ────────────────────────────────
    full_content = "\n".join(strategy_lines)
    limiter = LongContextLimiter()
    char_budget = limiter.max_tokens * 4  # chars equivalent
    if len(full_content) > char_budget:
        strategy_lines = strategy_lines[:80]  # hard cap: first 80 lines
        strategy_lines.append(f"\n[... context truncated from {len(full_content)} to {char_budget} chars ...]")
        logger.warning(f"[kairos] strategy truncated: {len(full_content)} → {char_budget} chars")

    report_path = paths.artifacts_root / "reports" / "kairos_daily_strategy.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(strategy_lines) + "\n", encoding="utf-8")

    record = {
        "ts": now_iso(),
        "cycle_id": cycle_id,
        "phase": "B",
        "source": "heartbeat",
        "model_hint": model.model,
        "top_folder_count": len(top_folders),
        "unresolved_signal_count": len(unresolved_signals),
        "rag_tokens": rag_summary["total_tokens"],
        "rag_sources": rag_summary["sources"],
        "kairos_score": round(sum(score.weighted_score for score in gold_scores) / max(len(gold_scores), 1), 3) if gold_scores else 0.0,
        "gold_promoted_count": len(promoted_scores),
        "council_triggered": bool(council_debates),
        "openclaw_fetch": any(run.search_ok or run.fetch_ok for run in research_runs),
        "meta_gov_flag": meta_gov_findings[0].flag if meta_gov_findings else None,
        "next_actions": next_actions,
    }
    append_jsonl(state.kairos, record)

    run_brain_predictions()

    # ── Produce KAIROS directives (data engineer + academic strategy) ──
    try:
        manifest = produce_kairos_directives(cycle=1)
        logger.info(
            f"[kairos] directives: {manifest.summary.get('total_directives',0)} "
            f"(dig={manifest.summary.get('dig',0)} "
            f"train={manifest.summary.get('train',0)} "
            f"refine={manifest.summary.get('refine',0)})"
        )
    except Exception as exc:
        logger.warning(f"[kairos] directive production skipped: {exc}")

    write_json(state.handoff_latest, {
        **(read_json(state.handoff_latest, default={}) or {}),
        "updated_at": now_iso(),
        "status": "ready",
        "goal": "Maintain a stable Obsidian-Otto retrieval core",
        "artifacts": [
            "artifacts/summaries/gold_summary.json",
            "artifacts/reports/kairos_daily_strategy.md",
            "artifacts/reports/dream_summary.md",
        ],
        "next_actions": next_actions,
        "morpheus": {
            "quality_indicator": enrichment.quality_indicator if enrichment else "unknown",
            "fault_line_count": len(enrichment.fault_lines) if enrichment else 0,
            "grounding_active": enrichment.grounding_active if enrichment else False,
            "protection_active": enrichment.protection_active if enrichment else False,
            "suffering_surface_count": len(enrichment.suffering_surface) if enrichment else 0,
            "love_surface_count": len(enrichment.love_surface) if enrichment else 0,
        },
    })

    bus = EventBus()
    bus.publish(Event(type=EVENT_KAIROS_GOLD_SCORED, source="kairos", payload={
        "cycle_id": cycle_id,
        "gold_promoted_count": len(promoted_scores),
        "score_count": len(gold_scores),
        "contradiction_count": len(contradictions),
    }))
    for contradiction in contradictions:
        bus.publish(Event(type=EVENT_KAIROS_CONTRADICTION, source="kairos", payload=contradiction.as_dict()))
    for debate in council_debates:
        bus.publish(Event(type=EVENT_COUNCIL_DEBATE, source="kairos", payload=debate.as_dict()))
    for run in research_runs:
        bus.publish(Event(type=EVENT_OPENCLAW_RESEARCH, source="kairos", payload=run.as_dict()))
    for finding in meta_gov_findings:
        bus.publish(Event(type=EVENT_META_GOV_ALERT, source="meta_gov", payload=finding.as_dict()))
    record.update({
        "morpheus_quality_indicator": enrichment.quality_indicator if enrichment else "unknown",
        "morpheus_fault_line_count": len(enrichment.fault_lines) if enrichment else 0,
        "morpheus_grounding_active": enrichment.grounding_active if enrichment else False,
        "morpheus_protection_active": enrichment.protection_active if enrichment else False,
        "morpheus_suffering_surface_count": len(enrichment.suffering_surface) if enrichment else 0,
        "morpheus_love_surface_count": len(enrichment.love_surface) if enrichment else 0,
    })
    bus.publish(Event(type=EVENT_KAIROS, source="kairos", payload=record))
    logger.info("[kairos] heartbeat written")
    return record
