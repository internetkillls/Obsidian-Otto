from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

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
    weakness_domain: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "trigger_category": self.trigger_category,
            "severity": self.severity,
            "diagnosis": self.diagnosis,
            "evidence": self.evidence,
            "recurrence_count": self.recurrence_count,
            "forced": self.forced,
            "weakness_domain": self.weakness_domain,
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
class CouncilOutput:
    role: str
    primary_action: str
    secondary_note: str = ""
    write_target: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "primary_action": self.primary_action,
            "secondary_note": self.secondary_note,
            "write_target": self.write_target,
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
    output: CouncilOutput = field(default_factory=lambda: CouncilOutput(role="assistant", primary_action=""))
    psychiatric_frame: dict[str, Any] = field(default_factory=dict)
    suffering_love_context: dict[str, Any] = field(default_factory=dict)
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
            "output": self.output.as_dict(),
            "psychiatric_frame": self.psychiatric_frame,
            "suffering_love_context": self.suffering_love_context,
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
                f"[PSYCHIATRIC FRAME]: {self.psychiatric_frame or {'functional_code': 'none'}}",
                f"[SUFFERING/LOVE]: {self.suffering_love_context or {'surface': 'none'}}",
                f"[OUTPUT ROLE]: {self.output.role}",
                f"[OUTPUT TARGET]: {self.output.write_target or 'n/a'}",
                f"[SYNTHESIS]: {self.synthesis}",
                f"[NEXT ACTION]: {self.next_action}",
                f"[ACTION SOURCE]: {self.action_source}",
            ]
        )
        return "\n".join(lines)


