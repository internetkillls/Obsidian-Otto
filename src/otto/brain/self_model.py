from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_paths
from ..state import now_iso


@dataclass
class SirAgathonProfile:
    preferred_response_length: str | None = None
    working_hours: dict[str, str] = field(default_factory=dict)
    vault_strengths: list[str] = field(default_factory=list)
    vault_weaknesses: list[str] = field(default_factory=list)
    observed_patterns: list[dict[str, Any]] = field(default_factory=list)
    theme_map: dict[str, int] = field(default_factory=dict)
    candidate_specialist_fits: dict[str, float] = field(default_factory=dict)
    style_profile: dict[str, str] = field(default_factory=dict)
    cognitive_risks: list[str] = field(default_factory=list)
    recovery_levers: list[str] = field(default_factory=list)
    support_style: list[str] = field(default_factory=list)
    continuity_commitments: list[dict[str, Any]] = field(default_factory=list)
    opportunity_map: list[dict[str, Any]] = field(default_factory=list)
    continuity_prompts: list[dict[str, Any]] = field(default_factory=list)
    suffering_signals: list[str] = field(default_factory=list)
    weakness_taxonomy: list[dict[str, Any]] = field(default_factory=list)
    swot: dict[str, list[str]] = field(default_factory=lambda: {
        "strengths": [],
        "weaknesses": [],
        "opportunities": [],
        "threats": [],
    })

    def add_pattern(self, pattern: str, observation: str, confidence: float) -> None:
        self.observed_patterns.append({
            "pattern": pattern,
            "observation": observation,
            "confidence": confidence,
            "ts": now_iso(),
        })

    @property
    def sm2_hooks(self) -> list[dict[str, Any]]:
        return self.continuity_prompts

    @sm2_hooks.setter
    def sm2_hooks(self, value: list[dict[str, Any]]) -> None:
        self.continuity_prompts = list(value)

    def profile_to_markdown(self) -> str:
        lines = [
            "# Otto Self-Model",
            "",
            f"Generated: {now_iso()}",
            "",
            "## Preferred Response Style",
            f"- Length: {self.preferred_response_length or 'unknown'}",
            f"- Working hours: {self.working_hours or 'not set'}",
            "",
            "## Vault Strengths",
        ]
        lines.extend([f"- {s}" for s in self.vault_strengths] or ["- (none yet)"])
        lines.extend(["", "## Vault Weaknesses"])
        lines.extend([f"- {w}" for w in self.vault_weaknesses] or ["- (none yet)"])
        lines.extend(["", "## Observed Patterns"])
        for p in self.observed_patterns:
            lines.append(f"- [{p['pattern']}] {p['observation']} (conf={p['confidence']:.1f})")
        if not self.observed_patterns:
            lines.append("- (none yet)")
        lines.extend(["", "## Theme Map"])
        for theme, count in sorted(self.theme_map.items(), key=lambda x: -x[1]):
            lines.append(f"- {theme}: {count}")
        if not self.theme_map:
            lines.append("- (no data yet)")
        lines.extend(["", "## Specialist Fit Candidates"])
        for specialist, score in sorted(self.candidate_specialist_fits.items(), key=lambda x: -x[1]):
            lines.append(f"- {specialist}: {score:.1f}")
        if not self.candidate_specialist_fits:
            lines.append("- (not yet analyzed)")
        lines.extend(["", "## Cognitive Risks"])
        lines.extend([f"- {item}" for item in self.cognitive_risks] or ["- (none yet)"])
        lines.extend(["", "## Recovery Levers"])
        lines.extend([f"- {item}" for item in self.recovery_levers] or ["- (none yet)"])
        lines.extend(["", "## Preferred Support Style"])
        lines.extend([f"- {item}" for item in self.support_style] or ["- (none yet)"])
        lines.extend(["", "## Continuity Commitments"])
        if self.continuity_commitments:
            for item in self.continuity_commitments:
                lines.append(
                    f"- {item['cue']} | path={item['path']} | kind={item['kind']} | conf={item['confidence']:.2f}"
                )
        else:
            lines.append("- (none yet)")
        lines.extend(["", "## Opportunity Map"])
        if self.opportunity_map:
            for item in self.opportunity_map:
                lines.append(
                    f"- {item['cue']} | horizon={item['horizon']} | kind={item['kind']} | path={item['path']} | conf={item['confidence']:.2f}"
                )
        else:
            lines.append("- (none yet)")
        lines.extend(["", "## Continuity Prompts"])
        if self.continuity_prompts:
            for item in self.continuity_prompts:
                lines.append(f"- {item['question']} | source={item['path']} | conf={item['confidence']:.2f}")
        else:
            lines.append("- (none yet)")
        lines.extend(["", "## Suffering Signals"])
        lines.extend([f"- {item}" for item in self.suffering_signals] or ["- (none yet)"])
        lines.extend(["", "## SWOT"])
        for key in ("strengths", "weaknesses", "opportunities", "threats"):
            lines.append(f"### {key.capitalize()}")
            lines.extend([f"- {item}" for item in self.swot.get(key, [])] or ["- (none yet)"])
        return "\n".join(lines) + "\n"


