from __future__ import annotations

import time as time_module
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..state import now_iso


class RitualPhase(str, Enum):
    SCAN = "scan"
    REFLECT = "reflect"
    DREAM = "dream"
    ACT = "act"


@dataclass
class RitualResult:
    phase: RitualPhase
    note_count: int = 0
    artifacts_created: int = 0
    duration_ms: float = 0.0
    summary: str = ""
    ts: str = field(default_factory=now_iso)
    errors: list[str] = field(default_factory=list)


class RitualEngine:
    RITUALS_PATH = "Otto-Realm/Rituals"

    def __init__(self, vault_path: Path | None = None):
        paths = load_paths()
        self.vault_path = vault_path or paths.vault_path
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        self.current_phase = RitualPhase.SCAN
        self.history: list[RitualResult] = []
        self._scan_results: dict[str, Any] = {}

    def run_phase(self, phase: RitualPhase) -> RitualResult:
        start = time_module.perf_counter()
        self.current_phase = phase

        if phase == RitualPhase.SCAN:
            result = self._do_scan()
        elif phase == RitualPhase.REFLECT:
            result = self._do_reflect()
        elif phase == RitualPhase.DREAM:
            result = self._do_dream()
        else:
            result = self._do_act()

        result.duration_ms = (time_module.perf_counter() - start) * 1000
        self.history.append(result)
        return result

    def run_full_cycle(self) -> list[RitualResult]:
        results: list[RitualResult] = []
        for phase in RitualPhase:
            r = self.run_phase(phase)
            results.append(r)
        return results

    def _do_scan(self) -> RitualResult:
        from ..tooling.obsidian_scan import scan_vault
        try:
            scan_data = scan_vault()
            self._scan_results = scan_data
            return RitualResult(
                phase=RitualPhase.SCAN,
                note_count=scan_data.get("note_count", 0),
                artifacts_created=1,
                summary=f"Scanned {scan_data.get('note_count', 0)} notes",
            )
        except Exception as e:
            return RitualResult(
                phase=RitualPhase.SCAN,
                summary=f"Scan failed: {e}",
                errors=[str(e)],
            )

    def _do_reflect(self) -> RitualResult:
        from .self_model import OttoSelfModel
        sm = OttoSelfModel(vault_path=self.vault_path)
        snapshot = sm.build_from_scan(self._scan_results)
        sm.write_profile_to_vault()
        return RitualResult(
            phase=RitualPhase.REFLECT,
            note_count=self._scan_results.get("note_count", 0),
            artifacts_created=1,
            summary=f"Reflected on {len(snapshot.get('strengths', []))} strengths, {len(snapshot.get('weaknesses', []))} weaknesses",
        )

    def _do_dream(self) -> RitualResult:
        from .predictive_scaffold import PredictiveScaffold
        from .memory_layer import MemoryLayer, TierEntry, MemoryTier

        profile = {
            "vault_strengths": [],
            "vault_weaknesses": [],
            "observed_patterns": [],
        }
        if self.history:
            last = self.history[-1]
            profile["vault_strengths"] = last.summary.split("strengths,")[0].split("strengths")[-1:] if "strengths" in last.summary else []

        ps = PredictiveScaffold(vault_path=self.vault_path)
        preds = ps.generate_from_profile(profile)
        ps.write_predictions_to_vault()

        ml = MemoryLayer(vault_path=self.vault_path)
        dream_entry = TierEntry(
            tier=MemoryTier.INTERPRETATION,
            content=f"Ritual dream consolidation: {len(preds)} predictions generated, {len(self.history)} phases completed",
            source_note="Otto-Realm/Rituals/ritual_cycle.md",
            confidence=0.75,
        )
        ml.write_tier_entry(dream_entry)

        return RitualResult(
            phase=RitualPhase.DREAM,
            artifacts_created=len(preds) + 1,
            summary=f"Dream consolidation: {len(preds)} predictions written",
        )

    def _do_act(self) -> RitualResult:
        return RitualResult(
            phase=RitualPhase.ACT,
            summary=f"Act phase: {len(self.history)} rituals completed this cycle",
        )

    def write_ritual_note(self, result: RitualResult) -> Path:
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        rituals_dir = self.vault_path / self.RITUALS_PATH
        rituals_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{result.ts[:10]}_{result.phase.value}_ritual.md"
        path = rituals_dir / filename
        content = f"""---
title: Otto Ritual — {result.phase.value}
date: {result.ts}
phase: {result.phase.value}
note_count: {result.note_count}
duration_ms: {result.duration_ms:.1f}
tags:
  - otto-ritual
  - {result.phase.value}
---

# Otto Ritual: {result.phase.value.capitalize()}

- **Phase:** {result.phase.value}
- **Notes processed:** {result.note_count}
- **Artifacts created:** {result.artifacts_created}
- **Duration:** {result.duration_ms:.1f}ms
- **Timestamp:** {result.ts}

## Summary

{result.summary}

## Errors

{" | ".join(result.errors) if result.errors else "(none)"}

---

*Ritual Engine v1 — Otto Brain Architecture*
"""
        path.write_text(content, encoding="utf-8")
        return path