@dataclass
class PsychiatricFrame:
    weakness_domain: str
    functional_code: str
    frame_summary: str
    generative_or_degenerative: str
    recommended_output_role: str

    def as_dict(self) -> dict[str, str]:
        return {
            "weakness_domain": self.weakness_domain,
            "functional_code": self.functional_code,
            "frame_summary": self.frame_summary,
            "generative_or_degenerative": self.generative_or_degenerative,
            "recommended_output_role": self.recommended_output_role,
        }


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
        self.persona_archive_path = self.paths.state_root / "kairos" / "mentor_persona_archive.jsonl"

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

    @staticmethod
    def _persona_payload_from_council_persona(persona: CouncilPersona) -> dict[str, str]:
        return {
            "name": persona.name,
            "domain": persona.domain,
            "core_heuristic": persona.core_heuristic,
            "position": persona.position,
        }

    @staticmethod
    def _coerce_persona_payload(payload: Any) -> dict[str, str] | None:
        if not isinstance(payload, dict):
            return None
        required = ("name", "domain", "core_heuristic", "position")
        cleaned: dict[str, str] = {}
        for key in required:
            value = str(payload.get(key, "")).strip()
            if not value:
                return None
            cleaned[key] = value
        return cleaned

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end < 0 or end <= start:
            return None
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _llm_json_payload(
        self,
        *,
        prompt: str,
        model: str = "gpt-5.4-mini",
        system_prompt: str = "Return only one strict JSON object. No markdown.",
    ) -> dict[str, Any] | None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        endpoint = f"{base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        req = urlrequest.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=25) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except (urlerror.URLError, TimeoutError, OSError):
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        message = choices[0].get("message") if isinstance(choices[0], dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("text")
            )
        if not text.strip():
            return None
        return self._extract_json_object(text)

    def _llm_persona_payload(self, *, prompt: str, model: str = "gpt-5.4-mini") -> dict[str, str] | None:
        system_prompt = (
            "Return only one strict JSON object with keys: "
            "name, domain, core_heuristic, position. No markdown."
        )
        payload = self._llm_json_payload(prompt=prompt, model=model, system_prompt=system_prompt)
        return self._coerce_persona_payload(payload)

    def _load_cached_persona_pair(
        self,
        *,
        weakness_domain: str,
        archive_path: Path,
        max_age_days: int = 7,
    ) -> tuple[dict[str, str], dict[str, str]] | None:
        if not weakness_domain.strip() or not archive_path.exists():
            return None
        try:
            lines = archive_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            if str(row.get("weakness_domain", "")).strip() != weakness_domain:
                continue
            ts = _parse_ts(str(row.get("ts", "")))
            if ts < cutoff:
                continue
            persona_a = self._coerce_persona_payload(row.get("persona_a"))
            persona_b = self._coerce_persona_payload(row.get("persona_b"))
            if persona_a and persona_b:
                return persona_a, persona_b
        return None

    def _resolve_personas(
        self,
        *,
        trigger_category: str,
        weakness_domain: str,
        weakness_summary: str,
        archive_path: str,
    ) -> tuple[dict[str, str], dict[str, str]]:
        fallback_pair = self._PERSONA_MAP.get(trigger_category) or self._PERSONA_MAP["cognitive_weakness"]
        fallback_a = self._persona_payload_from_council_persona(fallback_pair[0])
        fallback_b = self._persona_payload_from_council_persona(fallback_pair[1])
        if trigger_category != "cognitive_weakness":
            return fallback_a, fallback_b
        domain = weakness_domain.strip()
        if not domain:
            return fallback_a, fallback_b

        archive_file = Path(archive_path)
        cached = self._load_cached_persona_pair(weakness_domain=domain, archive_path=archive_file)
        if cached:
            return cached

        try:
            persona_a = self._llm_persona_payload(
                model="gpt-5.4-mini",
                prompt=(
                    f"Given weakness domain '{domain}' described as '{weakness_summary}', "
                    "name one real-world thinker known for systematic calibration, epistemic rigor, "
                    "or structured problem-solving in this area."
                ),
            )
            persona_b = self._llm_persona_payload(
                model="gpt-5.4-mini",
                prompt=(
                    f"Given weakness domain '{domain}' described as '{weakness_summary}', "
                    "name one real-world thinker who would radically challenge or invert the conventional "
                    "approach in this area."
                ),
            )
            if persona_a and persona_b:
                append_jsonl(
                    archive_file,
                    {
                        "ts": now_iso(),
                        "weakness_domain": domain,
                        "trigger_category": trigger_category,
                        "persona_a": persona_a,
                        "persona_b": persona_b,
                    },
                )
                return persona_a, persona_b
        except Exception:
            # Silent fallback for any transient model/parse/runtime failure.
            return fallback_a, fallback_b
        return fallback_a, fallback_b

    @staticmethod
    def _coerce_psychiatric_payload(payload: Any) -> dict[str, str] | None:
        if not isinstance(payload, dict):
            return None
        functional_code = str(payload.get("functional_code", "")).strip()
        verdict = str(payload.get("generative_or_degenerative", "")).strip()
        role = str(payload.get("recommended_output_role", "")).strip()
        frame_summary = str(payload.get("frame_summary", "")).strip()
        valid_codes = {"skill_gap", "belief_gap", "avoidance_loop", "capacity_limit"}
        valid_verdicts = {"generative", "degenerative"}
        valid_roles = {"mentor", "thought_partner", "therapist", "business_partner"}
        if functional_code not in valid_codes:
            return None
        if verdict not in valid_verdicts:
            return None
        if role not in valid_roles:
            return None
        if not frame_summary:
            return None
        return {
            "functional_code": functional_code,
            "generative_or_degenerative": verdict,
            "recommended_output_role": role,
            "frame_summary": frame_summary,
        }

    @staticmethod
    def _normalize_surface_entries(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        flattened: list[str] = []
        for item in values:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    flattened.append(text)
                continue
            if isinstance(item, dict):
                for key in ("weakness_domain", "cue", "item", "text", "label"):
                    text = str(item.get(key, "")).strip()
                    if text:
                        flattened.append(text)
                        break
        return flattened[:30]

    def _load_morpheus_surfaces(self) -> tuple[list[str], list[str]]:
        path = self.paths.state_root / "openclaw" / "morpheus_openclaw_bridge_latest.json"
        if not path.exists():
            return [], []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [], []
        suffering_surface = data.get("suffering_surface")
        love_surface = data.get("love_surface")
        if isinstance(data.get("morpheus"), dict):
            suffering_surface = data["morpheus"].get("suffering_surface", suffering_surface)
            love_surface = data["morpheus"].get("love_surface", love_surface)
        return (
            self._normalize_surface_entries(suffering_surface),
            self._normalize_surface_entries(love_surface),
        )

    @staticmethod
    def _surface_matches_domain(weakness_domain: str, surface_values: list[str]) -> bool:
        domain = weakness_domain.strip().lower()
        if not domain:
            return False
        normalized_variants = {
            domain,
            domain.replace("_", " "),
            domain.replace("-", " "),
            domain.replace("_", "-"),
        }
        tokens = [token for token in domain.replace("_", " ").replace("-", " ").split() if token]
        for value in surface_values:
            text = value.lower()
            if any(variant in text for variant in normalized_variants):
                return True
            if tokens and all(token in text for token in tokens):
                return True
        return False

    def _suffering_love_context(
        self,
        *,
        weakness_domain: str,
        suffering_surface: list[str],
        love_surface: list[str],
    ) -> dict[str, str]:
        suffering_hit = self._surface_matches_domain(weakness_domain, suffering_surface)
        love_hit = self._surface_matches_domain(weakness_domain, love_surface)
        if suffering_hit and love_hit:
            return {
                "surface": "both",
                "verdict": "mixed",
                "recommendation": "Name a hard stop-rule for drag, then crystallize the constructive thread into protocol.",
            }
        if suffering_hit:
            return {
                "surface": "suffering_surface",
                "verdict": "degenerative",
                "recommendation": "Name one hard stop-rule and remove the loop before adding scope.",
            }
        if love_hit:
            return {
                "surface": "love_surface",
                "verdict": "generative",
                "recommendation": "Crystallize this thread into a reusable protocol or artifact.",
            }
        return {
            "surface": "none",
            "verdict": "undetermined",
            "recommendation": "No explicit surface match; use psychiatric frame and current output role.",
        }

    def _psychiatric_frame(
        self,
        *,
        weakness_domain: str,
        gap_type: str,
        suffering_surface: list[str],
    ) -> PsychiatricFrame:
        domain = weakness_domain.strip() or "general_execution_pattern"
        normalized_gap = gap_type.strip() or "unknown"
        suffering_blob = " | ".join(suffering_surface[:8])
        payload = self._llm_json_payload(
            model="gpt-5.4-mini",
            system_prompt=(
                "Classify functional pattern only (not diagnosis). "
                "Return strict JSON with keys: functional_code, frame_summary, "
                "generative_or_degenerative, recommended_output_role."
            ),
            prompt=(
                "You are a functional-pattern triage layer for council briefing.\n"
                f"Weakness domain: {domain}\n"
                f"Gap type: {normalized_gap}\n"
                f"Morpheus suffering surface cues: {suffering_blob or 'none'}\n"
                "Choose one functional_code: skill_gap | belief_gap | avoidance_loop | capacity_limit.\n"
                "Choose one generative_or_degenerative: generative | degenerative.\n"
                "Choose one recommended_output_role: mentor | thought_partner | therapist | business_partner.\n"
                "frame_summary must be one sentence for persona briefing."
            ),
        )
        coerced = self._coerce_psychiatric_payload(payload)
        if coerced:
            return PsychiatricFrame(
                weakness_domain=domain,
                functional_code=coerced["functional_code"],
                frame_summary=coerced["frame_summary"],
                generative_or_degenerative=coerced["generative_or_degenerative"],
                recommended_output_role=coerced["recommended_output_role"],
            )

        suffering_hit = any(domain.lower() in item.lower() for item in suffering_surface)
        if suffering_hit:
            return PsychiatricFrame(
                weakness_domain=domain,
                functional_code="avoidance_loop",
                frame_summary=f"Recurring drag around {domain} suggests an avoidance loop over a pure skill issue.",
                generative_or_degenerative="degenerative",
                recommended_output_role="therapist",
            )
        if normalized_gap == "theory_gap":
            return PsychiatricFrame(
                weakness_domain=domain,
                functional_code="skill_gap",
                frame_summary=f"{domain} appears to be a conceptual skill gap needing structured rehearsal.",
                generative_or_degenerative="generative",
                recommended_output_role="mentor",
            )
        if normalized_gap == "application_gap":
            return PsychiatricFrame(
                weakness_domain=domain,
                functional_code="skill_gap",
                frame_summary=f"{domain} is mostly an application execution gap under real constraints.",
                generative_or_degenerative="generative",
                recommended_output_role="mentor",
            )
        return PsychiatricFrame(
            weakness_domain=domain,
            functional_code="belief_gap",
            frame_summary=f"{domain} likely reflects a belief friction and needs reframing before more effort.",
            generative_or_degenerative="generative",
            recommended_output_role="thought_partner",
        )

    def _output_role_for_debate(self, *, trigger: CouncilTrigger, psychiatric_frame: PsychiatricFrame) -> str:
        if trigger.trigger_category == "epistemic_gap":
            return "researcher"
        if psychiatric_frame.recommended_output_role in {"mentor", "thought_partner", "therapist", "business_partner"}:
            return psychiatric_frame.recommended_output_role
        if trigger.severity == "low":
            return "assistant"
        return "assistant"

    def _derive_council_output(
        self,
        *,
        trigger: CouncilTrigger,
        psychiatric_frame: PsychiatricFrame,
        action_candidate: CouncilActionCandidate,
    ) -> CouncilOutput:
        role = self._output_role_for_debate(trigger=trigger, psychiatric_frame=psychiatric_frame)
        domain = trigger.weakness_domain.strip() or trigger.trigger_category
        default_target = str(self.paths.state_root / "kairos" / "council_latest.json")
        if action_candidate.source == "graph_demotion_review":
            return CouncilOutput(
                role=role,
                primary_action=action_candidate.action,
                secondary_note=f"Role lens: {role}. {psychiatric_frame.frame_summary}",
                write_target=default_target,
            )
        if role == "mentor":
            queue_root = (
                str(self.paths.vault_path / ".Otto-Realm" / "Training" / "pending")
                if self.paths.vault_path is not None
                else ".Otto-Realm/Training/pending"
            )
            return CouncilOutput(
                role=role,
                primary_action=action_candidate.action,
                secondary_note=f"Training focus: {domain} ({psychiatric_frame.functional_code}).",
                write_target=queue_root,
            )
        if role == "thought_partner":
            probe_root = (
                str(self.paths.vault_path / ".Otto-Realm" / "Training" / "probes")
                if self.paths.vault_path is not None
                else ".Otto-Realm/Training/probes"
            )
            return CouncilOutput(
                role=role,
                primary_action=f"Probe {domain}: which belief blocks execution, and what evidence would falsify it this week?",
                secondary_note=psychiatric_frame.frame_summary,
                write_target=probe_root,
            )
        if role == "therapist":
            return CouncilOutput(
                role=role,
                primary_action=(
                    f"Stop-rule: if {domain} is deferred twice, pause new loops and execute this now: {action_candidate.action}. "
                    f"Confrontation: avoid one more abstraction pass and ship one visible step today."
                ),
                secondary_note=psychiatric_frame.frame_summary,
                write_target=default_target,
            )
        if role == "business_partner":
            return CouncilOutput(
                role=role,
                primary_action=(
                    f"Reprioritize around highest leverage: {action_candidate.action}. "
                    f"Defer lower-return tracks until this is closed."
                ),
                secondary_note=psychiatric_frame.frame_summary,
                write_target=default_target,
            )
        if role == "researcher":
            return CouncilOutput(
                role=role,
                primary_action=(
                    f"Research brief for {domain}: run one bounded literature query, extract one contradiction, and convert it into one execution decision."
                ),
                secondary_note="Epistemic gap requires evidence-first closure.",
                write_target=default_target,
            )
        return CouncilOutput(
            role="assistant",
            primary_action=action_candidate.action,
            secondary_note=psychiatric_frame.frame_summary,
            write_target=default_target,
        )

    @staticmethod
    def _dynamic_payload_to_persona(payload: dict[str, str], *, default: CouncilPersona, lens: str) -> CouncilPersona:
        name = str(payload.get("name", default.name)).strip() or default.name
        domain = str(payload.get("domain", default.domain)).strip() or default.domain
        core_heuristic = str(payload.get("core_heuristic", default.core_heuristic)).strip() or default.core_heuristic
        position = str(payload.get("position", default.position)).strip() or default.position
        if lens == "systematic":
            limitation = "Can underweight situational improvisation under severe time pressure."
        else:
            limitation = "Can over-index on inversion and underweight stable process gains."
        return CouncilPersona(
            name=name,
            domain=domain,
            core_heuristic=core_heuristic,
            position=position,
            strongest_argument=core_heuristic,
            limitation=limitation,
        )

    def _candidate_triggers(
        self,
        *,
        gold_result: KairosGoldResult,
        unresolved: list[str],
        weakness_registry: dict[str, dict[str, Any]] | None = None,
    ) -> list[CouncilTrigger]:
        unresolved_count = len(unresolved)
        contradictions_count = len(gold_result.contradictions)
        candidates: list[CouncilTrigger] = []

        active_gaps = [
            (key, entry)
            for key, entry in (weakness_registry or {}).items()
            if isinstance(entry, dict) and entry.get("latest_gap_type") in {"theory_gap", "application_gap"}
        ]
        if active_gaps:
            top_key, top_entry = active_gaps[0]
            gap_type = str(top_entry.get("latest_gap_type", "unknown"))
            candidates.append(
                CouncilTrigger(
                    trigger_category="cognitive_weakness",
                    severity="high",
                    diagnosis=f"Unresolved {gap_type} in domain: {top_key}",
                    evidence=[
                        f"weakness_domain={top_key}",
                        f"gap_type={gap_type}",
                        f"active_gaps={len(active_gaps)}",
                    ],
                    weakness_domain=top_key,
                )
            )
        elif not weakness_registry and (unresolved_count >= 5 or gold_result.noise_count >= 5):
            candidates.append(
                CouncilTrigger(
                    trigger_category="cognitive_weakness",
                    severity="medium",
                    diagnosis="Recurring unresolved load - no active mentor probe to anchor.",
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
        weakness_registry: dict[str, dict[str, Any]] | None = None,
    ) -> CouncilDebate:
        pair = self._PERSONA_MAP.get(trigger.trigger_category)
        if pair is None:
            pair = self._PERSONA_MAP["cognitive_weakness"]
        registry_entry = (
            (weakness_registry or {}).get(trigger.weakness_domain, {})
            if trigger.weakness_domain
            else {}
        )
        gap_type = ""
        if isinstance(registry_entry, dict):
            gap_type = str(registry_entry.get("latest_gap_type", "")).strip()
        if not gap_type:
            for item in trigger.evidence:
                if item.startswith("gap_type="):
                    gap_type = item.split("=", 1)[1].strip()
                    break
        suffering_surface, love_surface = self._load_morpheus_surfaces()
        psychiatric_frame = self._psychiatric_frame(
            weakness_domain=trigger.weakness_domain or trigger.trigger_category,
            gap_type=gap_type,
            suffering_surface=suffering_surface,
        )
        suffering_love_context = self._suffering_love_context(
            weakness_domain=trigger.weakness_domain or trigger.trigger_category,
            suffering_surface=suffering_surface,
            love_surface=love_surface,
        )
        if trigger.trigger_category == "cognitive_weakness":
            resolved_a, resolved_b = self._resolve_personas(
                trigger_category=trigger.trigger_category,
                weakness_domain=trigger.weakness_domain,
                weakness_summary=f"{trigger.diagnosis} | frame={psychiatric_frame.frame_summary}",
                archive_path=str(self.persona_archive_path),
            )
            persona_a = self._dynamic_payload_to_persona(resolved_a, default=pair[0], lens="systematic")
            persona_b = self._dynamic_payload_to_persona(resolved_b, default=pair[1], lens="contrarian")
        else:
            persona_a, persona_b = pair
        action_candidate = self._pick_action_candidate(unresolved, action_candidates)
        output = self._derive_council_output(
            trigger=trigger,
            psychiatric_frame=psychiatric_frame,
            action_candidate=action_candidate,
        )
        next_action = output.primary_action or action_candidate.action
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
        if suffering_love_context["surface"] in {"suffering_surface", "both"}:
            synthesis = (
                f"{synthesis} This pressure is flagged as degenerative drag. "
                "Council recommends naming a hard stop-rule."
            )
        if suffering_love_context["surface"] in {"love_surface", "both"}:
            synthesis = (
                f"{synthesis} This thread has generative depth. "
                "Council recommends crystallizing it into a reusable protocol."
            )
        metabolic_sentence = (
            "Predator qua Angel check: "
            f"verdict={suffering_love_context['verdict']}; "
            f"metabolic response={suffering_love_context['recommendation']}."
        )
        synthesis = f"{synthesis} {metabolic_sentence}"
        synthesis = f"{synthesis} Recommended output role: {output.role}."
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
            output=output,
            psychiatric_frame=psychiatric_frame.as_dict(),
            suffering_love_context=suffering_love_context,
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
        weakness_registry: dict[str, dict[str, Any]] | None = None,
    ) -> CouncilRunResult:
        now = datetime.now(timezone.utc)
        candidates = self._candidate_triggers(
            gold_result=gold_result,
            unresolved=unresolved,
            weakness_registry=weakness_registry,
        )
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

        debates = [
            self._build_debate(
                trigger,
                unresolved,
                action_candidates,
                weakness_registry=weakness_registry,
            )
            for trigger in fired
        ]
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
