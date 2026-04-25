from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import load_paths
from ..logging_utils import append_jsonl, get_logger
from ..state import now_iso, write_json
from .kairos_gold import KairosGoldResult


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


@dataclass
class CouncilTrigger:
    trigger_category: str
    severity: str
    diagnosis: str
    evidence: list[str] = field(default_factory=list)
    recurrence_count: int = 0
    forced: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "trigger_category": self.trigger_category,
            "severity": self.severity,
            "diagnosis": self.diagnosis,
            "evidence": self.evidence,
            "recurrence_count": self.recurrence_count,
            "forced": self.forced,
        }


@dataclass
class CouncilPersona:
    name: str
    domain: str
    core_heuristic: str
    position: str
    strongest_argument: str
    limitation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "core_heuristic": self.core_heuristic,
            "position": self.position,
            "strongest_argument": self.strongest_argument,
            "limitation": self.limitation,
        }


@dataclass
class CouncilActionCandidate:
    action: str
    priority: int = 0
    source: str = "unresolved"
    reason: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "priority": self.priority,
            "source": self.source,
            "reason": self.reason,
            "context": self.context,
        }


@dataclass
class CouncilDebate:
    ts: str
    trigger_category: str
    recurrence_count: int
    weakness: str
    evidence: list[str]
    persona_a: CouncilPersona
    persona_b: CouncilPersona
    synthesis: str
    next_action: str
    action_source: str = "unresolved"
    action_reason: str = ""
    action_context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "trigger_category": self.trigger_category,
            "recurrence_count": self.recurrence_count,
            "weakness": self.weakness,
            "evidence": self.evidence,
            "persona_a": self.persona_a.as_dict(),
            "persona_b": self.persona_b.as_dict(),
            "synthesis": self.synthesis,
            "next_action": self.next_action,
            "action_source": self.action_source,
            "action_reason": self.action_reason,
            "action_context": self.action_context,
        }

    def to_markdown(self) -> str:
        lines = [
            f"[WEAKNESS]: {self.weakness}",
            "[EVIDENCE]:",
        ]
        lines.extend([f"- {item}" for item in self.evidence] or ["- none"])
        lines.extend(
            [
                f"[PERSONA A]: {self.persona_a.name} ({self.persona_a.domain})",
                f"  -> Position: {self.persona_a.position}",
                f"  -> Strongest argument: {self.persona_a.strongest_argument}",
                f"  -> Limitation: {self.persona_a.limitation}",
                f"[PERSONA B]: {self.persona_b.name} ({self.persona_b.domain})",
                f"  -> Position: {self.persona_b.position}",
                f"  -> Strongest argument: {self.persona_b.strongest_argument}",
                f"  -> Limitation: {self.persona_b.limitation}",
                f"[SYNTHESIS]: {self.synthesis}",
                f"[NEXT ACTION]: {self.next_action}",
                f"[ACTION SOURCE]: {self.action_source}",
            ]
        )
        return "\n".join(lines)


@dataclass
class CouncilRunResult:
    ts: str
    triggers_detected: list[CouncilTrigger] = field(default_factory=list)
    debates: list[CouncilDebate] = field(default_factory=list)

    @property
    def triggered(self) -> bool:
        return bool(self.debates)

    @property
    def trigger_count(self) -> int:
        return len(self.debates)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "triggered": self.triggered,
            "trigger_count": self.trigger_count,
            "triggers_detected": [item.as_dict() for item in self.triggers_detected],
            "debates": [item.as_dict() for item in self.debates],
        }