class OttoSelfModel:
    BRAIN_NOTES_PATH = ".Otto-Realm/Brain"
    PRIORITY_PREFIX_WEIGHTS: dict[str, int] = {
        "!My/Backboard": 220,
        "!My/Practical-honesty": 210,
        "10-Personal": 205,
        "Action": 180,
        "30-Projects": 175,
        "20-Programs": 165,
        "!My/Meta-Kernel": 150,
        "z Incubator": 140,
        "memory": 120,
        "Otto-session": 100,
        "90-Archive": 160,
        "10-Inbox": 70,
    }
    DEPRIORITIZED_PREFIX_WEIGHTS: dict[str, int] = {
        "00-Meta/scarcity": -180,
        "00_Templates": -170,
        "!My/Template": -170,
        ".Otto-Realm/Handoff": -260,
        ".Otto-Realm/Reports": -240,
        ".Otto-Realm/Memory-Tiers": -220,
        ".Otto-Realm/Predictions": -210,
        ".Otto-Realm/Heartbeats": -180,
        ".Otto-Realm/Brain": -140,
        "Otto-Realm/Handoff": -260,
        "Otto-Realm/Reports": -240,
        "Otto-Realm/Memory-Tiers": -220,
        "Otto-Realm/Predictions": -210,
        "Otto-Realm/Heartbeats": -180,
        "Otto-Realm/Brain": -140,
        ".obsidian": -320,
        ".trash": -320,
    }
    PROFILE_KEYWORDS: dict[str, tuple[str, ...]] = {
        "monolog": (
            "i ", " i'm ", " i've ", " i want", " i need", " i have",
            "saya", "aku", "gue", "gw", "my ", "honesty", "backboard",
        ),
        "commitment": (
            "must", "need to", "should", "commit", "komitmen", "janji",
            "target", "deadline", "next step", "follow up", "follow-up",
            "harus", "perlu", "mau", "ingin", "minggu ini", "this week",
        ),
        "opportunity": (
            "opportunity", "peluang", "revenue", "client", "offer",
            "service", "package", "proposal", "portfolio", "seller",
            "asset", "income", "monetizable", "business", "market",
        ),
        "historical": (
            "2 years", "3 years", "tahun lalu", "dulu", "back then",
            "archive", "old", "stale", "lagi", "pernah",
        ),
    }
    PROFILE_SOURCE_ROOTS: tuple[str, ...] = (
        "!My/Backboard",
        "!My/Practical-honesty",
        "10-Personal",
        "Action",
        "30-Projects",
        "20-Programs",
        "!My/Meta-Kernel",
        "z Incubator",
        "memory",
        "Otto-session",
        "90-Archive",
        "10-Inbox",
    )

    def __init__(self, vault_path: Path | None = None):
        paths = load_paths()
        self.vault_path = vault_path or paths.vault_path
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        self.profile = SirAgathonProfile()
        self._load_existing_profile()

    def _load_existing_profile(self) -> None:
        if self.vault_path is None:
            return
        brain_dir = self.vault_path / self.BRAIN_NOTES_PATH
        profile_path = brain_dir / "self_model.md"
        if not profile_path.exists():
            return
        text = profile_path.read_text(encoding="utf-8", errors="replace")
        if "terse" in text.lower():
            self.profile.preferred_response_length = "terse"
        if "verbose" in text.lower():
            self.profile.preferred_response_length = "verbose"
        theme_matches = re.findall(r"- (\w+):\s*(\d+)", text)
        for theme, count in theme_matches:
            self.profile.theme_map[theme] = int(count)

    def build_from_scan(
        self,
        scan_result: dict[str, Any],
        mentor_weakness_registry: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        notes = self._build_profile_note_pool(scan_result.get("notes", []))
        registry = mentor_weakness_registry
        if registry is None:
            maybe_registry = scan_result.get("mentor_weakness_registry", {})
            registry = maybe_registry if isinstance(maybe_registry, dict) else {}
        self.profile.vault_strengths = self._derive_strengths(notes)
        self.profile.vault_weaknesses = self._derive_weaknesses(notes)
        self.profile.weakness_taxonomy = self._derive_weakness_taxonomy(registry)
        self._build_theme_map(notes)
        self._infer_response_style(notes)
        self.profile.cognitive_risks = self._derive_cognitive_risks(notes)
        self.profile.recovery_levers = self._derive_recovery_levers(notes)
        self.profile.support_style = self._derive_support_style(notes)
        self.profile.continuity_commitments = self._extract_commitments(notes)
        self.profile.opportunity_map = self._extract_opportunities(notes)
        self.profile.continuity_prompts = self._build_continuity_prompts(notes)
        self.profile.suffering_signals = self._derive_suffering_signals(notes)
        self.profile.swot = self._build_swot()
        return {
            "profile_snapshot": self.profile.profile_to_markdown(),
            "strengths": self.profile.vault_strengths,
            "weaknesses": self.profile.vault_weaknesses,
            "theme_map": self.profile.theme_map,
            "patterns": self.profile.observed_patterns,
            "cognitive_risks": self.profile.cognitive_risks,
            "recovery_levers": self.profile.recovery_levers,
            "support_style": self.profile.support_style,
            "continuity_commitments": self.profile.continuity_commitments,
            "opportunity_map": self.profile.opportunity_map,
            "continuity_prompts": self.profile.continuity_prompts,
            "suffering_signals": self.profile.suffering_signals,
            "weakness_taxonomy": self.profile.weakness_taxonomy,
            "swot": self.profile.swot,
        }

    def _derive_strengths(self, notes: list[dict[str, Any]]) -> list[str]:
        strengths: list[str] = []
        tagged_notes = [n for n in notes if n.get("tags")]
        if len(tagged_notes) / max(len(notes), 1) > 0.5:
            strengths.append("High tagging discipline")
        linked_notes = [n for n in notes if n.get("wikilinks")]
        if len(linked_notes) / max(len(notes), 1) > 0.3:
            strengths.append("Good wikilink density")
        return strengths

    def _derive_weaknesses(self, notes: list[dict[str, Any]]) -> list[str]:
        weaknesses: list[str] = []
        orphaned = [n for n in notes if not n.get("wikilinks") and not n.get("tags")]
        if len(orphaned) / max(len(notes), 1) > 0.2:
            weaknesses.append(f"High orphan ratio ({len(orphaned)} orphan notes)")
        no_frontmatter = [n for n in notes if not n.get("has_frontmatter")]
        if len(no_frontmatter) / max(len(notes), 1) > 0.3:
            weaknesses.append(f"Missing frontmatter on {len(no_frontmatter)} notes")
        return weaknesses

    def _derive_weakness_taxonomy(
        self,
        mentor_weakness_registry: dict[str, dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        taxonomy: list[dict[str, Any]] = []
        for weakness_key, entry in (mentor_weakness_registry or {}).items():
            if not isinstance(entry, dict):
                continue
            gap_type = str(entry.get("latest_gap_type", "")).strip()
            if gap_type not in {"theory_gap", "application_gap"}:
                continue
            recurrence_count = 0
            for history_key in ("probe_history", "task_history", "history"):
                history = entry.get(history_key)
                if isinstance(history, list):
                    recurrence_count = max(recurrence_count, len(history))
            try:
                recurrence_count = max(recurrence_count, int(entry.get("recurrence_count", 0) or 0))
            except (TypeError, ValueError):
                recurrence_count = max(recurrence_count, 0)
            taxonomy.append(
                {
                    "weakness_key": str(weakness_key),
                    "gap_type": gap_type,
                    "recurrence_count": max(1, recurrence_count),
                }
            )
        taxonomy.sort(key=lambda item: (-int(item["recurrence_count"]), str(item["weakness_key"])))
        return taxonomy[:20]

    def _build_theme_map(self, notes: list[dict[str, Any]]) -> None:
        tag_counts: dict[str, int] = {}
        for note in notes:
            for tag in note.get("tags", []):
                base = tag.split("/")[0].replace("-", "_")
                tag_counts[base] = tag_counts.get(base, 0) + 1
        self.profile.theme_map = dict(sorted(tag_counts.items(), key=lambda x: -x[1])[:10])

    def _infer_response_style(self, notes: list[dict[str, Any]]) -> None:
        bodies = [n.get("body_excerpt", "") for n in notes]
        avg_body_len = sum(len(b) for b in bodies) / max(len(bodies), 1)
        if avg_body_len < 500:
            self.profile.preferred_response_length = "terse"
        elif avg_body_len > 2000:
            self.profile.preferred_response_length = "verbose"
        else:
            self.profile.preferred_response_length = "moderate"

    def _derive_cognitive_risks(self, notes: list[dict[str, Any]]) -> list[str]:
        return self._top_matches(
            notes,
            {
                "Context switching stays expensive; continuity must be carried by the system.": [
                    "context switching", "context-switching", "lompat", "jump", "re-entry"
                ],
                "Overload and confusion loops need narrower prompts and one-step guidance.": [
                    "overload", "confusion", "bingung", "stuck", "freeze", "executive dysfunction"
                ],
                "Commitments can be forgotten unless recalled from history and surfaced proactively.": [
                    "forgot", "lupa", "commitment", "promise", "target", "deadline"
                ],
                "Long-running loops need visible stop conditions and externalized next actions.": [
                    "stop condition", "too long", "run too long", "next action", "resume"
                ],
            },
        )

    def _derive_recovery_levers(self, notes: list[dict[str, Any]]) -> list[str]:
        return self._top_matches(
            notes,
            {
                "Short, concrete prompts with one next step reduce friction.": [
                    "one action", "one next step", "terse", "short response", "actionable"
                ],
                "Anchors, MOC links, and durable writebacks improve re-entry.": [
                    "moc", "anchor", "re-entry", "resume", "checkpoint", "handoff"
                ],
                "Externalizing thought into notes/checklists/protocols restores momentum.": [
                    "checklist", "protocol", "write it down", "operator", "workflow"
                ],
                "System-held memory is a recovery aid when attention becomes inconsistent.": [
                    "memory load", "carry this memory load", "do not have to remember", "vault must reduce"
                ],
            },
        )

    def _derive_support_style(self, notes: list[dict[str, Any]]) -> list[str]:
        style = self._top_matches(
            notes,
            {
                "Default to humane tone first, then rigor.": [
                    "humane", "warm", "friendly", "natural/human"
                ],
                "Prefer one main action over parallel task floods.": [
                    "one action", "one clear next step", "without options", "parallel"
                ],
                "Use recall and synthesis proactively instead of waiting for chat prompts.": [
                    "proactive", "recall", "surface", "follow-up", "check-in"
                ],
            },
        )
        if not style:
            style = [
                "Default to humane tone first, then rigor.",
                "Prefer one main action over parallel task floods.",
            ]
        return style

    def _derive_suffering_signals(self, notes: list[dict[str, Any]]) -> list[str]:
        return self._top_matches(
            notes,
            {
                "Repeated unresolved load suggests degenerative drag rather than a single missing tactic.": [
                    "unresolved", "drag", "recurring", "stalled", "drift"
                ],
                "Opportunity cost rises when promising threads are not revisited.": [
                    "opportunity", "neglected", "someday", "stale", "2 years", "3 years"
                ],
                "Noise and inconsistency likely hide valuable self-knowledge inside scattered monologs.": [
                    "monolog", "inconsistent", "jump", "scattered", "vault"
                ],
            },
        )

    def _build_swot(self) -> dict[str, list[str]]:
        return {
            "strengths": list(self.profile.vault_strengths[:5]),
            "weaknesses": list(self.profile.cognitive_risks[:5]) or list(self.profile.vault_weaknesses[:5]),
            "opportunities": [item["cue"] for item in self.profile.opportunity_map[:5]],
            "threats": list(self.profile.suffering_signals[:5]),
        }

    def _extract_commitments(self, notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = self._collect_note_candidates(
            notes,
            keywords=[
                "must", "need to", "should", "commit", "komitmen", "target", "deadline",
                "follow up", "follow-up", "next step", "plan", "sprint", "promise",
                "harus", "perlu", "janji", "ingin", "mau", "this week", "minggu ini",
            ],
            kinds=("goal", "project", "task", "commitment", "personal"),
            horizons=("week", "month", "quarter", "year"),
        )
        return self._prioritize_candidate_mix(
            candidates,
            preferred_prefixes=(
                "10-Personal",
                "Action",
                "!My/Practical-honesty",
                "!My/Backboard",
                "20-Programs",
                "30-Projects",
                "90-Archive",
            ),
        )[:8]

    def _extract_opportunities(self, notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = self._collect_note_candidates(
            notes,
            keywords=[
                "opportunity", "peluang", "revenue", "client", "offer", "service", "package",
                "proposal", "portfolio", "linkedin", "monetizable", "business",
                "seller", "asset", "market", "income", "jualan",
            ],
            kinds=("opportunity", "service", "client", "research", "business", "project"),
            horizons=("week", "year", "1-year", "3-year"),
        )
        return self._prioritize_candidate_mix(
            candidates,
            preferred_prefixes=(
                "30-Projects",
                "20-Programs",
                "z Incubator",
                "Action",
                "90-Archive",
                "!My/Backboard",
                "!My/Practical-honesty",
            ),
            historical_bias=True,
        )[:8]

    def _build_continuity_prompts(self, notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prompts: list[dict[str, Any]] = []
        seeds = self.profile.continuity_commitments[:4] + self.profile.opportunity_map[:4]
        for item in seeds:
            prompts.append({
                "question": f"Apa status terbaru untuk '{item['cue']}' dan apa next step terkecilnya?",
                "path": item["path"],
                "confidence": item["confidence"],
            })
        return prompts[:6]

    def _top_matches(self, notes: list[dict[str, Any]], mapping: dict[str, list[str]]) -> list[str]:
        scores: list[tuple[int, str]] = []
        for label, keywords in mapping.items():
            score = 0
            for note in notes:
                haystack = self._note_text(note)
                if any(keyword in haystack for keyword in keywords):
                    score += 1
            if score:
                scores.append((score, label))
        scores.sort(key=lambda item: (-item[0], item[1]))
        return [label for _, label in scores[:5]]

    def _collect_note_candidates(
        self,
        notes: list[dict[str, Any]],
        *,
        keywords: list[str],
        kinds: tuple[str, ...],
        horizons: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for note in notes:
            haystack = self._note_text(note)
            matched = sum(1 for keyword in keywords if keyword in haystack)
            kind = self._detect_kind(note, haystack, kinds)
            if matched == 0 and kind is None:
                continue
            cue = self._clean_excerpt(note.get("title") or note.get("path") or "Untitled")
            horizon = self._detect_horizon(haystack, horizons)
            priority_bonus = max(0.0, float(note.get("_profile_priority", 0)) / 500.0)
            historical_bonus = 0.06 if note.get("_historical_signal") else 0.0
            confidence = min(0.98, 0.4 + (0.09 * matched) + (0.08 if kind else 0) + priority_bonus + historical_bonus)
            candidates.append({
                "path": str(note.get("path", "")),
                "cue": cue,
                "kind": kind or "note",
                "horizon": horizon,
                "confidence": round(confidence, 2),
                "historical": bool(note.get("_historical_signal")),
                "priority": int(note.get("_profile_priority", 0) or 0),
            })
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in sorted(candidates, key=lambda row: (-row["confidence"], row["path"])):
            key = item["path"]
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _prioritize_candidate_mix(
        self,
        candidates: list[dict[str, Any]],
        *,
        preferred_prefixes: tuple[str, ...],
        historical_bias: bool = False,
    ) -> list[dict[str, Any]]:
        def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
            prefix_rank = next(
                (idx for idx, prefix in enumerate(preferred_prefixes) if str(item.get("path", "")).startswith(prefix)),
                len(preferred_prefixes),
            )
            historical_rank = 0 if item.get("historical") else 1
            return (
                historical_rank if historical_bias else 0,
                prefix_rank,
                -float(item.get("confidence", 0.0)),
                -int(item.get("priority", 0)),
                str(item.get("path", "")),
            )

        ordered = sorted(candidates, key=sort_key)
        selected: list[dict[str, Any]] = []
        seen_families: set[str] = set()
        for item in ordered:
            family = self._candidate_family(str(item.get("path", "")))
            if family in seen_families:
                continue
            seen_families.add(family)
            selected.append(item)
            if len(selected) >= 5:
                break
        for item in ordered:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) >= 8:
                break
        return selected

    def _candidate_family(self, path: str) -> str:
        normalized = self._normalize_note_path(path)
        parts = normalized.split("/")
        if normalized.startswith("!My/") and len(parts) >= 2:
            return "/".join(parts[:2])
        if normalized.startswith("90-Archive") and len(parts) >= 2:
            return "/".join(parts[:2])
        return parts[0] if parts else normalized

    def _detect_kind(self, note: dict[str, Any], haystack: str, kinds: tuple[str, ...]) -> str | None:
        tags = [str(tag).lower() for tag in note.get("tags", [])]
        path = str(note.get("path", "")).lower()
        for kind in kinds:
            if kind in haystack or any(kind in tag for tag in tags) or kind in path:
                return kind
        return None

    def _detect_horizon(self, haystack: str, horizons: tuple[str, ...]) -> str:
        if "90-archive" in haystack or any(token in haystack for token in ("2 years", "3 years", "tahun lalu")):
            return "1y+"
        if any(token in haystack for token in ("today", "minggu ini", "this week", "week")):
            return "7d"
        if any(token in haystack for token in ("month", "bulan", "30 hari")):
            return "30d"
        if any(token in haystack for token in ("year", "1-year", "tahun", "2 years", "3 years")):
            return "1y+"
        for token in horizons:
            if token in haystack:
                return token
        return "unknown"

    def _build_profile_note_pool(self, scan_notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pool: dict[str, dict[str, Any]] = {}
        for note in scan_notes:
            normalized = dict(note)
            path = str(normalized.get("path", ""))
            if not path:
                continue
            normalized["path"] = self._normalize_note_path(path)
            normalized["_source"] = "scan"
            normalized["_profile_priority"] = self._score_profile_priority(normalized)
            normalized["_historical_signal"] = self._historical_signal(normalized)
            pool[normalized["path"]] = normalized

        for note in self._load_priority_notes_from_vault():
            existing = pool.get(note["path"])
            if existing is None or len(note.get("body_excerpt", "")) > len(existing.get("body_excerpt", "")):
                pool[note["path"]] = note

        sorted_notes = sorted(
            pool.values(),
            key=lambda note: (
                -int(note.get("_profile_priority", 0)),
                -len(str(note.get("body_excerpt", ""))),
                str(note.get("path", "")),
            ),
        )
        return sorted_notes[:600]

    def _load_priority_notes_from_vault(self) -> list[dict[str, Any]]:
        if self.vault_path is None:
            return []
        loaded: list[dict[str, Any]] = []
        for root in self.PROFILE_SOURCE_ROOTS:
            base = self.vault_path.joinpath(*root.split("/"))
            if not base.exists():
                continue
            for path in sorted(base.rglob("*.md")):
                note = self._read_markdown_note(path)
                if note is None:
                    continue
                note["_source"] = "vault"
                note["_profile_priority"] = self._score_profile_priority(note)
                note["_historical_signal"] = self._historical_signal(note)
                loaded.append(note)
        return loaded

    def _read_markdown_note(self, path: Path) -> dict[str, Any] | None:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        frontmatter_text, body = self._split_frontmatter(raw)
        rel_path = self._normalize_note_path(path.relative_to(self.vault_path).as_posix())
        tags = self._extract_tags(frontmatter_text)
        wikilinks = re.findall(r"\[\[([^\]]+)\]\]", body)
        title = self._extract_title(path, body)
        age_days = self._age_days(path)
        return {
            "path": rel_path,
            "title": title,
            "tags": tags,
            "wikilinks": wikilinks,
            "body_excerpt": body[:2400],
            "frontmatter_text": frontmatter_text,
            "has_frontmatter": bool(frontmatter_text),
            "age_days": age_days,
        }

    def _split_frontmatter(self, text: str) -> tuple[str, str]:
        if not text.startswith("---"):
            return "", text
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
        if not match:
            return "", text
        frontmatter_text = match.group(1)
        body = text[match.end():]
        return frontmatter_text, body

    def _extract_tags(self, frontmatter_text: str) -> list[str]:
        tags: list[str] = []
        if not frontmatter_text:
            return tags
        inline = re.search(r"(?im)^tags:\s*\[(.*?)\]\s*$", frontmatter_text)
        if inline:
            tags.extend(
                token.strip().strip("'\"")
                for token in inline.group(1).split(",")
                if token.strip()
            )
        block = re.search(r"(?ims)^tags:\s*\n((?:\s*-\s*.+\n?)*)", frontmatter_text)
        if block:
            tags.extend(
                token.strip().strip("'\"")
                for token in re.findall(r"(?im)^\s*-\s*(.+?)\s*$", block.group(1))
            )
        return [tag for tag in tags if tag]

    def _extract_title(self, path: Path, body: str) -> str:
        heading = re.search(r"(?m)^#\s+(.+?)\s*$", body)
        if heading:
            return heading.group(1).strip()
        return path.stem

    def _score_profile_priority(self, note: dict[str, Any]) -> int:
        path = self._normalize_note_path(str(note.get("path", "")))
        haystack = self._note_text(note)
        score = 0
        for prefix, weight in self.PRIORITY_PREFIX_WEIGHTS.items():
            if path.startswith(prefix):
                score += weight
        for prefix, weight in self.DEPRIORITIZED_PREFIX_WEIGHTS.items():
            if path.startswith(prefix):
                score += weight
        if any(token in haystack for token in self.PROFILE_KEYWORDS["monolog"]):
            score += 40
        if any(token in haystack for token in self.PROFILE_KEYWORDS["commitment"]):
            score += 35
        if any(token in haystack for token in self.PROFILE_KEYWORDS["opportunity"]):
            score += 35
        if self._historical_signal(note):
            score += 20
        return score

    def _historical_signal(self, note: dict[str, Any]) -> bool:
        path = str(note.get("path", "")).lower().replace("\\", "/")
        haystack = self._note_text(note)
        age_days = int(note.get("age_days", 0) or 0)
        return (
            path.startswith("90-archive")
            or age_days >= 90
            or any(token in haystack for token in self.PROFILE_KEYWORDS["historical"])
        )

    def _age_days(self, path: Path) -> int:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return 0
        return max(0, int((datetime.now(timezone.utc) - mtime).days))

    def _normalize_note_path(self, path: str) -> str:
        return path.replace("\\", "/").lstrip("./")

    def _note_text(self, note: dict[str, Any]) -> str:
        parts = [
            str(note.get("path", "")),
            str(note.get("title", "")),
            " ".join(str(tag) for tag in note.get("tags", [])),
            str(note.get("frontmatter_text", "")),
            str(note.get("body_excerpt", "")),
            str(note.get("orientation", "")),
            str(note.get("allocation", "")),
        ]
        return " ".join(parts).lower()

    def _clean_excerpt(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text.replace("\\", " / ")).strip()
        return text[:120]

    def write_profile_to_vault(self) -> Path:
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        brain_dir = self.vault_path / self.BRAIN_NOTES_PATH
        brain_dir.mkdir(parents=True, exist_ok=True)
        path = brain_dir / "self_model.md"
        path.write_text(self.profile.profile_to_markdown(), encoding="utf-8")
        return path
