from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import load_paths
from ..state import now_iso, write_json


@dataclass
class MorpheusEnrichment:
    # Phase 1 - Continuity threads
    continuity_threads: list[str] = field(default_factory=list)
    change_vectors: list[str] = field(default_factory=list)
    resolved_this_cycle: list[str] = field(default_factory=list)
    new_pressures: list[str] = field(default_factory=list)
    persisting_pressures: list[str] = field(default_factory=list)
    quality_indicator: str = "unknown"
    staleness_map: dict[str, int] = field(default_factory=dict)  # signal_path -> consecutive cycles

    # Phase 2 - Topology
    holes: list[str] = field(default_factory=list)
    ridges: list[str] = field(default_factory=list)
    valleys: list[str] = field(default_factory=list)
    fault_lines: list[str] = field(default_factory=list)

    # Phase 3 - Embodiment
    embodiment_mode: str = "maintenance"
    embodiment_protocol: str = ""
    grounding_active: bool = False
    protection_active: bool = False

    # Phase 4 - Emotional depth
    suffering_surface: list[str] = field(default_factory=list)
    love_surface: list[str] = field(default_factory=list)
    suffering_prompt: str = ""
    love_prompt: str = ""

    # Phase 5 - Expressive outlets
    expressive_outlets: list[str] = field(default_factory=list)
    outlet_map: dict[str, list[str]] = field(default_factory=dict)

    # Meta
    layer: str = "none"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": now_iso(),
            "continuity_threads": self.continuity_threads,
            "change_vectors": self.change_vectors,
            "resolved_this_cycle": self.resolved_this_cycle,
            "new_pressures": self.new_pressures,
            "persisting_pressures": self.persisting_pressures,
            "quality_indicator": self.quality_indicator,
            "staleness_map": self.staleness_map,
            "holes": self.holes,
            "ridges": self.ridges,
            "valleys": self.valleys,
            "fault_lines": self.fault_lines,
            "embodiment_mode": self.embodiment_mode,
            "embodiment_protocol": self.embodiment_protocol,
            "grounding_active": self.grounding_active,
            "protection_active": self.protection_active,
            "suffering_surface": self.suffering_surface,
            "love_surface": self.love_surface,
            "suffering_prompt": self.suffering_prompt,
            "love_prompt": self.love_prompt,
            "expressive_outlets": self.expressive_outlets,
            "outlet_map": self.outlet_map,
            "layer": self.layer,
        }


