from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import load_paths
from .graph_demotion import load_graph_demotion_review


@dataclass
class MorpheusEnrichment:
    layer: str
    continuity_threads: list[str] = field(default_factory=list)
    resolved_this_cycle: list[str] = field(default_factory=list)
    new_pressures: list[str] = field(default_factory=list)
    persisting_pressures: list[str] = field(default_factory=list)
    quality_indicator: str = "steady"
    holes: list[str] = field(default_factory=list)
    ridges: list[str] = field(default_factory=list)
    valleys: list[str] = field(default_factory=list)
    fault_lines: list[str] = field(default_factory=list)
    embodiment_mode: str = "observe"
    embodiment_protocol: str = ""
    grounding_active: bool = False
    protection_active: bool = False
    suffering_surface: list[str] = field(default_factory=list)
    suffering_prompt: str = ""
    love_surface: list[str] = field(default_factory=list)
    love_prompt: str = ""
    expressive_outlets: list[str] = field(default_factory=list)
    outlet_map: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "continuity_threads": self.continuity_threads,
            "resolved_this_cycle": self.resolved_this_cycle,
            "new_pressures": self.new_pressures,
            "persisting_pressures": self.persisting_pressures,
            "quality_indicator": self.quality_indicator,
            "holes": self.holes,
            "ridges": self.ridges,
            "valleys": self.valleys,
            "fault_lines": self.fault_lines,
            "embodiment_mode": self.embodiment_mode,
            "embodiment_protocol": self.embodiment_protocol,
            "grounding_active": self.grounding_active,
            "protection_active": self.protection_active,
            "suffering_surface": self.suffering_surface,
            "suffering_prompt": self.suffering_prompt,
            "love_surface": self.love_surface,
            "love_prompt": self.love_prompt,
            "expressive_outlets": self.expressive_outlets,
            "outlet_map": self.outlet_map,
        }