class CouncilEngine:
    _PERSONA_MAP: dict[str, tuple[CouncilPersona, CouncilPersona]] = {
        "cognitive_weakness": (
            CouncilPersona(
                name="Julia Galef",
                domain="epistemic calibration",
                core_heuristic="Update beliefs early and often from disconfirming evidence.",
                position="Run faster feedback loops and write explicit falsification criteria.",
                strongest_argument="Calibration compounds faster than more effort.",
                limitation="Can underweight execution urgency.",
            ),
            CouncilPersona(
                name="Charlie Munger",
                domain="inversion and decision hygiene",
                core_heuristic="Avoid stupidity first, then optimize.",
                position="Install hard stop-rules before starting new loops.",
                strongest_argument="Removing recurring failure modes unlocks net progress.",
                limitation="Can over-compress experimentation windows.",
            ),
        ),
        "economic_threat": (
            CouncilPersona(
                name="Balaji Srinivasan",
                domain="economic sovereignty",
                core_heuristic="Build optionality and resilient distribution early.",
                position="Prioritize assets and channels that reduce single-point fragility.",
                strongest_argument="Survival runway buys strategic freedom.",
                limitation="Can bias toward speed over craft.",
            ),
            CouncilPersona(
                name="Michael Nielsen",
                domain="deep compounding work",
                core_heuristic="Invest in durable intellectual capital.",
                position="Protect deep work blocks and publish compounding artifacts.",
                strongest_argument="High-trust output compounds long-term leverage.",
                limitation="Can under-react to immediate cash pressure.",
            ),
        ),
        "identity_incoherence": (
            CouncilPersona(
                name="Tiago Forte",
                domain="knowledge operations",
                core_heuristic="Externalize commitments into trustworthy systems.",
                position="Make identity claims operational via explicit system constraints.",
                strongest_argument="Systems convert aspiration into repeatable behavior.",
                limitation="System overhead can rise quickly.",
            ),
            CouncilPersona(
                name="Jason Fried",
                domain="constraint execution",
                core_heuristic="Reduce scope until shipping becomes inevitable.",
                position="Use smaller scopes with fixed time windows.",
                strongest_argument="Constraint clarity exposes false identity claims quickly.",
                limitation="Can miss broader strategic abstractions.",
            ),
        ),
        "epistemic_gap": (
            CouncilPersona(
                name="Julia Galef",
                domain="epistemic scouting",
                core_heuristic="Map uncertainty before choosing confidence.",
                position="Write what is unknown and define one bounded research loop.",
                strongest_argument="Clear uncertainty maps prevent fake confidence.",
                limitation="Does not automatically choose execution sequencing.",
            ),
            CouncilPersona(
                name="Nassim Taleb",
                domain="antifragile risk",
                core_heuristic="Prefer barbell strategies under uncertainty.",
                position="Avoid irreversible bets while learning.",
                strongest_argument="Antifragile posture limits downside from unknowns.",
                limitation="Can underweight steady incremental gains.",
            ),
        ),
        "predator_angel_deviation": (
            CouncilPersona(
                name="David Heinemeier Hansson",
                domain="calm execution",
                core_heuristic="Do fewer things with stronger finishing quality.",
                position="Collapse concurrent tracks and finish one track fully.",
                strongest_argument="Calm systems reduce reactive drift.",
                limitation="Can be too conservative in high-opportunity windows.",
            ),
            CouncilPersona(
                name="Nassim Taleb",
                domain="stress navigation",
                core_heuristic="Design for volatility, not comfort.",
                position="Add downside guards, then lean into asymmetric upside.",
                strongest_argument="Volatility-aware moves preserve optionality.",
                limitation="Can introduce complexity if applied indiscriminately.",
            ),
        ),
    }

    def __init__(self) -> None:
        self.paths = load_paths()
        self.logger = get_logger("otto.council")
        self.history_path = self.paths.state_root / "run_journal" / "council_trigger_history.jsonl"
        self.debate_path = self.paths.state_root / "run_journal" / "council_debates.jsonl"

    @staticmethod
    def _looks_economic(text: str) -> bool:
        lowered = text.lower()
        keywords = (
            "economic",
            "revenue",
            "income",
            "market",
            "pricing",
            "financial",
            "burn rate",
            "career",
        )
        return any(word in lowered for word in keywords)

    def _load_history(self, limit: int = 1000) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        lines = self.history_path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        rows: list[dict[str, Any]] = []
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def _recurrence_count(self, category: str, now: datetime) -> int:
        window_start = now - timedelta(days=30)
        count = 0
        for row in self._load_history():
            if str(row.get("trigger_category", "")) != category:
                continue
            ts = _parse_ts(str(row.get("ts", "")))
            if ts >= window_start:
                count += 1
        return count

    def _candidate_triggers(
        self,
        *,
        gold_result: KairosGoldResult,
        unresolved: list[str],
    ) -> list[CouncilTrigger]:
        unresolved_count = len(unresolved)
        contradictions_count = len(gold_result.contradictions)
        candidates: list[CouncilTrigger] = []

        if unresolved_count >= 5 or gold_result.noise_count >= 5:
            candidates.append(
                CouncilTrigger(
                    trigger_category="cognitive_weakness",
                    severity="high",
                    diagnosis="Recurring unresolved load indicates execution pattern drift.",
                    evidence=[
                        f"unresolved_count={unresolved_count}",
                        f"noise_count={gold_result.noise_count}",
                    ],
                )
            )

        economic_hits = [
            item for item in gold_result.contradictions
            if self._looks_economic(item.primary_claim) or self._looks_economic(item.conflicting_excerpt)
        ]
        unresolved_economic = [item for item in unresolved if self._looks_economic(item)]
        if economic_hits or unresolved_economic:
            candidates.append(
                CouncilTrigger(
                    trigger_category="economic_threat",
                    severity="critical",
                    diagnosis="Economic fragility signals remain unresolved.",
                    evidence=[
                        f"economic_contradictions={len(economic_hits)}",
                        f"economic_unresolved={len(unresolved_economic)}",
                    ],
                    forced=True,
                )
            )

        if contradictions_count >= 2:
            candidates.append(
                CouncilTrigger(
                    trigger_category="identity_incoherence",
                    severity="high",
                    diagnosis="Vault claims and current signals diverge.",
                    evidence=[f"contradictions={contradictions_count}"],
                )
            )

        if gold_result.gold_promoted_count == 0 and unresolved_count >= 3:
            candidates.append(
                CouncilTrigger(
                    trigger_category="epistemic_gap",
                    severity="medium",
                    diagnosis="No Gold promotion while unresolved stack persists.",
                    evidence=[
                        f"gold_promoted_count={gold_result.gold_promoted_count}",
                        f"unresolved_count={unresolved_count}",
                    ],
                )
            )

        if gold_result.kairos_score < 5.8 and unresolved_count >= 4:
            candidates.append(
                CouncilTrigger(
                    trigger_category="predator_angel_deviation",
                    severity="medium",
                    diagnosis="Signal quality indicates reactive drift from desired standard.",
                    evidence=[f"kairos_score={gold_result.kairos_score:.2f}"],
                )
            )
        return candidates

    def _build_debate(
        self,
        trigger: CouncilTrigger,
        unresolved: list[str],
        action_candidates: list[CouncilActionCandidate | dict[str, Any]] | None = None,
    ) -> CouncilDebate:
        pair = self._PERSONA_MAP.get(trigger.trigger_category)
        if pair is None:
            pair = self._PERSONA_MAP["cognitive_weakness"]
        persona_a, persona_b = pair
        action_candidate = self._pick_action_candidate(unresolved, action_candidates)
        next_action = action_candidate.action
        if action_candidate.source == "graph_demotion_review":
            mode = str(action_candidate.context.get("recommended_next_apply_mode") or "mixed-family").strip() or "mixed-family"
            family = str(action_candidate.context.get("primary_hotspot_family") or "graph-demotion").strip() or "graph-demotion"
            synthesis = (
                f"Use reviewed graph-demotion evidence to run one bounded OpenClaw fetch, "
                f"then apply the next {mode} batch around {family}."
            )
        else:
            synthesis = (
                "Adopt constraint-first execution with explicit anti-fragility guardrails; "
                "ship one bounded action before widening scope."
            )
        return CouncilDebate(
            ts=now_iso(),
            trigger_category=trigger.trigger_category,
            recurrence_count=trigger.recurrence_count,
            weakness=trigger.diagnosis,
            evidence=trigger.evidence[:5],
            persona_a=persona_a,
            persona_b=persona_b,
            synthesis=synthesis,
            next_action=next_action,
            action_source=action_candidate.source,
            action_reason=action_candidate.reason,
            action_context=action_candidate.context,
        )

    @staticmethod
    def _normalize_action_candidates(
        action_candidates: list[CouncilActionCandidate | dict[str, Any]] | None,
    ) -> list[CouncilActionCandidate]:
        normalized: list[CouncilActionCandidate] = []
        for item in action_candidates or []:
            if isinstance(item, CouncilActionCandidate):
                if item.action.strip():
                    normalized.append(item)
                continue
            if not isinstance(item, dict):
                continue
            action = str(item.get("action") or "").strip()
            if not action:
                continue
            context = item.get("context") if isinstance(item.get("context"), dict) else {}
            try:
                priority = int(item.get("priority", 0))
            except (TypeError, ValueError):
                priority = 0
            normalized.append(
                CouncilActionCandidate(
                    action=action,
                    priority=priority,
                    source=str(item.get("source") or "unresolved"),
                    reason=str(item.get("reason") or ""),
                    context=dict(context),
                )
            )
        normalized.sort(key=lambda candidate: (-candidate.priority, candidate.source, candidate.action))
        return normalized

    def _pick_action_candidate(
        self,
        unresolved: list[str],
        action_candidates: list[CouncilActionCandidate | dict[str, Any]] | None = None,
    ) -> CouncilActionCandidate:
        normalized = self._normalize_action_candidates(action_candidates)
        if normalized:
            return normalized[0]
        if unresolved:
            return CouncilActionCandidate(
                action=unresolved[0],
                priority=0,
                source="unresolved",
                reason="fallback-first-unresolved",
            )
        return CouncilActionCandidate(
            action="Write one bounded action in Otto-Realm/Heartbeats before next cycle.",
            priority=0,
            source="fallback",
            reason="no-unresolved-actions",
        )

    def run(
        self,
        *,
        gold_result: KairosGoldResult,
        unresolved: list[str],
        action_candidates: list[CouncilActionCandidate | dict[str, Any]] | None = None,
    ) -> CouncilRunResult:
        now = datetime.now(timezone.utc)
        candidates = self._candidate_triggers(gold_result=gold_result, unresolved=unresolved)
        fired: list[CouncilTrigger] = []
        for trigger in candidates:
            trigger.recurrence_count = self._recurrence_count(trigger.trigger_category, now) + 1
            append_jsonl(
                self.history_path,
                {
                    "ts": now_iso(),
                    "trigger_category": trigger.trigger_category,
                    "severity": trigger.severity,
                    "diagnosis": trigger.diagnosis,
                    "evidence": trigger.evidence,
                    "forced": trigger.forced,
                    "recurrence_count": trigger.recurrence_count,
                },
            )
            if trigger.forced or trigger.recurrence_count >= 3:
                fired.append(trigger)

        debates = [self._build_debate(trigger, unresolved, action_candidates) for trigger in fired]
        for debate in debates:
            append_jsonl(self.debate_path, debate.as_dict())

        result = CouncilRunResult(ts=now_iso(), triggers_detected=candidates, debates=debates)
        write_json(self.paths.state_root / "kairos" / "council_latest.json", result.as_dict())
        self.logger.info(
            "[council] candidates=%s fired=%s",
            len(candidates),
            len(debates),
        )
        return result
