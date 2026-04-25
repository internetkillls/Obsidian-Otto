from __future__ import annotations

from pathlib import Path
from typing import Any

from ..brain import (
    OttoSelfModel,
    PredictiveScaffold,
    MemoryLayer,
    MemoryTier,
    TierEntry,
)
from ..config import load_paths
from ..events import (
    Event,
    EventBus,
    EVENT_BRAIN_SELF_MODEL_UPDATED,
    EVENT_BRAIN_PREDICTION_GENERATED,
    EVENT_BRAIN_RITUAL_COMPLETED,
)
from ..logging_utils import get_logger
from ..state import OttoState, now_iso, read_json, write_json


def _write_otto_profile_report(paths: Any, snapshot: dict[str, Any]) -> Path:
    report_path = paths.artifacts_root / "reports" / "otto_profile.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Otto Profile Report",
        "",
        f"- generated_at: {now_iso()}",
        "",
        "## Cognitive Risks",
    ]
    lines.extend([f"- {item}" for item in snapshot.get("cognitive_risks", [])] or ["- (none)"])
    lines.extend(["", "## Recovery Levers"])
    lines.extend([f"- {item}" for item in snapshot.get("recovery_levers", [])] or ["- (none)"])
    lines.extend(["", "## Support Style"])
    lines.extend([f"- {item}" for item in snapshot.get("support_style", [])] or ["- (none)"])
    lines.extend(["", "## Commitments To Recall"])
    for item in snapshot.get("continuity_commitments", [])[:6]:
        lines.append(f"- {item['cue']} | kind={item['kind']} | path={item['path']} | conf={item['confidence']:.2f}")
    if not snapshot.get("continuity_commitments"):
        lines.append("- (none)")
    lines.extend(["", "## Opportunities To Surface"])
    for item in snapshot.get("opportunity_map", [])[:6]:
        lines.append(f"- {item['cue']} | horizon={item['horizon']} | kind={item['kind']} | path={item['path']} | conf={item['confidence']:.2f}")
    if not snapshot.get("opportunity_map"):
        lines.append("- (none)")
    continuity_prompts = snapshot.get("continuity_prompts", []) or snapshot.get("sm2_hooks", [])
    lines.extend(["", "## Continuity Prompts"])
    for item in continuity_prompts[:6]:
        lines.append(f"- {item['question']} | source={item['path']} | conf={item['confidence']:.2f}")
    if not continuity_prompts:
        lines.append("- (none)")
    lines.extend(["", "## Mentor Queue"])
    for item in snapshot.get("mentor_pending_tasks", [])[:6]:
        lines.append(f"- {item['title']} | task_id={item['task_id']} | status={item['status']}")
    if not snapshot.get("mentor_pending_tasks"):
        lines.append("- (none)")
    lines.extend(["", "## SWOT"])
    swot = snapshot.get("swot", {}) or {}
    for key in ("strengths", "weaknesses", "opportunities", "threats"):
        lines.append(f"### {key.capitalize()}")
        lines.extend([f"- {item}" for item in swot.get(key, [])] or ["- (none)"])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def run_brain_self_model() -> dict[str, Any]:
    logger = get_logger("otto.brain.self_model")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()

    if paths.vault_path is None:
        raise RuntimeError("Vault path not configured.")

    bronze_path = paths.bronze_root / "bronze_manifest.json"
    if not bronze_path.exists():
        logger.warning("[brain] no bronze scan found — run pipeline first")
        return {"status": "skipped", "reason": "no_bronze_scan"}

    import json
    bronze = json.loads(bronze_path.read_text(encoding="utf-8"))

    sm = OttoSelfModel(vault_path=paths.vault_path)
    snapshot = sm.build_from_scan(bronze)
    profile_path = sm.write_profile_to_vault()
    report_path = _write_otto_profile_report(paths, snapshot)

    EventBus(paths).publish(Event(
        type=EVENT_BRAIN_SELF_MODEL_UPDATED,
        source="brain",
        payload={
            "ts": now_iso(),
            "profile_path": str(profile_path),
            "report_path": str(report_path),
            "strengths": snapshot["strengths"],
            "weaknesses": snapshot["weaknesses"],
            "theme_map": snapshot["theme_map"],
            "cognitive_risks": snapshot.get("cognitive_risks", []),
            "recovery_levers": snapshot.get("recovery_levers", []),
            "support_style": snapshot.get("support_style", []),
        },
    ))

    handoff = read_json(state.handoff_latest, default={}) or {}
    handoff.update({
        "profile_updated_at": now_iso(),
        "profile_report_path": str(report_path),
        "profile_note_path": str(profile_path),
        "profile_cognitive_risks": snapshot.get("cognitive_risks", [])[:5],
        "profile_recovery_levers": snapshot.get("recovery_levers", [])[:5],
        "profile_support_style": snapshot.get("support_style", [])[:5],
        "profile_commitments_to_recall": snapshot.get("continuity_commitments", [])[:5],
        "profile_opportunities_to_surface": snapshot.get("opportunity_map", [])[:5],
        "profile_continuity_prompts": snapshot.get("continuity_prompts", [])[:5],
        "profile_suffering_signals": snapshot.get("suffering_signals", [])[:5],
        "profile_swot": snapshot.get("swot", {}),
        "profile_legacy_reflection_hooks": snapshot.get("continuity_prompts", [])[:5],
    })
    write_json(state.handoff_latest, handoff)

    ml = MemoryLayer(vault_path=paths.vault_path)
    entry = TierEntry(
        tier=MemoryTier.INTERPRETATION,
        content=f"Self-model updated: {len(snapshot['strengths'])} strengths, {len(snapshot['weaknesses'])} weaknesses identified",
        source_note=str(profile_path),
        confidence=0.85,
    )
    ml.write_tier_entry(entry)

    logger.info(f"[brain] self-model written to {profile_path}")
    return {
        "status": "ok",
        "profile_path": str(profile_path),
        "report_path": str(report_path),
        "commitments": len(snapshot.get("continuity_commitments", [])),
        "opportunities": len(snapshot.get("opportunity_map", [])),
    }