class MorpheusEngine:
    def __init__(self) -> None:
        self.paths = load_paths()

    @staticmethod
    def _normalize_area(value: str) -> str:
        text = str(value or "").replace("\\", "/").strip("/")
        if not text:
            return ""
        return text.split("/", 1)[0]

    @staticmethod
    def _parse_ts(raw: str | None) -> datetime:
        if not raw:
            return datetime.now(timezone.utc)
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return datetime.now(timezone.utc)

    def _recent_events(self, *, days: int = 7, limit: int = 1500) -> list[dict[str, Any]]:
        path = self.paths.state_root / "run_journal" / "events.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        window_start = datetime.now(timezone.utc) - timedelta(days=days)
        events: list[dict[str, Any]] = []
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            ts = self._parse_ts(str(payload.get("ts", "")))
            if ts >= window_start:
                events.append(payload)
        return events

    def _heartbeat_snapshots(self, events: list[dict[str, Any]]) -> list[list[str]]:
        snapshots: list[list[str]] = []
        for event in events:
            if event.get("type") != "kairos.heartbeat":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            actions = payload.get("next_actions")
            if isinstance(actions, list):
                snapshots.append([str(item) for item in actions])
        return snapshots

    def _change_vectors(
        self,
        unresolved: list[str],
        snapshots: list[list[str]],
    ) -> tuple[list[str], list[str], list[str], str, dict[str, int]]:
        current = [str(item) for item in unresolved]
        previous = snapshots[-1] if snapshots else []
        current_set = set(current)
        previous_set = set(previous)

        recurring_counts: dict[str, int] = {}
        for snapshot in snapshots:
            for item in snapshot:
                recurring_counts[item] = recurring_counts.get(item, 0) + 1
        for item in current:
            recurring_counts[item] = recurring_counts.get(item, 0) + 1

        resolved_this_cycle = [item for item in previous if item not in current_set][:5]
        new_pressures = [item for item in current if item not in previous_set][:5]
        persisting_pressures = [item for item in current if item in previous_set][:5]
        if not persisting_pressures:
            persisting_pressures = [item for item in current if recurring_counts.get(item, 0) >= 3][:5]

        if not current:
            quality = "stable"
        elif resolved_this_cycle and len(resolved_this_cycle) >= len(new_pressures):
            quality = "stabilizing"
        elif len(persisting_pressures) >= 3:
            quality = "stalled"
        else:
            quality = "active-pressure"
        return resolved_this_cycle, new_pressures, persisting_pressures, quality, recurring_counts

    def _derive_topology(
        self,
        *,
        telemetry: Any | None,
        vault_materials: list[Any],
        unresolved: list[str],
        recurring_counts: dict[str, int],
        events: list[dict[str, Any]],
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        ridges: list[str] = []
        if telemetry is not None:
            for item in getattr(telemetry, "train_targets", []) or []:
                area = str(item.get("area", "")).strip()
                if area and area not in ridges:
                    ridges.append(area)
        for material in vault_materials:
            area = str(getattr(material, "area", "")).strip()
            if area and area not in ridges:
                ridges.append(area)
            if len(ridges) >= 5:
                break

        holes: list[str] = []
        if telemetry is not None:
            for item in getattr(telemetry, "dead_zones", []) or []:
                area = str(item).strip()
                if area and area not in holes:
                    holes.append(area)

        valleys = [item for item, count in recurring_counts.items() if count >= 3][:5]
        if not valleys:
            valleys = unresolved[:3]

        # Derive ridge pressure from promoted paths in recent events
        promoted_roots: set[str] = set()
        for event in events:
            if event.get("type") != "kairos.gold.scored":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            for path in payload.get("promoted_paths", []) or []:
                promoted_roots.add(self._normalize_area(str(path)))
        for root in sorted(promoted_roots):
            if root and root not in ridges:
                ridges.append(root)

        for item in unresolved:
            if recurring_counts.get(item, 0) < 3:
                continue
            area = self._normalize_area(item)
            if area and area not in holes:
                holes.append(area)
        if not holes:
            holes = ["none"]
        if not ridges:
            ridges = ["none"]

        fault_lines: list[str] = []
        lowered_valleys = [item.lower() for item in valleys]
        for ridge in ridges:
            if ridge == "none":
                continue
            if any(ridge.lower() in valley for valley in lowered_valleys):
                fault_lines.append(f"{ridge}: high-value area under recurring pressure")
        for hole in holes:
            if hole == "none":
                continue
            if hole in ridges:
                fault_lines.append(f"{hole}: simultaneously high-value and neglected")
        if not fault_lines and valleys:
            fault_lines = valleys[:2]
        return holes[:5], ridges[:5], valleys[:5], fault_lines[:5]

    @staticmethod
    def _choose_embodiment_mode(
        *,
        unresolved: list[str],
        resolved: list[str],
        persisting: list[str],
        events: list[dict[str, Any]],
    ) -> tuple[str, str, bool, bool]:
        lowered = " ".join(unresolved).lower()
        economic_pressure = any(
            word in lowered for word in ("economic", "revenue", "income", "market", "pricing", "financial", "career")
        )

        recent_council = any(event.get("type") == "council.debate" for event in events[-30:])
        promotion_recent = 0
        for event in events[-50:]:
            if event.get("type") != "kairos.gold.scored":
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            promotion_recent += int(payload.get("gold_promoted_count", 0))

        if economic_pressure:
            return (
                "protection",
                "Switch to downside protection: cap commitments, preserve runway, and resolve one economic threat first.",
                False,
                True,
            )
        if len(unresolved) >= 6 or len(persisting) >= 4:
            return (
                "grounding",
                "Reduce context switching and convert strongest pressure into one durable writeback.",
                True,
                False,
            )
        if recent_council and unresolved:
            return (
                "consolidation",
                "Freeze new intake temporarily; integrate council synthesis into one execution track.",
                False,
                False,
            )
        if len(resolved) >= 2 and promotion_recent > 0:
            return (
                "integration",
                "Codify recent wins into repeatable protocol and preserve momentum.",
                False,
                False,
            )
        if len(unresolved) <= 2 and promotion_recent > 0:
            return (
                "expansion",
                "Use available headroom to expand one high-value ridge deliberately.",
                False,
                False,
            )
        return (
            "maintenance",
            "Maintain steady cadence, keep daily coherence checks, avoid unnecessary branching.",
            False,
            False,
        )

    @staticmethod
    def _surfaces(
        *,
        stable_facts: list[str],
        resolved: list[str],
        unresolved: list[str],
        ridges: list[str],
        valleys: list[str],
        fault_lines: list[str],
    ) -> tuple[list[str], str, list[str], str]:
        suffering_surface: list[str] = []
        for item in valleys + fault_lines + unresolved:
            if item not in suffering_surface:
                suffering_surface.append(item)
            if len(suffering_surface) >= 5:
                break
        if not suffering_surface:
            suffering_surface = ["No acute suffering surface detected this cycle."]
        suffering_prompt = (
            "Which pressure is generative suffering, and which is degenerative drag that must be removed?"
        )

        love_surface: list[str] = []
        for item in ridges + resolved + stable_facts:
            if item not in love_surface:
                love_surface.append(item)
            if len(love_surface) >= 5:
                break
        if not love_surface:
            love_surface = ["No clear love surface detected this cycle."]
        love_prompt = (
            "What thread keeps asking for deeper form, and how can it be embodied without fragmentation?"
        )
        return suffering_surface, suffering_prompt, love_surface, love_prompt

    @staticmethod
    def _outlets(
        holes: list[str],
        ridges: list[str],
        valleys: list[str],
        graph_review: dict[str, Any] | None = None,
    ) -> tuple[list[str], dict[str, list[str]]]:
        outlets: list[str] = []
        outlet_map: dict[str, list[str]] = {}

        for hole in holes:
            if hole == "none":
                continue
            outlets.append(f"{hole}: write one bridge note connecting gap to active project.")
            outlet_map.setdefault(hole, ["writing", "mapping"])
        for ridge in ridges:
            if ridge == "none":
                continue
            outlets.append(f"{ridge}: crystallize working pattern into reusable operator protocol.")
            outlet_map.setdefault(ridge, ["strategy", "documentation"])
        for valley in valleys:
            if valley == "none":
                continue
            key = valley[:64]
            outlets.append(f"{key}: run 15-minute after-action review with one corrective move.")
            outlet_map.setdefault(key, ["reflection", "execution"])
        if graph_review:
            family = str(graph_review.get("primary_hotspot_family") or "graph-demotion").strip() or "graph-demotion"
            mode = str(graph_review.get("recommended_next_apply_mode") or "mixed-family").strip() or "mixed-family"
            next_action = str(graph_review.get("recommended_next_action") or "").strip()
            label = f"{family}: execute reviewed {mode} graph-demotion follow-up."
            if next_action:
                label = f"{family}: {next_action}"
            outlets.append(label)
            outlet_map.setdefault(family, ["graph-demotion", "execution"])

        if not outlets:
            outlets = ["Convert strongest continuity thread into one durable Otto-Realm artifact."]
        return outlets[:8], outlet_map

    def enrich(
        self,
        *,
        stable_facts: list[str],
        unresolved: list[str],
        vault_materials: list[Any],
        telemetry: Any | None = None,
    ) -> MorpheusEnrichment:
        events = self._recent_events(days=7)
        graph_review = load_graph_demotion_review(self.paths)
        snapshots = self._heartbeat_snapshots(events)
        (
            resolved_this_cycle,
            new_pressures,
            persisting_pressures,
            quality_indicator,
            recurring_counts,
        ) = self._change_vectors(unresolved=unresolved, snapshots=snapshots)
        if graph_review:
            graph_action = str(graph_review.get("recommended_next_action") or "").strip()
            if graph_action and graph_action not in persisting_pressures:
                persisting_pressures = [graph_action, *persisting_pressures][:5]

        continuity_threads = list(dict.fromkeys(stable_facts[:3] + persisting_pressures[:2] + resolved_this_cycle[:2]))[:6]
        if graph_review:
            family = str(graph_review.get("primary_hotspot_family") or "graph-demotion").strip() or "graph-demotion"
            mode = str(graph_review.get("recommended_next_apply_mode") or "mixed-family").strip() or "mixed-family"
            graph_thread = f"Graph demotion track: {mode} via {family}"
            continuity_threads = list(dict.fromkeys([graph_thread] + continuity_threads))[:6]
        if not continuity_threads:
            continuity_threads = ["No major continuity shifts detected."]

        holes, ridges, valleys, fault_lines = self._derive_topology(
            telemetry=telemetry,
            vault_materials=vault_materials,
            unresolved=unresolved,
            recurring_counts=recurring_counts,
            events=events,
        )
        if graph_review:
            family = str(graph_review.get("primary_hotspot_family") or "graph-demotion").strip() or "graph-demotion"
            next_action = str(graph_review.get("recommended_next_action") or "").strip()
            if family not in ridges:
                ridges = [family, *ridges][:5]
            if next_action and next_action not in valleys:
                valleys = [next_action, *valleys][:5]
            tension = f"{family}: reviewed graph hotspot awaiting bounded follow-up"
            if tension not in fault_lines:
                fault_lines = [tension, *fault_lines][:5]
        embodiment_mode, embodiment_protocol, grounding_active, protection_active = self._choose_embodiment_mode(
            unresolved=unresolved,
            resolved=resolved_this_cycle,
            persisting=persisting_pressures,
            events=events,
        )
        suffering, suffering_prompt, love, love_prompt = self._surfaces(
            stable_facts=stable_facts,
            resolved=resolved_this_cycle,
            unresolved=unresolved,
            ridges=ridges,
            valleys=valleys,
            fault_lines=fault_lines,
        )
        outlets, outlet_map = self._outlets(holes, ridges, valleys, graph_review)

        return MorpheusEnrichment(
            layer="continuity-topology",
            continuity_threads=continuity_threads or ["No major continuity shifts detected."],
            resolved_this_cycle=resolved_this_cycle,
            new_pressures=new_pressures,
            persisting_pressures=persisting_pressures,
            quality_indicator=quality_indicator,
            holes=holes,
            ridges=ridges,
            valleys=valleys or ["none"],
            fault_lines=fault_lines,
            embodiment_mode=embodiment_mode,
            embodiment_protocol=embodiment_protocol,
            grounding_active=grounding_active,
            protection_active=protection_active,
            suffering_surface=suffering,
            suffering_prompt=suffering_prompt,
            love_surface=love,
            love_prompt=love_prompt,
            expressive_outlets=outlets,
            outlet_map=outlet_map,
        )
