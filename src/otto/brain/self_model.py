from __future__ import annotations

import re
from dataclasses import dataclass, field
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

    def add_pattern(self, pattern: str, observation: str, confidence: float) -> None:
        self.observed_patterns.append({
            "pattern": pattern,
            "observation": observation,
            "confidence": confidence,
            "ts": now_iso(),
        })

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
        return "\n".join(lines) + "\n"


class OttoSelfModel:
    BRAIN_NOTES_PATH = "Otto-Realm/Brain"

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

    def build_from_scan(self, scan_result: dict[str, Any]) -> dict[str, Any]:
        notes = scan_result.get("notes", [])
        self.profile.vault_strengths = self._derive_strengths(notes)
        self.profile.vault_weaknesses = self._derive_weaknesses(notes)
        self._build_theme_map(notes)
        self._infer_response_style(notes)
        return {
            "profile_snapshot": self.profile.profile_to_markdown(),
            "strengths": self.profile.vault_strengths,
            "weaknesses": self.profile.vault_weaknesses,
            "theme_map": self.profile.theme_map,
            "patterns": self.profile.observed_patterns,
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

    def write_profile_to_vault(self) -> Path:
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        brain_dir = self.vault_path / self.BRAIN_NOTES_PATH
        brain_dir.mkdir(parents=True, exist_ok=True)
        path = brain_dir / "self_model.md"
        path.write_text(self.profile.profile_to_markdown(), encoding="utf-8")
        return path