def run_brain_predictions() -> dict[str, Any]:
    logger = get_logger("otto.brain.predictions")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()

    if paths.vault_path is None:
        raise RuntimeError("Vault path not configured.")

    sm = OttoSelfModel(vault_path=paths.vault_path)
    handoff = read_json(state.handoff_latest, default={}) or {}
    profile = {
        "vault_strengths": sm.profile.vault_strengths,
        "vault_weaknesses": sm.profile.vault_weaknesses,
        "observed_patterns": sm.profile.observed_patterns,
        "cognitive_risks": sm.profile.cognitive_risks or handoff.get("profile_cognitive_risks", []),
        "recovery_levers": sm.profile.recovery_levers or handoff.get("profile_recovery_levers", []),
        "support_style": sm.profile.support_style or handoff.get("profile_support_style", []),
        "continuity_commitments": sm.profile.continuity_commitments or handoff.get("profile_commitments_to_recall", []),
        "opportunity_map": sm.profile.opportunity_map or handoff.get("profile_opportunities_to_surface", []),
        "continuity_prompts": (
            sm.profile.continuity_prompts
            or handoff.get("profile_continuity_prompts", [])
            or handoff.get("profile_sm2_hooks", [])
        ),
        "legacy_reflection_hooks": handoff.get("profile_legacy_reflection_hooks", []),
        "suffering_signals": sm.profile.suffering_signals or handoff.get("profile_suffering_signals", []),
        "mentor_pending_tasks": handoff.get("mentor_pending_tasks", []),
    }

    ps = PredictiveScaffold(vault_path=paths.vault_path)
    preds = ps.generate_from_profile(profile)
    pred_path = ps.write_predictions_to_vault()

    EventBus(paths).publish(Event(
        type=EVENT_BRAIN_PREDICTION_GENERATED,
        source="brain",
        payload={"ts": now_iso(), "prediction_count": len(preds), "path": str(pred_path)},
    ))

    logger.info(f"[brain] {len(preds)} predictions written to {pred_path}")
    return {"status": "ok", "predictions": len(preds), "path": str(pred_path)}


def run_brain_ritual_cycle() -> dict[str, Any]:
    logger = get_logger("otto.brain.ritual")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()

    if paths.vault_path is None:
        raise RuntimeError("Vault path not configured.")

    from ..brain import RitualEngine

    re_engine = RitualEngine(vault_path=paths.vault_path)
    results = re_engine.run_full_cycle()

    ritual_paths = []
    for r in results:
        p = re_engine.write_ritual_note(r)
        ritual_paths.append(str(p))

    ml = MemoryLayer(vault_path=paths.vault_path)
    cycle_entry = TierEntry(
        tier=MemoryTier.INTERPRETATION,
        content=f"Ritual cycle completed: {len(results)} phases, {sum(r.artifacts_created for r in results)} artifacts",
        source_note=".Otto-Realm/Rituals",
        confidence=0.9,
    )
    ml.write_tier_entry(cycle_entry)

    EventBus(paths).publish(Event(
        type=EVENT_BRAIN_RITUAL_COMPLETED,
        source="brain",
        payload={
            "ts": now_iso(),
            "phases": [r.phase.value for r in results],
            "artifacts": sum(r.artifacts_created for r in results),
        },
    ))

    logger.info(f"[brain] ritual cycle complete: {len(results)} phases")
    return {
        "status": "ok",
        "phases": [r.phase.value for r in results],
        "durations": [f"{r.duration_ms:.1f}ms" for r in results],
        "ritual_notes": ritual_paths,
    }
