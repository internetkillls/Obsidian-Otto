from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..state import now_iso


class MemoryTier(str, Enum):
    FACT = "otto-fact"
    INTERPRETATION = "otto-interpretation"
    SPECULATION = "otto-speculation"


class WriteBoundary:
    def can_write_new_note(self) -> bool:
        return True

    def can_rewrite_vault_past(self, target: str) -> bool:
        return False

    def can_rewrite_vault_without_concent(self, target: str) -> bool:
        return False

    def can_link_to_folder(self, folder: str) -> bool:
        return folder in {"Action", "30-Projects", ".Otto-realm"}

    def can_write_future_ref_links(self) -> bool:
        return True


@dataclass
class TierEntry:
    tier: MemoryTier
    content: str
    source_note: str
    confidence: float
    ts: str = field(default_factory=now_iso)


class MemoryLayer:
    def __init__(self, vault_path: Path | None = None):
        from ..config import load_yaml_config, load_paths

        cfg = load_yaml_config("brain.yaml").get("brain", {})
        paths = load_paths()
        self.vault_path = vault_path or paths.vault_path
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured. Run initial.bat first.")

        self.facts_path = cfg.get("memory_tiers", {}).get("facts_path", ".Otto-Realm/Memory-Tiers/01-Facts")
        self.interpretations_path = cfg.get("memory_tiers", {}).get("interpretations_path", ".Otto-Realm/Memory-Tiers/02-Interpretations")
        self.speculations_path = cfg.get("memory_tiers", {}).get("speculations_path", ".Otto-Realm/Memory-Tiers/03-Speculations")
        self.max_facts = cfg.get("max_facts", 100)
        self.max_interpretations = cfg.get("max_interpretations", 50)
        self.max_speculations = cfg.get("max_speculations", 30)
        self.write_boundary = WriteBoundary()

    def resolve_tier_path(self, tier: MemoryTier) -> Path:
        base = self.vault_path
        if tier == MemoryTier.FACT:
            return base / self.facts_path
        if tier == MemoryTier.INTERPRETATION:
            return base / self.interpretations_path
        return base / self.speculations_path

    def max_for_tier(self, tier: MemoryTier) -> int:
        if tier == MemoryTier.FACT:
            return self.max_facts
        if tier == MemoryTier.INTERPRETATION:
            return self.max_interpretations
        return self.max_speculations

    def write_tier_entry(self, entry: TierEntry) -> Path:
        tier_dir = self.resolve_tier_path(entry.tier)
        tier_dir.mkdir(parents=True, exist_ok=True)

        slug = re.sub(r"[^a-z0-9]+", "-", entry.content[:40].lower()).strip("-")
        filename = f"{entry.ts[:10]}_{slug}.md"

        content = f"""---
title: {entry.content[:80]}
date: {entry.ts}
tier: {entry.tier.value}
confidence: {entry.confidence}
source: {entry.source_note}
tags:
  - {entry.tier.value}
---

# {entry.content}

- **Tier:** {entry.tier.value}
- **Confidence:** {entry.confidence}
- **Source:** [[{entry.source_note}]]
- **Created:** {entry.ts}
"""
        path = tier_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def read_tier_entries(self, tier: MemoryTier) -> list[TierEntry]:
        tier_dir = self.resolve_tier_path(tier)
        if not tier_dir.exists():
            return []

        entries: list[TierEntry] = []
        for md_file in sorted(tier_dir.glob("*.md")):
            text = md_file.read_text(encoding="utf-8", errors="replace")
            fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
            if fm_match:
                fm: dict[str, Any] = {}
                for line in fm_match.group(1).splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        fm[k.strip()] = v.strip()
                body = text[fm_match.end():].strip()
                entries.append(TierEntry(
                    tier=MemoryTier(fm.get("tier", tier.value)),
                    content=body.split("\n", 1)[0].lstrip("# ").strip(),
                    source_note=str(md_file),
                    confidence=float(fm.get("confidence", 0.5)),
                    ts=fm.get("date", md_file.stem[:10]),
                ))
        return entries
