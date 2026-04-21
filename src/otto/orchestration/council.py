from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..logging_utils import append_jsonl
from ..state import now_iso


@dataclass
class CouncilTrigger:
    trigger_id: str
    category: str
    weakness: str
    severity: str
    evidence: list[str]
    recommended_action: str


@dataclass
class PersonaProfile:
    name: str
    domain: str
    heuristic: str
    stance_template: str
    strongest_argument: str
    limitation: str


@dataclass
class PersonaPair:
    person_a: PersonaProfile
    person_b: PersonaProfile
    tension_axis: str


@dataclass
class CouncilDebate:
    ts: str
    trigger: CouncilTrigger
    pair: PersonaPair
    synthesis: str
    next_action: str

    def to_markdown(self) -> str:
        a = self.pair.person_a
        b = self.pair.person_b
        evidence_lines = "\n".join(f"- {item}" for item in self.trigger.evidence)
        return "\n".join(
            [
                f"### Council Debate — {self.trigger.category}",
                f"[WEAKNESS]: {self.trigger.weakness}",
                "[EVIDENCE]:",
                evidence_lines or "- none",
                f"[PERSONA A]: {a.name}, {a.domain}, {a.heuristic}",
                f"  -> Position: {a.stance_template.format(weakness=self.trigger.weakness)}",
                f"  -> Strongest argument: {a.strongest_argument}",
                f"  -> Limitation: {a.limitation}",
                f"[PERSONA B]: {b.name}, {b.domain}, {b.heuristic}",
                f"  -> Position: {b.stance_template.format(weakness=self.trigger.weakness)}",
                f"  -> Strongest argument: {b.strongest_argument}",
                f"  -> Limitation: {b.limitation}",
                f"[SYNTHESIS]: {self.synthesis}",
                f"[NEXT ACTION]: {self.next_action}",
            ]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "trigger_category": self.trigger.category,
            "trigger": self.trigger.__dict__,
            "pair": {
                "person_a": self.pair.person_a.__dict__,
                "person_b": self.pair.person_b.__dict__,
                "tension_axis": self.pair.tension_axis,
            },
            "synthesis": self.synthesis,
            "next_action": self.next_action,
        }


