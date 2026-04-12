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
from ..state import OttoState, now_iso


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

    EventBus(paths).publish(Event(
        type=EVENT_BRAIN_SELF_MODEL_UPDATED,
        source="brain",
        payload={
            "ts": now_iso(),
            "profile_path": str(profile_path),
            "strengths": snapshot["strengths"],
            "weaknesses": snapshot["weaknesses"],
            "theme_map": snapshot["theme_map"],
        },
    ))

    ml = MemoryLayer(vault_path=paths.vault_path)
    entry = TierEntry(
        tier=MemoryTier.INTERPRETATION,
        content=f"Self-model updated: {len(snapshot['strengths'])} strengths, {len(snapshot['weaknesses'])} weaknesses identified",
        source_note=str(profile_path),
        confidence=0.85,
    )
    ml.write_tier_entry(entry)

    logger.info(f"[brain] self-model written to {profile_path}")
    return {"status": "ok", "profile_path": str(profile_path)}


def run_brain_predictions() -> dict[str, Any]:
    logger = get_logger("otto.brain.predictions")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()

    if paths.vault_path is None:
        raise RuntimeError("Vault path not configured.")

    sm = OttoSelfModel(vault_path=paths.vault_path)
    profile = {
        "vault_strengths": sm.profile.vault_strengths,
        "vault_weaknesses": sm.profile.vault_weaknesses,
        "observed_patterns": sm.profile.observed_patterns,
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
        source_note="Otto-Realm/Rituals",
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