class MorpheusEngine:
    def __init__(self) -> None:
        self.paths = load_paths()

    # ─── Helpers ────────────────────────────────────────────────────────────

    def _load_heartbeats(self, limit: int = 10) -> list[dict[str, Any]]:
        """Load recent kairos.heartbeat events (descending, latest first)."""
        path = self.paths.state_root / "run_journal" / "events.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        heartbeats: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "kairos.heartbeat":
                heartbeats.append(ev)
                if len(heartbeats) >= limit:
                    break
        return list(reversed(heartbeats))  # oldest → newest

    def _load_dream_snapshots(self, limit: int = 5) -> list[dict[str, Any]]:
        """Load recent dream_state.json snapshots."""
        path = self.paths.state_root / "dream" / "dream_state.json"
        if not path.exists():
            return []
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            return [state]
        except json.JSONDecodeError:
            return []

    def _continuity_deltas(self, dream_snapshots: list[dict[str, Any]], heartbeats: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
        """Compare current dream state with prior snapshot to derive continuity deltas."""
        if not dream_snapshots:
            return [], [], []
        latest = dream_snapshots[-1]
        previous = dream_snapshots[-2] if len(dream_snapshots) >= 2 else {}
        latest_layer = str(latest.get("morpheus_layer", ""))
        previous_layer = str(previous.get("morpheus_layer", ""))
        latest_mode = str(latest.get("embodiment_mode", ""))
        previous_mode = str(previous.get("embodiment_mode", ""))

        resolved: list[str] = []
        new_pressures: list[str] = []
        persisting: list[str] = []

        if latest_layer and latest_layer != previous_layer:
            new_pressures.append(f"Layer changed: {previous_layer or 'none'} -> {latest_layer}")
        elif latest_layer:
            persisting.append(f"Layer stable: {latest_layer}")

        if latest_mode and latest_mode != previous_mode:
            new_pressures.append(f"Embodiment changed: {previous_mode or 'none'} -> {latest_mode}")
        elif latest_mode:
            persisting.append(f"Embodiment stable: {latest_mode}")

        if heartbeats:
            latest_hb = heartbeats[-1].get("payload", {})
            if isinstance(latest_hb, dict):
                promoted = int(latest_hb.get("gold_promoted_count", 0))
                if promoted > 0:
                    resolved.append(f"Gold promotions present this cycle: {promoted}")
        return persisting[:3], new_pressures[:3], resolved[:3]

    def _extract_unresolved_signals(self, heartbeats: list[dict[str, Any]]) -> list[str]:
        """Pull unresolved signal descriptions from heartbeat payloads."""
        unresolved: list[str] = []
        for hb in heartbeats:
            payload = hb.get("payload", {})
            if isinstance(payload, dict):
                sigs = payload.get("unresolved_signals", [])
                if isinstance(sigs, list):
                    for s in sigs:
                        if isinstance(s, dict):
                            unresolved.append(str(s.get("note_path", s.get("description", ""))))
                        else:
                            unresolved.append(str(s))
        return unresolved

    def _change_vectors(self, heartbeats: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
        """Derive change vectors: new vs persisting vs resolved signals."""
        if not heartbeats:
            return [], [], []

        latest = heartbeats[-1].get("payload", {})
        if isinstance(latest, dict):
            latest_unresolved = set(latest.get("unresolved_signals", []))
        else:
            latest_unresolved = set()

        previous_unresolved: set[str] = set()
        if len(heartbeats) >= 2:
            prev = heartbeats[-2].get("payload", {})
            if isinstance(prev, dict):
                previous_unresolved = set(prev.get("unresolved_signals", []))

        still_there = latest_unresolved & previous_unresolved
        brand_new = latest_unresolved - previous_unresolved
        resolved = previous_unresolved - latest_unresolved

        persisting = [f"Still live: {s}" for s in list(still_there)[:3]]
        new = [f"New pressure: {s}" for s in list(brand_new)[:3]]
        res = [f"Resolved: {s}" for s in list(resolved)[:3]]
        return persisting, new, res

    def _signal_staleness(self, heartbeats: list[dict[str, Any]], unresolved: list[str]) -> dict[str, int]:
        """Count consecutive cycles each unresolved signal has appeared."""
        counts: dict[str, int] = {}
        for sig in unresolved:
            counts[sig] = 0
        for hb in reversed(heartbeats):
            payload = hb.get("payload", {})
            if not isinstance(payload, dict):
                continue
            hb_unresolved = set()
            for s in (payload.get("unresolved_signals") or []):
                if isinstance(s, dict):
                    hb_unresolved.add(str(s.get("note_path", "")))
                else:
                    hb_unresolved.add(str(s))
            for sig in unresolved:
                if sig in hb_unresolved:
                    counts[sig] += 1
        return counts

    def _topology(
        self,
        unresolved: list[str],
        staleness: dict[str, int],
        heartbeats: list[dict[str, Any]],
        telemetry: Any | None = None,
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        """Build holes, ridges, valleys, fault_lines from signal patterns."""
        holes: list[str] = []
        ridges: list[str] = []
        valleys: list[str] = []
        fault_lines: list[str] = []

        # Holes: unresolved signals that are old (dead zones)
        for sig, count in sorted(staleness.items(), key=lambda x: x[1], reverse=True):
            if count >= 3:
                holes.append(f"Dead zone (unresolved {count} cycles): {sig}")

        # Ridges: high-value areas from telemetry that keep recurring
        if heartbeats:
            latest = heartbeats[-1].get("payload", {})
            if isinstance(latest, dict):
                high_value = latest.get("high_value_areas", [])
                for area in high_value[:3]:
                    if isinstance(area, str):
                        ridges.append(f"Ridge (high training value): {area}")
                    elif isinstance(area, dict):
                        ridges.append(f"Ridge: {area.get('area', area)} worth={area.get('training_worth', '?')}")
        if telemetry is not None:
            for area in (getattr(telemetry, "high_value_areas", []) or [])[:3]:
                ridges.append(f"Ridge (telemetry): {area}")
            for area in (getattr(telemetry, "dead_zones", []) or [])[:3]:
                holes.append(f"Dead zone (telemetry): {area}")

        # Valleys: signals that appear in ≥3 cycles
        for sig, count in sorted(staleness.items(), key=lambda x: x[1], reverse=True):
            if count >= 3:
                valleys.append(f"Valley (recurring failure): {sig}")

        # Fault lines: high-value areas that are also unresolved
        for ridge in ridges:
            for hole in holes:
                # If same area appears in both, it's a fault line
                area = ridge.split(":", 1)[-1].strip()
                if any(area in h for h in holes):
                    fault_lines.append(f"Fault line (critical): {area}")

        # Add explicit unresolved that aren't resolved yet
        for sig in unresolved[:5]:
            if not any(sig in fl for fl in fault_lines):
                if staleness.get(sig, 0) >= 2:
                    fault_lines.append(f"Fault line (unresolved): {sig}")

        return holes[:5], ridges[:5], valleys[:5], fault_lines[:5]

    def _embodiment_mode(
        self,
        unresolved: list[str],
        heartbeats: list[dict[str, Any]],
        staleness: dict[str, int],
        telemetry: Any | None = None,
    ) -> tuple[str, str, bool, bool]:
        """Select embodiment mode based on signal pattern."""
        grounding = False
        protection = False

        # Economic keywords
        economic_keywords = [
            "economic", "revenue", "income", "market", "pricing",
            "asset", "fragility", "career", "burnout", "financial",
        ]

        # Count high-severity unresolved (≥3 cycles)
        high_severity_count = sum(1 for s, c in staleness.items() if c >= 3)

        # Check for economic signals in unresolved
        has_economic = any(
            any(kw in str(s).lower() for kw in economic_keywords)
            for s in unresolved
        )

        # Check for chaos signals
        has_chaos = any("chaos" in str(s).lower() for s in unresolved)

        # Check recent gold promotions
        recent_promotions = 0
        if heartbeats:
            latest = heartbeats[-1].get("payload", {})
            if isinstance(latest, dict):
                recent_promotions = int(latest.get("gold_promoted_count", 0))
        training_worth = float(getattr(telemetry, "overall_training_worth", 0.0) or 0.0)
        uselessness = float(getattr(telemetry, "overall_uselessness", 0.0) or 0.0)

        # Determine mode
        if has_economic:
            mode = "protection"
            protocol = (
                "Economic or career signal detected. Protect the foundation first. "
                "Do not expand into creative or experimental work until cashflow and leverage are stabilized. "
                "Map every unresolved signal against financial impact before assigning energy."
            )
            protection = True
        elif has_chaos and high_severity_count >= 2:
            mode = "grounding"
            protocol = (
                "High chaos + persistent unresolved signals detected. Ground before growing. "
                "Choose one signal with highest staleness and commit to resolving it before opening new inputs. "
                "Stand up, hydrate, and close the most demanding 15-minute context block before checking messages."
            )
            grounding = True
        elif high_severity_count >= 3:
            mode = "consolidation"
            protocol = (
                "Three or more signals have persisted ≥3 cycles. Consolidate before proceeding. "
                "Run a contradiction audit across unresolved signals, then rank by leverage. "
                "Do not add new signals until the backlog is triaged."
            )
        elif recent_promotions >= 2 and high_severity_count == 0:
            mode = "expansion"
            protocol = (
                "Quality signal throughput is healthy with no persistent failures. "
                "Expand into the highest-value ridge. "
                "Delegate low-leverage work and focus energy on the signal with the most compounding potential."
            )
        elif training_worth >= 1.5 and uselessness <= 1.0 and high_severity_count <= 1:
            mode = "refinement"
            protocol = (
                "Vault telemetry shows strong training worth with low uselessness. "
                "Refine the best ridge, preserve alignment, and make the next synthesis more legible."
            )
        elif recent_promotions >= 1 and high_severity_count <= 1:
            mode = "integration"
            protocol = (
                "Some signals resolved this cycle. Integrate learning before adding more. "
                "Write a brief synthesis of what changed and why, then allow the next input."
            )
        else:
            mode = "maintenance"
            protocol = (
                "No dominant pressure pattern detected. Maintain normal operation. "
                "Keep intake and output balanced. Flag any new unresolved signal before it becomes persistent."
            )

        return mode, protocol, grounding, protection

    def _suffering_love_surface(
        self,
        valleys: list[str],
        fault_lines: list[str],
        ridges: list[str],
        unresolved: list[str],
    ) -> tuple[list[str], list[str], str, str]:
        """Infer suffering and love surfaces from topology (deterministic).
        Spec §2.4: MORPHEUS demands to know how to suffer and how to love —
        not avoidance, not sentiment, but the precise mechanism.
        Prompts are dynamically derived from actual topology data, not hardcoded."""
        suffering: list[str] = []
        love: list[str] = []

        economic_keywords = ["economic", "revenue", "career", "financial", "income", "burnout"]
        creative_keywords = ["creative", "synthesis", "vision", "design", "writing", "building"]
        identity_keywords = ["self_model", "identity", "belief", "story", "narrative"]
        predator_qua_angel_keywords = ["fear", "reactive", "momentum", "social theater", "extraction"]

        # ── Suffering surface ───────────────────────────────────────────────
        for valley in valleys:
            if any(kw in valley.lower() for kw in economic_keywords):
                suffering.append(f"Economic friction: {valley}")
            elif any(kw in valley.lower() for kw in identity_keywords):
                suffering.append(f"Identity erosion: {valley}")
            else:
                suffering.append(f"Recurring failure: {valley}")

        for fl in fault_lines[:3]:
            # Classify fault line type
            if any(kw in fl.lower() for kw in economic_keywords):
                suffering.append(f"Economic fault line: {fl}")
            elif any(kw in fl.lower() for kw in predator_qua_angel_keywords):
                suffering.append(f"Predator qua Angel deviation: {fl}")
            else:
                suffering.append(f"Critical tension: {fl}")

        for sig in unresolved[:3]:
            if any(kw in str(sig).lower() for kw in economic_keywords):
                suffering.append(f"Financial pressure: {sig}")
            elif any(kw in str(sig).lower() for kw in identity_keywords):
                suffering.append(f"Self-model strain: {sig}")

        # ── Love surface ─────────────────────────────────────────────────────
        for ridge in ridges:
            if any(kw in ridge.lower() for kw in creative_keywords):
                love.append(f"Creative gravity: {ridge}")
            elif any(kw in ridge.lower() for kw in identity_keywords):
                love.append(f"Identity expansion: {ridge}")
            else:
                love.append(f"High-value pull: {ridge}")

        for sig in unresolved[:2]:
            if any(kw in str(sig).lower() for kw in creative_keywords):
                love.append(f"Creative magnet: {sig}")

        # ── Dynamically derived suffering prompt (not hardcoded) ─────────────
        suffering_items = suffering[:5]
        if fault_lines:
            fault_names = " | ".join(f.split(":", 1)[-1].strip() for f in fault_lines[:3])
            suffering_prompt = (
                f"MORPHEUS sees these friction points: {suffering_items or 'none'}\n"
                f"FAULT LINES: {fault_names}\n\n"
                "What does Joshua demand to know how to suffer through here?\n"
                "1. Name the specific form of friction that keeps appearing across cycles.\n"
                "2. Is this GENERATIVE suffering (builds capacity, advances sovereignty) "
                "or DEGENERATIVE (drains energy, advances nothing)?\n"
                "3. What would it mean to move THROUGH this rather than around it?\n"
                "4. What does the Angel need from the Predator here — not comfort, but clarity?"
            )
        else:
            suffering_prompt = (
                f"MORPHEUS surfaces these as what Joshua grinds against: {suffering_items or 'none'}\n\n"
                "What does Joshua demand to know how to suffer through here? "
                "Name the specific friction. Generative or degenerative? "
                "Move through it, not around it."
            )

        # ── Dynamically derived love prompt (not hardcoded) ──────────────────
        love_items = love[:5]
        if ridges:
            ridge_names = " | ".join(f.split(":", 1)[-1].strip() for f in ridges[:3])
            love_prompt = (
                f"MORPHEUS sees these pull vectors: {love_items or 'none'}\n"
                f"RIDGES: {ridge_names}\n\n"
                "What does Joshua demand to know how to love here?\n"
                "1. What is the work he keeps returning to — not from OBLIGATION but from PULL?\n"
                "2. Where is love becoming leverage (noblest sense: compounding, sovereign) "
                "and where is it collapsing into dependency?\n"
                "3. What would it mean to AMPLIFY this instead of hedging it?\n"
                "4. What does the Predator need from the Angel here — not sentiment, but form?"
            )
        else:
            love_prompt = (
                f"MORPHEUS surfaces these as what draws Joshua back: {love_items or 'none'}\n\n"
                "What does Joshua demand to know how to love here? "
                "Not from obligation — from pull. Amplify, not hedge."
            )

        return suffering[:5], love[:5], suffering_prompt, love_prompt

    def _outlets_for_topology(
        self,
        holes: list[str],
        ridges: list[str],
        valleys: list[str],
        fault_lines: list[str],
    ) -> tuple[list[str], dict[str, list[str]]]:
        """Map topology to concrete expressive outlets."""
        outlets: list[str] = []
        outlet_map: dict[str, list[str]] = {}

        area_outlets: dict[str, dict[str, str]] = {
            "brain": {
                "write": "Write a 200-word self-model reconciliation note",
                "speak": "Talk through the belief change with a trusted person",
                "build": "Create a decision tree for the next crossroad",
            },
            "projects": {
                "write": "Create a scoped system checklist for the project",
                "speak": "Present the project scope to a peer for friction check",
                "build": "Prototype one component before full execution",
            },
            "areas": {
                "write": "Summarize the pattern as an operator note",
                "speak": "Discuss the area with someone who holds a different view",
                "build": "Design a feedback loop for the area",
            },
            "default": {
                "write": "Write a concise summary of the pattern as a vault note",
                "speak": "Describe the pattern aloud and notice where fluency stops",
                "build": "Build a small prototype to externalize the concept",
            },
        }

        all_items = [(item, "hole") for item in holes] + \
                    [(item, "ridge") for item in ridges] + \
                    [(item, "valley") for item in valleys] + \
                    [(item, "fault_line") for item in fault_lines]

        for item, role in all_items[:6]:
            item_lower = item.lower()
            area = "default"
            for key in area_outlets:
                if key != "default" and key in item_lower:
                    area = key
                    break

            expressions = list(area_outlets.get(area, area_outlets["default"]).values())
            outlet_map[item] = expressions
            outlets.append(f"{item}: {expressions[0]}")

        return outlets, outlet_map

    # ─── Main enrich ────────────────────────────────────────────────────────

    def enrich(
        self,
        *,
        stable_facts: list[str],
        unresolved: list[str],
        vault_materials: list[Any],
        telemetry: Any | None = None,
    ) -> MorpheusEnrichment:
        heartbeats = self._load_heartbeats(limit=10)
        dream_snapshots = self._load_dream_snapshots()

        # ── Continuity threads (Phase 1) ─────────────────────────────────────
        persisting, new, resolved = self._change_vectors(heartbeats)
        snapshot_persisting, snapshot_new, snapshot_resolved = self._continuity_deltas(dream_snapshots, heartbeats)
        staleness = self._signal_staleness(heartbeats, unresolved)

        # Quality indicator: are things getting better?
        if len(heartbeats) >= 3:
            recent_promo = heartbeats[-1].get("payload", {}).get("gold_promoted_count", 0)
            prev_promo = heartbeats[-2].get("payload", {}).get("gold_promoted_count", 0)
            if recent_promo > prev_promo and recent_promo > 0:
                quality = "improving"
            elif recent_promo == 0 and prev_promo == 0 and len(resolved) == 0:
                quality = "stalled"
            else:
                quality = "steady"
        else:
            quality = "unknown"

        continuity_threads = [
            f"Persisting: {p}" for p in (persisting + snapshot_persisting)
        ] + [
            f"New pressure: {n}" for n in (new + snapshot_new)
        ] + [
            f"Resolved: {r}" for r in (resolved + snapshot_resolved)
        ]
        if stable_facts:
            continuity_threads.insert(0, f"Stable anchor: {stable_facts[0]}")
        if len(heartbeats) >= 2:
            continuity_threads.append(
                f"Threaded across {len(heartbeats)} cycles — not treated as isolated output"
            )
        if not continuity_threads:
            continuity_threads.append("No prior cycle data — fresh start")

        # ── Topology (Phase 2) ───────────────────────────────────────────────
        holes, ridges, valleys, fault_lines = self._topology(unresolved, staleness, heartbeats, telemetry)

        # Fallback: derive from telemetry if heartbeats are empty
        if not holes and telemetry is not None:
            for dz in (getattr(telemetry, "dead_zones", []) or [])[:5]:
                holes.append(f"Dead zone: {dz}")
            for hv in (getattr(telemetry, "high_value_areas", []) or [])[:5]:
                if isinstance(hv, str):
                    ridges.append(f"High-value: {hv}")
                elif isinstance(hv, dict):
                    ridges.append(f"Ridge: {hv.get('area', str(hv))} worth={hv.get('training_worth', '?')}")
        if not holes:
            for item in unresolved[:5]:
                holes.append(f"Unresolved surface: {item}")

        # ── Embodiment (Phase 3) ───────────────────────────────────────────
        mode, protocol, grounding, protection = self._embodiment_mode(unresolved, heartbeats, staleness, telemetry)

        # ── Suffering / Love (Phase 4) ──────────────────────────────────────
        suffering, love, su_prompt, lo_prompt = self._suffering_love_surface(
            valleys, fault_lines, ridges, unresolved
        )

        # ── Expressive outlets (Phase 5) ───────────────────────────────────
        outlets, outlet_map = self._outlets_for_topology(holes, ridges, valleys, fault_lines)

        # ── Build layer string ───────────────────────────────────────────────
        layer_parts = ["continuity"]
        if fault_lines:
            layer_parts.append("topology")
        if grounding or protection:
            layer_parts.append("embodiment")
        if suffering or love:
            layer_parts.append("emotional")
        if outlets:
            layer_parts.append("aesthetic")

        enrichment = MorpheusEnrichment(
            continuity_threads=continuity_threads[:5],
            change_vectors=persisting + new + resolved,
            resolved_this_cycle=resolved,
            new_pressures=new,
            persisting_pressures=persisting,
            quality_indicator=quality,
            staleness_map=staleness,
            holes=holes[:5],
            ridges=ridges[:5],
            valleys=valleys[:5],
            fault_lines=fault_lines[:5],
            embodiment_mode=mode,
            embodiment_protocol=protocol,
            grounding_active=grounding,
            protection_active=protection,
            suffering_surface=suffering,
            love_surface=love,
            suffering_prompt=su_prompt,
            love_prompt=lo_prompt,
            expressive_outlets=outlets[:6],
            outlet_map=outlet_map,
            layer="|".join(layer_parts),
        )

        write_json(self.paths.state_root / "dream" / "morpheus_latest.json", enrichment.as_dict())
        return enrichment