class CouncilEngine:
    def __init__(self) -> None:
        self.paths = load_paths()
        self._registry = {
            "cognitive_weakness": PersonaPair(
                person_a=PersonaProfile(
                    name="Tiago Forte",
                    domain="systems design",
                    heuristic="externalize structure and reduce ambiguity",
                    stance_template="Tiago would turn '{weakness}' into a clearer container and explicit workflow so it stops leaking attention.",
                    strongest_argument="A stable system reduces repeated failure by making decisions legible and reviewable.",
                    limitation="This can over-systematize if the real issue is lack of constraint rather than lack of structure.",
                ),
                person_b=PersonaProfile(
                    name="Jason Fried",
                    domain="product execution",
                    heuristic="reduce scope and enforce hard constraints",
                    stance_template="Jason would treat '{weakness}' as a scoping problem and cut the work down until completion becomes trivial.",
                    strongest_argument="Constraint creates momentum faster than architectural elaboration.",
                    limitation="Too much reduction can underspecify work that genuinely needs deeper system design.",
                ),
                tension_axis="structure vs. constraint",
            ),
            "identity_incoherence": PersonaPair(
                person_a=PersonaProfile(
                    name="Julia Galef",
                    domain="epistemics",
                    heuristic="update beliefs by calibration and reality contact",
                    stance_template="Julia would ask Joshua to test whether '{weakness}' is a self-story mismatch and revise the story to fit evidence.",
                    strongest_argument="Calibration keeps the self-model from drifting into comforting fiction.",
                    limitation="Calibration alone does not create decisive action if the environment still rewards avoidance.",
                ),
                person_b=PersonaProfile(
                    name="Charlie Munger",
                    domain="decision making",
                    heuristic="invert failure and remove stupidity first",
                    stance_template="Charlie would frame '{weakness}' as something to subtract by eliminating the recurring bad pattern before adding new ideals.",
                    strongest_argument="Via negativa often resolves identity drift faster than aspirational reframing.",
                    limitation="Pure subtraction can become too blunt for emotionally loaded self-model conflicts.",
                ),
                tension_axis="update vs. subtract",
            ),
            "economic_threat": PersonaPair(
                person_a=PersonaProfile(
                    name="Balaji Srinivasan",
                    domain="economic strategy",
                    heuristic="increase sovereignty through leverage and exit options",
                    stance_template="Balaji would respond to '{weakness}' by increasing leverage, optionality, and economic independence.",
                    strongest_argument="Economic fragility usually improves when options widen and dependence narrows.",
                    limitation="This can overshoot into strategic abstraction if the immediate cashflow problem is concrete.",
                ),
                person_b=PersonaProfile(
                    name="Michael Nielsen",
                    domain="research capital",
                    heuristic="compound trust and deep capability over time",
                    stance_template="Michael would answer '{weakness}' by building a slower but more durable asset base grounded in hard-to-copy work.",
                    strongest_argument="Deep compounding creates resilience that survives hype cycles.",
                    limitation="Depth-first moves can be too slow when the present burn rate is the immediate threat.",
                ),
                tension_axis="velocity vs. depth",
            ),
            "epistemic_gap": PersonaPair(
                person_a=PersonaProfile(
                    name="David Heinemeier Hansson",
                    domain="product philosophy",
                    heuristic="simplify and cut needless complexity",
                    stance_template="DHH would treat '{weakness}' as a sign that the model should be simplified until action is obvious.",
                    strongest_argument="Simplicity exposes the real decision and prevents analysis sprawl.",
                    limitation="Some domains really are complex, and oversimplification can hide important second-order effects.",
                ),
                person_b=PersonaProfile(
                    name="Nassim Taleb",
                    domain="risk thinking",
                    heuristic="respect variability and build antifragility",
                    stance_template="Taleb would answer '{weakness}' by stress-testing assumptions and designing around volatility instead of eliminating it.",
                    strongest_argument="Robustness comes from modeling uncertainty rather than pretending it is absent.",
                    limitation="Too much antifragility framing can make ordinary prioritization feel more exotic than it is.",
                ),
                tension_axis="subtraction vs. absorption",
            ),
            "predicate_qua_angel": PersonaPair(
                person_a=PersonaProfile(
                    name="Marcus Aurelius",
                    domain="stoic sovereign action",
                    heuristic="align every action with the rational order of the whole",
                    stance_template="Marcus would respond to '{weakness}' by asking: does this action serve my highest function as a rational, generative being — or am I reacting from fear?",
                    strongest_argument="The stoic framework demands that fear-driven decisions be immediately reframed as either rational choices or eliminated.",
                    limitation="This can become moral abstraction that avoids concrete economic decisions.",
                ),
                person_b=PersonaProfile(
                    name="Cormac McCarthy",
                    domain="dark clarity and brutal efficiency",
                    heuristic="cut everything that does not serve the mission",
                    stance_template="Cormac would treat '{weakness}' as a sign that Joshua is carrying weight that serves no one — and must be dropped immediately.",
                    strongest_argument="Brutal simplification reveals what is actually load-bearing. Non-essential commitments are the root of predicate failure.",
                    limitation="This can become nihilism — cutting things that have genuine long-term value because they feel heavy in the moment.",
                ),
                tension_axis="clarity vs. courage",
            ),
        }

    def _trigger_history_path(self) -> Path:
        return self.paths.state_root / "run_journal" / "council_trigger_history.jsonl"

    def _load_trigger_history(self) -> list[dict]:
        path = self._trigger_history_path()
        if not path.exists():
            return []
        events: list[dict] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _count_recent_fires(self, category: str, history: list[dict], days: int = 30) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return sum(
            1 for e in history
            if e.get("category") == category and str(e.get("ts", "")) >= cutoff
        )

    def _record_detection(self, category: str) -> None:
        """Record a trigger detection event (fires even if threshold not yet met)."""
        path = self._trigger_history_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": now_iso(), "category": category}) + "\n")

    def detect_triggers(
        self,
        *,
        gold_scores: list[Any],
        unresolved_signals: list[dict[str, Any]],
        top_folders: list[dict[str, Any]],
        contradictions: list[Any],
        staleness_map: dict[str, int] | None = None,  # from morpheus
    ) -> list[CouncilTrigger]:
        history = self._load_trigger_history()
        triggers: list[CouncilTrigger] = []

        # cognitive_weakness: spec requires ≥3 recurrences before council fires
        if len(unresolved_signals) >= 5 or any(float(item.get("risk_score", 0)) >= 4.0 for item in top_folders):
            fires = self._count_recent_fires("cognitive_weakness", history)
            self._record_detection("cognitive_weakness")
            # Dual gating: history fires OR morpheus staleness ≥3 per signal
            has_stale_signal = staleness_map and any(c >= 3 for c in staleness_map.values())
            if fires >= 3 or has_stale_signal:
                severity = "high" if len(unresolved_signals) >= 8 else "medium"
                evidence = [f"{len(unresolved_signals)} unresolved signals ({fires}× history, ≥3 required)"]
                if has_stale_signal:
                    stale_signals = [(p, c) for p, c in (staleness_map or {}).items() if c >= 3]
                    evidence.append(f"Stale signals (≥3 cycles): {len(stale_signals)} — {[p for p, _ in stale_signals[:3]]}")
                evidence.extend(f"{item['folder']} risk={item['risk_score']}" for item in top_folders[:2])
                triggers.append(
                    CouncilTrigger(
                        trigger_id=f"cognitive-{now_iso()}",
                        category="cognitive_weakness",
                        weakness="repeated metadata and execution friction is slowing reliable progress",
                        severity=severity,
                        evidence=evidence,
                        recommended_action="Reduce scope and repair the highest-risk folder before expanding the loop",
                    )
                )

        # identity_incoherence: fires at ≥3 detections per spec
        if any("self_model" in str(sig.get("note_path", "")).lower() for sig in unresolved_signals):
            fires = self._count_recent_fires("identity_incoherence", history)
            self._record_detection("identity_incoherence")
            if fires >= 3:
                triggers.append(
                    CouncilTrigger(
                        trigger_id=f"identity-{now_iso()}",
                        category="identity_incoherence",
                        weakness="the self-model is part of the chaos surface instead of a stable orientation aid",
                        severity="medium",
                        evidence=[
                            "Otto-Realm\\Brain\\self_model.md is still unresolved in the current signal set",
                            f"Detected {fires}× — pattern is structural, not incidental",
                        ],
                        recommended_action="Repair the self-model note and reconcile it with measured behavior",
                    )
                )

        # economic_threat: fires immediately — spec says cannot be suppressed
        economic_scores = [
            score for score in gold_scores
            if "economic" in score.primary_claim.lower() or "career" in score.primary_claim.lower()
        ]
        if economic_scores:
            self._record_detection("economic_threat")
            triggers.append(
                CouncilTrigger(
                    trigger_id=f"economic-{now_iso()}",
                    category="economic_threat",
                    weakness="economic or career leverage signals need explicit prioritization",
                    severity="high",
                    evidence=[f"{len(economic_scores)} Gold signal(s) flag economic or career leverage — immediate response required"],
                    recommended_action="Treat economic signals as first-class constraints in the next action queue",
                )
            )

        # epistemic_gap: fires at ≥3 detections or ≥3 contradictions per cycle (override allowed)
        if contradictions:
            fires = self._count_recent_fires("epistemic_gap", history)
            self._record_detection("epistemic_gap")
            if fires >= 3 or len(contradictions) >= 3:
                triggers.append(
                    CouncilTrigger(
                        trigger_id=f"epistemic-{now_iso()}",
                        category="epistemic_gap",
                        weakness="new evidence conflicts with existing memory and requires reconciliation",
                        severity="high" if len(contradictions) >= 3 else "medium",
                        evidence=[
                            f"{len(contradictions)} contradiction signal(s) emitted this cycle",
                            f"Epistemic gap detected {fires}× — reconciliation overdue",
                        ],
                        recommended_action="Run a contradiction audit before further synthesis",
                    )
                )

        # predicate_qua_angel deviation: falls below the Predator qua Angel standard
        # Fires when: repeated fear-driven pattern OR acute deviation (economic threat + metadata friction)
        # Spec §4.3: Predator only (extraction, no regeneration) vs Angel only (idealism, no execution)
        economic_count = sum(
            1 for s in unresolved_signals
            if any(kw in str(s.get("note_path", "")).lower() for kw in ["economic", "career", "revenue", "burnout"])
        )
        has_meta_repair = any(float(f.get("risk_score", 0)) >= 4.0 for f in top_folders[:3])
        decision_markers = ["project", "launch", "start", "hire", "spend", "commit"]
        has_decision_pressure = any(
            any(marker in str(s.get("note_path", "")).lower() for marker in decision_markers)
            for s in unresolved_signals
        )
        fear_markers = ["avoid", "afraid", "stuck", "freeze", "hesitate", "delay"]
        fear_pressure = any(
            any(marker in str(s.get("primary_claim", "")).lower() for marker in fear_markers)
            or any(marker in str(s.get("note_path", "")).lower() for marker in fear_markers)
            for s in unresolved_signals
        )
        structural_drag = sum(1 for f in top_folders if float(f.get("risk_score", 0)) >= 10.0)

        fires = self._count_recent_fires("predicate_qua_angel", history)
        # Acute mode: economic + metadata + decision = immediate trigger
        acute_mode = economic_count >= 2 and has_meta_repair and has_decision_pressure
        # Chronic mode: 3+ fires or repeated structural drag = always trigger
        chronic_mode = fires >= 3 or structural_drag >= 2
        # Soft failure mode: fear pressure plus execution friction, even if not acute
        soft_mode = fear_pressure and has_meta_repair and has_decision_pressure and fires >= 3

        if acute_mode or chronic_mode or soft_mode:
            self._record_detection("predicate_qua_angel")
            mode_label = "acute" if acute_mode else "chronic" if chronic_mode else "soft"
            triggers.append(
                CouncilTrigger(
                    trigger_id=f"predator-{now_iso()}",
                    category="predicate_qua_angel",
                    weakness=(
                        "Falling below Predator qua Angel standard. "
                        + (
                            "Reactive decisions driven by fear + economic pressure + metadata friction."
                            if acute_mode
                            else "Recurring pattern of Angel-only behavior without Predator execution."
                            if chronic_mode
                            else "Fear pressure is present, but execution remains underspecified."
                        )
                    ),
                    severity="high",
                    evidence=[
                        f"[{mode_label}] fires={fires}×",
                        f"{economic_count} unresolved economic/career signals",
                        f"metadata_friction={has_meta_repair}",
                        f"decision_pressure={has_decision_pressure}",
                        f"fear_pressure={fear_pressure}",
                    ],
                    recommended_action=(
                        "Predator qua Angel: every decision must serve sovereignty, compound leverage, "
                        "and generative capacity. Cut load-bearing weight. Write one explicit exit criterion per active commitment."
                    ),
                )
            )
        return triggers

    def spawn_persona_pair(self, trigger: CouncilTrigger) -> PersonaPair:
        return self._registry.get(trigger.category, self._registry["cognitive_weakness"])

    def run_council_debate(self, trigger: CouncilTrigger) -> CouncilDebate:
        pair = self.spawn_persona_pair(trigger)
        debate = CouncilDebate(
            ts=now_iso(),
            trigger=trigger,
            pair=pair,
            synthesis=(
                f"Use the {pair.tension_axis} tension as a bounded decision tool: start with the smallest concrete move "
                f"that addresses '{trigger.weakness}', but preserve enough structure to learn from the outcome."
            ),
            next_action=f"{now_iso()} — {trigger.recommended_action}",
        )
        append_jsonl(self.paths.state_root / "run_journal" / "council_debates.jsonl", debate.as_dict())
        return debate
