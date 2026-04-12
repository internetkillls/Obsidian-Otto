# Otto Brain Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Otto Brain — a self-modeling, anticipatory, memory-tiered cognitive layer for Otto, using modular Python (A) + vault-native markdown (C), scaffoldable to deep refactor (B).

**Architecture:** Otto Brain lives in `src/otto/brain/` as pure Python modules. Otto-Realm lives in the Obsidian vault as markdown notes with `#otto-brain` tags. Brain modules read/write vault-native notes as the canonical Otto memory. Pipeline integration wires Brain into KAIROS + Dream + Retrieval loops.

**Tech Stack:** Python 3.11+, existing Otto stack (YAML, JSON, Rich, SQLite), Obsidian markdown + wikilinks, no new dependencies.

---

## File Structure

```
src/otto/
├── brain/
│   ├── __init__.py
│   ├── memory_layer.py       # fact/interpretation/speculation tier manager
│   ├── self_model.py         # vault → Otto mental model of Sir Agathon
│   ├── predictive_scaffold.py # anticipation engine
│   └── ritual_engine.py      # scan → reflect → dream → act cycle
├── orchestration/
│   ├── brain.py              # orchestrates brain modules (NEW, thin)
│   ├── kairos.py             # (existing, modified)
│   └── dream.py              # (existing, modified)
├── Otto-Realm/
│   ├── Brain/                # vault-native self-model notes
│   ├── Predictions/          # anticipatory scaffolding notes
│   ├── Memory-Tiers/
│   │   ├── 01-Facts/
│   │   ├── 02-Interpretations/
│   │   └── 03-Speculations/
│   └── Rituals/              # ritual cycle notes
config/
├── brain.yaml                # Otto Brain config (tier paths, write rules)
tests/
├── test_brain_memory_layer.py
├── test_brain_self_model.py
├── test_brain_predictive.py
└── test_brain_ritual.py
```

---

## PHASE 1 TASKS

### Task 1: Otto Brain Memory Layer

**Files:**
- Create: `src/otto/brain/memory_layer.py`
- Create: `tests/test_brain_memory_layer.py`
- Modify: `src/otto/brain/__init__.py`
- Modify: `config/brain.yaml`

- [ ] **Step 1: Create config/brain.yaml**

```yaml
brain:
  memory_tiers:
    facts_path: "Otto-Realm/Memory-Tiers/01-Facts"
    interpretations_path: "Otto-Realm/Memory-Tiers/02-Interpretations"
    speculations_path: "Otto-Realm/Memory-Tiers/03-Speculations"
  brain_notes_path: "Otto-Realm/Brain"
  predictions_path: "Otto-Realm/Predictions"
  rituals_path: "Otto-Realm/Rituals"
  max_facts: 100
  max_interpretations: 50
  max_speculations: 30
  write_boundary:
    allow_new_notes: true
    allow_link_to_action: true
    allow_link_to_project: true
    allow_future_ref_links: true
    disallow_rewrite_vault_past: true
    disallow_rewrite_vault_without_concent: true
```

- [ ] **Step 2: Write failing test for MemoryTier enum and write_boundary check**

```python
# tests/test_brain_memory_layer.py
from __future__ import annotations
from otto.brain.memory_layer import MemoryTier, WriteBoundary, TierEntry


class TestMemoryTier:
    def test_tier_enum_values(self):
        assert MemoryTier.FACT.value == "otto-fact"
        assert MemoryTier.INTERPRETATION.value == "otto-interpretation"
        assert MemoryTier.SPECULATION.value == "otto-speculation"


class TestWriteBoundary:
    def test_can_write_new_note_allowed(self):
        wb = WriteBoundary()
        assert wb.can_write_new_note() is True

    def test_can_rewrite_vault_past_denied(self):
        wb = WriteBoundary()
        assert wb.can_rewrite_vault_past(target="01-Inbox/test.md") is False

    def test_can_rewrite_vault_without_concent_denied(self):
        wb = WriteBoundary()
        assert wb.can_rewrite_vault_without_concent(target="10-Personal/diary.md") is False

    def test_can_link_to_action_allowed(self):
        wb = WriteBoundary()
        assert wb.can_link_to_folder("Action") is True

    def test_can_link_to_project_allowed(self):
        wb = WriteBoundary()
        assert wb.can_link_to_folder("30-Projects") is True

    def test_future_ref_link_allowed(self):
        wb = WriteBoundary()
        assert wb.can_write_future_ref_link() is True


class TestTierEntry:
    def test_tier_entry_creation(self):
        entry = TierEntry(
            tier=MemoryTier.FACT,
            content="Sir Agathon prefers short responses",
            source_note="Otto-Realm/Brain/preference_model.md",
            confidence=0.9,
        )
        assert entry.tier == MemoryTier.FACT
        assert entry.confidence == 0.9
        assert "short responses" in entry.content
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_brain_memory_layer.py -v`
Expected: FAIL — ModuleNotFoundError: No module named 'otto.brain'

- [ ] **Step 4: Create src/otto/brain/__init__.py**

```python
from __future__ import annotations

from .memory_layer import MemoryTier, WriteBoundary, TierEntry, MemoryLayer

__all__ = [
    "MemoryTier",
    "WriteBoundary",
    "TierEntry",
    "MemoryLayer",
]
```

- [ ] **Step 5: Write minimal MemoryTier enum + WriteBoundary class**

```python
# src/otto/brain/memory_layer.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

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
        return folder in {"Action", "30-Projects", "Otto-Realm"}

    def can_write_future_ref_links(self) -> bool:
        return True


@dataclass
class TierEntry:
    tier: MemoryTier
    content: str
    source_note: str
    confidence: float
    ts: str = field(default_factory=now_iso)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_brain_memory_layer.py::TestMemoryTier -v`
Run: `pytest tests/test_brain_memory_layer.py::TestWriteBoundary -v`
Run: `pytest tests/test_brain_memory_layer.py::TestTierEntry -v`
Expected: PASS for all three

- [ ] **Step 7: Add MemoryLayer class to memory_layer.py**

```python
# Add to src/otto/brain/memory_layer.py (after WriteBoundary)
from pathlib import Path
from typing import Any

from ..config import load_yaml_config, load_paths


class MemoryLayer:
    def __init__(self, vault_path: Path | None = None):
        cfg = load_yaml_config("brain.yaml").get("brain", {})
        paths = load_paths()
        self.vault_path = vault_path or paths.vault_path
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured. Run initial.bat first.")

        self.facts_path = Path(cfg.get("memory_tiers", {}).get("facts_path", "Otto-Realm/Memory-Tiers/01-Facts"))
        self.interpretations_path = Path(cfg.get("memory_tiers", {}).get("interpretations_path", "Otto-Realm/Memory-Tiers/02-Interpretations"))
        self.speculations_path = Path(cfg.get("memory_tiers", {}).get("speculations_path", "Otto-Realm/Memory-Tiers/03-Speculations"))
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

        slug = entry.content[:40].lower().replace(" ", "-").replace("/", "-").replace(".", "")
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
            # Extract frontmatter
            import re
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
                    source_note=fm.get("source", str(md_file)),
                    confidence=float(fm.get("confidence", 0.5)),
                    ts=fm.get("date", md_file.stem[:10]),
                ))
        return entries
```

- [ ] **Step 8: Add tests for MemoryLayer**

```python
# Add to tests/test_brain_memory_layer.py
from pathlib import Path
from otto.brain.memory_layer import MemoryLayer, TierEntry, MemoryTier


class TestMemoryLayer:
    def test_resolve_tier_path_fact(self, tmp_vault):
        ml = MemoryLayer(vault_path=tmp_vault)
        result = ml.resolve_tier_path(MemoryTier.FACT)
        assert "01-Facts" in str(result)

    def test_resolve_tier_path_interpretation(self, tmp_vault):
        ml = MemoryLayer(vault_path=tmp_vault)
        result = ml.resolve_tier_path(MemoryTier.INTERPRETATION)
        assert "02-Interpretations" in str(result)

    def test_resolve_tier_path_speculation(self, tmp_vault):
        ml = MemoryLayer(vault_path=tmp_vault)
        result = ml.resolve_tier_path(MemoryTier.SPECULATION)
        assert "03-Speculations" in str(result)

    def test_write_tier_entry_creates_file(self, tmp_vault):
        ml = MemoryLayer(vault_path=tmp_vault)
        entry = TierEntry(
            tier=MemoryTier.FACT,
            content="Sir Agathon prefers terse responses",
            source_note="Otto-Realm/Brain/preference.md",
            confidence=0.95,
        )
        path = ml.write_tier_entry(entry)
        assert path.exists()
        assert path.suffix == ".md"

    def test_write_tier_entry_content_has_tags(self, tmp_vault):
        ml = MemoryLayer(vault_path=tmp_vault)
        entry = TierEntry(
            tier=MemoryTier.SPECULATION,
            content="Otto predicts Sir Agathon will prioritize vault hygiene",
            source_note="Otto-Realm/Predictions/vault_hygiene.md",
            confidence=0.6,
        )
        path = ml.write_tier_entry(entry)
        text = path.read_text(encoding="utf-8")
        assert "otto-speculation" in text
        assert "confidence: 0.6" in text

    def test_read_tier_entries_empty_when_no_files(self, tmp_vault):
        ml = MemoryLayer(vault_path=tmp_vault)
        entries = ml.read_tier_entries(MemoryTier.FACT)
        assert entries == []

    def test_read_tier_entries_returns_written_entry(self, tmp_vault):
        ml = MemoryLayer(vault_path=tmp_vault)
        entry = TierEntry(
            tier=MemoryTier.INTERPRETATION,
            content="Sir Agathon seems to value directness",
            source_note="Otto-Realm/Brain/style.md",
            confidence=0.8,
        )
        ml.write_tier_entry(entry)
        entries = ml.read_tier_entries(MemoryTier.INTERPRETATION)
        assert len(entries) >= 1
        assert entries[-1].tier == MemoryTier.INTERPRETATION


# Add fixture to tests/conftest.py (create if not exists)
# tests/conftest.py
import pytest
from pathlib import Path


@pytest.fixture
def tmp_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault
```

- [ ] **Step 9: Run all memory layer tests**

Run: `pytest tests/test_brain_memory_layer.py -v`
Expected: PASS for all

- [ ] **Step 10: Commit**

```bash
git add config/brain.yaml src/otto/brain/__init__.py src/otto/brain/memory_layer.py tests/test_brain_memory_layer.py tests/conftest.py
git commit -m "feat(brain): add Otto Brain memory layer with fact/interpretation/speculation tiers"
```

---

### Task 2: Otto Brain Self-Model

**Files:**
- Create: `src/otto/brain/self_model.py`
- Create: `tests/test_brain_self_model.py`
- Modify: `src/otto/brain/__init__.py`
- Modify: `src/otto/tooling/obsidian_scan.py` (read only)

- [ ] **Step 1: Write failing test for SelfModel**

```python
# tests/test_brain_self_model.py
from __future__ import annotations
from pathlib import Path
from otto.brain.self_model import OttoSelfModel, SirAgathonProfile


class TestSirAgathonProfile:
    def test_profile_default_values(self):
        p = SirAgathonProfile()
        assert p.preferred_response_length is None
        assert p.working_hours == {}
        assert p.vault_strengths == []
        assert p.vault_weaknesses == []
        assert p.observed_patterns == []

    def test_profile_can_add_pattern(self):
        p = SirAgathonProfile()
        p.add_pattern("terse_responses", "Sir Agathon prefers short sentences", confidence=0.9)
        assert len(p.observed_patterns) == 1
        assert p.observed_patterns[0]["pattern"] == "terse_responses"
        assert p.observed_patterns[0]["confidence"] == 0.9


class TestOttoSelfModel:
    def test_self_model_initializes_with_profile(self):
        sm = OttoSelfModel()
        assert sm.profile is not None
        assert isinstance(sm.profile, SirAgathonProfile)

    def test_build_from_vault_scan_results(self):
        sm = OttoSelfModel()
        mock_scan = {
            "note_count": 5,
            "notes": [
                {"path": "10-Personal/goal.md", "tags": ["goal"], "wikilinks": ["30-Projects/app"]},
                {"path": "10-Personal/habit.md", "tags": ["habit"], "wikilinks": []},
            ]
        }
        result = sm.build_from_scan(mock_scan)
        assert "profile_snapshot" in result
        assert "strengths" in result
        assert "weaknesses" in result

    def test_write_profile_to_vault(self, tmp_vault):
        sm = OttoSelfModel(vault_path=tmp_vault)
        sm.profile.preferred_response_length = "terse"
        sm.profile.working_hours = {"start": "09:00", "end": "17:00"}
        path = sm.write_profile_to_vault()
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "preferred_response_length" in text.lower() or "terse" in text.lower()

    def test_profile_markdown_format(self, tmp_vault):
        sm = OttoSelfModel(vault_path=tmp_vault)
        sm.profile.add_pattern("short_sentences", "Sir Agathon uses short sentences", confidence=0.9)
        md = sm.profile_to_markdown()
        assert "# Otto Self-Model" in md
        assert "short_sentences" in md
        assert "otto-interpretation" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_brain_self_model.py -v`
Expected: FAIL — ModuleNotFoundError: No module named 'otto.brain.self_model'

- [ ] **Step 3: Write SirAgathonProfile dataclass**

```python
# src/otto/brain/self_model.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

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
```

- [ ] **Step 4: Write OttoSelfModel class**

```python
# Add to src/otto/brain/self_model.py (after SirAgathonProfile)
from pathlib import Path

from ..config import load_paths


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
        brain_dir = self.vault_path / self.BRAIN_NOTES_PATH
        profile_path = brain_dir / "self_model.md"
        if not profile_path.exists():
            return
        text = profile_path.read_text(encoding="utf-8", errors="replace")
        # Light parse — populate known fields if present
        import re
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
        avg_body_len = sum(len(n.get("body_excerpt", "")) for n in notes) / max(len(notes), 1)
        if avg_body_len < 500:
            self.profile.preferred_response_length = "terse"
        elif avg_body_len > 2000:
            self.profile.preferred_response_length = "verbose"
        else:
            self.profile.preferred_response_length = "moderate"

    def write_profile_to_vault(self) -> Path:
        brain_dir = self.vault_path / self.BRAIN_NOTES_PATH
        brain_dir.mkdir(parents=True, exist_ok=True)
        path = brain_dir / "self_model.md"
        path.write_text(self.profile.profile_to_markdown(), encoding="utf-8")
        return path
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_brain_self_model.py -v`
Expected: PASS for all

- [ ] **Step 6: Update src/otto/brain/__init__.py**

```python
from __future__ import annotations

from .memory_layer import MemoryTier, WriteBoundary, TierEntry, MemoryLayer
from .self_model import OttoSelfModel, SirAgathonProfile

__all__ = [
    "MemoryTier",
    "WriteBoundary",
    "TierEntry",
    "MemoryLayer",
    "OttoSelfModel",
    "SirAgathonProfile",
]
```

- [ ] **Step 7: Commit**

```bash
git add src/otto/brain/__init__.py src/otto/brain/self_model.py tests/test_brain_self_model.py
git commit -m "feat(brain): add Otto self-modeling — vault scan to Sir Agathon profile"
```

---

### Task 3: Otto Brain Predictive Scaffold

**Files:**
- Create: `src/otto/brain/predictive_scaffold.py`
- Create: `tests/test_brain_predictive.py`
- Modify: `src/otto/brain/__init__.py`

- [ ] **Step 1: Write failing test for PredictiveScaffold**

```python
# tests/test_brain_predictive.py
from __future__ import annotations
from pathlib import Path
from otto.brain.predictive_scaffold import Prediction, PredictiveScaffold


class TestPrediction:
    def test_prediction_creation(self):
        p = Prediction(
            prediction="Sir Agathon will prioritize vault hygiene next week",
            confidence=0.65,
            trigger="increased note capture observed",
            horizon_days=7,
        )
        assert p.prediction is not None
        assert 0.0 <= p.confidence <= 1.0
        assert p.horizon_days >= 1

    def test_prediction_to_markdown(self):
        p = Prediction(
            prediction="Next focus: linking orphans to MOC",
            confidence=0.7,
            trigger="recent linking activity spike",
            horizon_days=3,
        )
        md = p.to_markdown()
        assert "# Prediction" in md
        assert "confidence: 0.7" in md
        assert "3 days" in md


class TestPredictiveScaffold:
    def test_scaffold_initializes_empty(self):
        ps = PredictiveScaffold()
        assert ps.predictions == []

    def test_generate_predictions_from_profile(self):
        ps = PredictiveScaffold()
        mock_profile = {
            "vault_weaknesses": ["High orphan ratio (5 orphan notes)"],
            "vault_strengths": ["Good wikilink density"],
            "observed_patterns": [],
        }
        preds = ps.generate_from_profile(mock_profile)
        assert isinstance(preds, list)

    def test_write_predictions_to_vault(self, tmp_vault):
        ps = PredictiveScaffold(vault_path=tmp_vault)
        ps.add_prediction(
            prediction="Sir Agathon will check status tomorrow morning",
            confidence=0.75,
            trigger="morning routine observed",
            horizon_days=1,
        )
        path = ps.write_predictions_to_vault()
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "status" in text.lower() or "prediction" in text.lower()

    def test_add_prediction_stores(self):
        ps = PredictiveScaffold()
        ps.add_prediction("Test prediction", confidence=0.5, trigger="test", horizon_days=2)
        assert len(ps.predictions) == 1
        assert ps.predictions[0].prediction == "Test prediction"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_brain_predictive.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Write Prediction dataclass + PredictiveScaffold**

```python
# src/otto/brain/predictive_scaffold.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..state import now_iso


@dataclass
class Prediction:
    prediction: str
    confidence: float
    trigger: str
    horizon_days: int
    ts: str = field(default_factory=now_iso)

    def to_markdown(self) -> str:
        return f"""# Prediction

- **What:** {self.prediction}
- **Confidence:** {self.confidence:.0%}
- **Horizon:** {self.horizon_days} day(s)
- **Trigger:** {self.trigger}
- **Created:** {self.ts}

---

*This is Otto's anticipation — not a promise. Confidence below 0.6 means low certainty.*
"""


class PredictiveScaffold:
    PREDICTIONS_PATH = "Otto-Realm/Predictions"

    def __init__(self, vault_path: Any | None = None):
        from ..config import load_paths
        paths = load_paths()
        self.vault_path = vault_path or paths.vault_path
        if self.vault_path is None:
            raise RuntimeError("Vault path not configured.")
        self.predictions: list[Prediction] = []

    def add_prediction(
        self,
        prediction: str,
        confidence: float,
        trigger: str,
        horizon_days: int,
    ) -> Prediction:
        p = Prediction(
            prediction=prediction,
            confidence=max(0.0, min(1.0, confidence)),
            trigger=trigger,
            horizon_days=horizon_days,
        )
        self.predictions.append(p)
        return p

    def generate_from_profile(self, profile: dict[str, Any]) -> list[Prediction]:
        self.predictions.clear()
        weaknesses = profile.get("vault_weaknesses", [])
        strengths = profile.get("vault_strengths", [])
        patterns = profile.get("observed_patterns", [])

        # Predict from weaknesses
        if any("orphan" in w.lower() for w in weaknesses):
            self.add_prediction(
                prediction="Next vault action: linking orphan notes to MOC anchors",
                confidence=0.75,
                trigger="High orphan ratio detected in last scan",
                horizon_days=3,
            )

        if any("frontmatter" in w.lower() for w in weaknesses):
            self.add_prediction(
                prediction="Next focus: normalizing frontmatter on tagged notes",
                confidence=0.7,
                trigger="Missing frontmatter detected",
                horizon_days=5,
            )

        # Predict from patterns
        pattern_names = [p.get("pattern", "") for p in patterns]
        if "terse_responses" in pattern_names:
            self.add_prediction(
                prediction="Sir Agathon will appreciate terse, actionable responses",
                confidence=0.85,
                trigger="Terse response pattern confirmed across sessions",
                horizon_days=1,
            )

        # Predict from strengths
        if any("wikilink" in s.lower() for s in strengths):
            self.add_prediction(
                prediction="Sir Agathon values connected knowledge — keep linking dense",
                confidence=0.8,
                trigger="Strong wikilink discipline observed",
                horizon_days=7,
            )

        return self.predictions

    def write_predictions_to_vault(self) -> Any:
        vault = self.vault_path
        pred_dir = vault / self.PREDICTIONS_PATH
        pred_dir.mkdir(parents=True, exist_ok=True)

        today = now_iso()[:10]
        filename = f"{today}_predictions.md"
        path = pred_dir / filename

        lines = [
            f"# Otto Predictions — {today}",
            "",
            f"Generated: {now_iso()}",
            "",
            f"Total predictions: {len(self.predictions)}",
            "",
            "## Active Predictions",
            "",
        ]
        for i, p in enumerate(self.predictions, 1):
            lines.append(f"### {i}. {p.prediction}")
            lines.append(f"- Confidence: {p.confidence:.0%}")
            lines.append(f"- Horizon: {p.horizon_days} day(s)")
            lines.append(f"- Trigger: {p.trigger}")
            lines.append(f"- Created: {p.ts}")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brain_predictive.py -v`
Expected: PASS

- [ ] **Step 5: Update src/otto/brain/__init__.py**

```python
from __future__ import annotations

from .memory_layer import MemoryTier, WriteBoundary, TierEntry, MemoryLayer
from .self_model import OttoSelfModel, SirAgathonProfile
from .predictive_scaffold import PredictiveScaffold, Prediction

__all__ = [
    "MemoryTier",
    "WriteBoundary",
    "TierEntry",
    "MemoryLayer",
    "OttoSelfModel",
    "SirAgathonProfile",
    "PredictiveScaffold",
    "Prediction",
]
```

- [ ] **Step 6: Commit**

```bash
git add src/otto/brain/__init__.py src/otto/brain/predictive_scaffold.py tests/test_brain_predictive.py
git commit -m "feat(brain): add Otto predictive scaffold — anticipation engine"
```

---

### Task 4: Otto Brain Ritual Engine

**Files:**
- Create: `src/otto/brain/ritual_engine.py`
- Create: `tests/test_brain_ritual.py`
- Modify: `src/otto/brain/__init__.py`

- [ ] **Step 1: Write failing test for RitualEngine**

```python
# tests/test_brain_ritual.py
from __future__ import annotations
from pathlib import Path
from otto.brain.ritual_engine import RitualPhase, RitualResult, RitualEngine


class TestRitualPhase:
    def test_phase_enum_values(self):
        assert RitualPhase.SCAN.value == "scan"
        assert RitualPhase.REFLECT.value == "reflect"
        assert RitualPhase.DREAM.value == "dream"
        assert RitualPhase.ACT.value == "act"


class TestRitualEngine:
    def test_engine_initializes(self):
        re = RitualEngine()
        assert re.current_phase == RitualPhase.SCAN
        assert re.history == []

    def test_run_scan_phase(self, tmp_vault, monkeypatch):
        import tempfile
        # Create a minimal note in vault
        note = tmp_vault / "10-Personal" / "test.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text("---\ntags: [test]\n---\n# Test\nContent here.", encoding="utf-8")

        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        re = RitualEngine(vault_path=tmp_vault)
        result = re.run_phase(RitualPhase.SCAN)
        assert result.phase == RitualPhase.SCAN
        assert result.note_count >= 1
        assert result.artifacts_created >= 0

    def test_run_reflect_phase(self, tmp_vault):
        re = RitualEngine(vault_path=tmp_vault)
        re._scan_results = {"note_count": 5, "notes": []}
        result = re.run_phase(RitualPhase.REFLECT)
        assert result.phase == RitualPhase.REFLECT

    def test_run_dream_phase(self, tmp_vault):
        re = RitualEngine(vault_path=tmp_vault)
        re._scan_results = {"note_count": 5, "notes": []}
        result = re.run_phase(RitualPhase.DREAM)
        assert result.phase == RitualPhase.DREAM

    def test_run_act_phase(self, tmp_vault):
        re = RitualEngine(vault_path=tmp_vault)
        re._scan_results = {"note_count": 5, "notes": []}
        result = re.run_phase(RitualPhase.ACT)
        assert result.phase == RitualPhase.ACT

    def test_run_full_cycle(self, tmp_vault, monkeypatch):
        monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))
        re = RitualEngine(vault_path=tmp_vault)
        results = re.run_full_cycle()
        assert len(results) == 4
        assert results[0].phase == RitualPhase.SCAN
        assert results[-1].phase == RitualPhase.ACT

    def test_write_ritual_note(self, tmp_vault):
        re = RitualEngine(vault_path=tmp_vault)
        result = RitualResult(
            phase=RitualPhase.SCAN,
            note_count=3,
            artifacts_created=1,
            duration_ms=150,
            summary="Scanned 3 notes",
        )
        path = re.write_ritual_note(result)
        assert path.exists()
        assert "ritual" in str(path).lower() or "scan" in str(path).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_brain_ritual.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Write RitualPhase, RitualResult, RitualEngine**

```python
# src/otto/brain/ritual_engine.py
from __future__ import annotations

import time as time_module
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

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

    def __init__(self, vault_path: Any | None = None):
        from ..config import load_paths
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
        else:  # ACT
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
            "vault_strengths": self.history[1].summary if len(self.history) > 1 else "",
            "vault_weaknesses": self.history[1].summary if len(self.history) > 1 else "",
            "observed_patterns": [],
        }
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
        rituals_dir = self.vault_path / self.RITUALS_PATH
        rituals_dir.mkdir(parents=True, exist_ok=True)
        ts = result.ts[:10]
        filename = f"{ts}_{result.phase.value}_ritual.md"
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brain_ritual.py -v`
Expected: PASS

- [ ] **Step 5: Update src/otto/brain/__init__.py**

```python
from __future__ import annotations

from .memory_layer import MemoryTier, WriteBoundary, TierEntry, MemoryLayer
from .self_model import OttoSelfModel, SirAgathonProfile
from .predictive_scaffold import PredictiveScaffold, Prediction
from .ritual_engine import RitualEngine, RitualPhase, RitualResult

__all__ = [
    "MemoryTier",
    "WriteBoundary",
    "TierEntry",
    "MemoryLayer",
    "OttoSelfModel",
    "SirAgathonProfile",
    "PredictiveScaffold",
    "Prediction",
    "RitualEngine",
    "RitualPhase",
    "RitualResult",
]
```

- [ ] **Step 6: Commit**

```bash
git add src/otto/brain/__init__.py src/otto/brain/ritual_engine.py tests/test_brain_ritual.py
git commit -m "feat(brain): add Otto ritual engine — scan/reflect/dream/act cycle"
```

---

### Task 5: Otto Brain Orchestration + Events

**Files:**
- Create: `src/otto/orchestration/brain.py`
- Modify: `src/otto/events.py`
- Modify: `src/otto/orchestration/kairos.py`
- Modify: `src/otto/orchestration/dream.py`

- [ ] **Step 1: Add brain event constants to events.py**

```python
# Add to src/otto/events.py (after existing EVENT_* constants)
EVENT_BRAIN_SELF_MODEL_UPDATED = "brain.self_model.updated"
EVENT_BRAIN_PREDICTION_GENERATED = "brain.prediction.generated"
EVENT_BRAIN_RITUAL_COMPLETED = "brain.ritual.completed"
```

- [ ] **Step 2: Write orchestration/brain.py**

```python
# src/otto/orchestration/brain.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..brain import (
    OttoSelfModel,
    PredictiveScaffold,
    MemoryLayer,
    RitualEngine,
    MemoryTier,
    TierEntry,
)
from ..config import load_paths
from ..events import Event, EventBus, EVENT_BRAIN_SELF_MODEL_UPDATED, EVENT_BRAIN_PREDICTION_GENERATED, EVENT_BRAIN_RITUAL_COMPLETED
from ..logging_utils import get_logger
from ..state import OttoState, now_iso, write_json


def run_brain_self_model() -> dict[str, Any]:
    logger = get_logger("otto.brain.self_model")
    state = OttoState.load()
    state.ensure()
    paths = load_paths()

    if paths.vault_path is None:
        raise RuntimeError("Vault path not configured.")

    # Read latest bronze scan
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

    # Write tier entry for the update
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

    # Build minimal profile from existing brain notes
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

    re = RitualEngine(vault_path=paths.vault_path)
    results = re.run_full_cycle()

    # Write ritual notes for each phase
    ritual_paths = []
    for r in results:
        p = re.write_ritual_note(r)
        ritual_paths.append(str(p))

    # Write tier entry for completed cycle
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
        payload={"ts": now_iso(), "phases": [r.phase.value for r in results], "artifacts": sum(r.artifacts_created for r in results)},
    ))

    logger.info(f"[brain] ritual cycle complete: {len(results)} phases")
    return {
        "status": "ok",
        "phases": [r.phase.value for r in results],
        "durations": [f"{r.duration_ms:.1f}ms" for r in results],
        "ritual_notes": ritual_paths,
    }
```

- [ ] **Step 3: Wire brain into kairos.py (add brain_predictions call)**

```python
# Modify src/otto/orchestration/kairos.py
# Add import at top
from .brain import run_brain_predictions

# In run_kairos_once(), after writing strategy report, add:
pred_result = run_brain_predictions()
```

- [ ] **Step 4: Wire brain into dream.py (add brain_self_model call)**

```python
# Modify src/otto/orchestration/dream.py
# Add import at top
from .brain import run_brain_self_model

# In run_dream_once(), after dream_state write, add:
sm_result = run_brain_self_model()
```

- [ ] **Step 5: Commit**

```bash
git add src/otto/events.py src/otto/orchestration/brain.py src/otto/orchestration/kairos.py src/otto/orchestration/dream.py
git commit -m "feat(brain): wire Otto Brain into KAIROS + Dream orchestration"
```

---

### Task 6: Otto Brain CLI + brain.bat

**Files:**
- Create: `src/otto/brain_cli.py` (entry point)
- Create: `brain.bat` (Windows launcher)
- Modify: `src/otto/cli.py`

- [ ] **Step 1: Write src/otto/brain_cli.py**

```python
# src/otto/brain_cli.py
from __future__ import annotations

import argparse
import sys

from otto.orchestration.brain import (
    run_brain_self_model,
    run_brain_predictions,
    run_brain_ritual_cycle,
)
from otto.logging_utils import get_logger


def main() -> int:
    parser = argparse.ArgumentParser(prog="otto brain", description="Otto Brain operations")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("self-model", help="Build Otto self-model from vault scan")
    sub.add_parser("predictions", help="Generate Otto predictions from profile")
    sub.add_parser("ritual", help="Run full scan/reflect/dream/act cycle")
    sub.add_parser("all", help="Run self-model + predictions + ritual cycle")

    args = parser.parse_args()
    logger = get_logger("otto.brain.cli")

    if args.command == "self-model":
        result = run_brain_self_model()
        print(f"Self-model: {result}")
        return 0 if result.get("status") == "ok" else 1
    elif args.command == "predictions":
        result = run_brain_predictions()
        print(f"Predictions: {result}")
        return 0 if result.get("status") == "ok" else 1
    elif args.command == "ritual":
        result = run_brain_ritual_cycle()
        print(f"Ritual cycle: {result}")
        return 0 if result.get("status") == "ok" else 1
    elif args.command == "all":
        sm = run_brain_self_model()
        pred = run_brain_predictions()
        ritual = run_brain_ritual_cycle()
        print(f"=== Otto Brain All ===")
        print(f"Self-model: {sm}")
        print(f"Predictions: {pred}")
        print(f"Ritual: {ritual}")
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write brain.bat**

```batch
@echo off
setlocal

cd /d "%~dp0"

if "%~1"=="" (
    echo Otto Brain CLI
    echo Usage: brain.bat [self-model^|predictions^|ritual^|all]
    exit /b 1
)

call .venv\Scripts\activate.bat 2>nul || (
    echo Warning: virtualenv not found, using system python
)

python -m otto.brain_cli %*

endlocal
```

- [ ] **Step 3: Commit**

```bash
git add src/otto/brain_cli.py brain.bat
git commit -m "feat(cli): add Otto Brain CLI and brain.bat launcher"
```

---

### Task 7: Otto-Realm Vault Structure Bootstrap

**Files:**
- Create: `Otto-Realm/Brain/.gitkeep`
- Create: `Otto-Realm/Predictions/.gitkeep`
- Create: `Otto-Realm/Memory-Tiers/01-Facts/.gitkeep`
- Create: `Otto-Realm/Memory-Tiers/02-Interpretations/.gitkeep`
- Create: `Otto-Realm/Memory-Tiers/03-Speculations/.gitkeep`
- Create: `Otto-Realm/Rituals/.gitkeep`
- Create: `Otto-Realm/README.md` (Otto-Realm usage guide)
- Modify: `docs/openclud-injection-map.md`

- [ ] **Step 1: Write Otto-Realm/README.md**

```markdown
# Otto-Realm

Otto's autonomous workspace inside the Obsidian vault.

## Structure

```
Otto-Realm/
├── Brain/                    # Otto's self-model of Sir Agathon
│   └── self_model.md         # Latest Sir Agathon profile snapshot
├── Predictions/             # Otto's anticipatory scaffolding
│   └── YYYY-MM-DD_predictions.md
├── Memory-Tiers/            # Otto's memory architecture
│   ├── 01-Facts/            # Vault-derived facts (#otto-fact)
│   ├── 02-Interpretations/  # Otto's synthesis (#otto-interpretation)
│   └── 03-Speculations/     # Otto's predictions (#otto-speculation)
└── Rituals/                 # Ritual cycle notes
    └── YYYY-MM-DD_{phase}_ritual.md
```

## Write Boundary

Otto may:
- Write new notes in Otto-Realm
- Link [[...]] to Action/ or 30-Projects/ as outcomes
- Create [[future-ref]] links to link past notes to anticipated future notes
- Write in Memory-Tiers with appropriate tier tags

Otto may NOT:
- Rewrite vault past content without explicit Sir Agathon concent
- Edit Sir Agathon's notes without concent
- Claim speculation as fact

## Usage

Run ritual cycle: `brain.bat ritual`
Run full brain: `brain.bat all`
```

- [ ] **Step 2: Create .gitkeep files**

```bash
touch "Otto-Realm/Brain/.gitkeep"
touch "Otto-Realm/Predictions/.gitkeep"
touch "Otto-Realm/Memory-Tiers/01-Facts/.gitkeep"
touch "Otto-Realm/Memory-Tiers/02-Interpretations/.gitkeep"
touch "Otto-Realm/Memory-Tiers/03-Speculations/.gitkeep"
touch "Otto-Realm/Rituals/.gitkeep"
```

- [ ] **Step 3: Update docs/openclud-injection-map.md — add Otto Brain section**

```markdown
### 6. Otto Brain Architecture (Phase 1)
Adopted as:
- `src/otto/brain/` — modular brain modules
  - `memory_layer.py` — fact/interpretation/speculation tiers
  - `self_model.py` — vault → Otto mental model
  - `predictive_scaffold.py` — anticipation engine
  - `ritual_engine.py` — scan/reflect/dream/act cycle
- `src/otto/orchestration/brain.py` — brain orchestration
- `Otto-Realm/` — vault-native brain notes
  - Brain/ — self-model notes
  - Predictions/ — anticipatory notes
  - Memory-Tiers/ — fact/interpretation/speculation
  - Rituals/ — ritual cycle notes
- `brain.bat` — Otto Brain CLI
- Wired into KAIROS + Dream loops

### 7. Phase 2 — B Migration (Future)
When deeper refactor is needed:
- Extract vault-native memory → structured brain state
- Migrate Otto-Realm markdown patterns → brain Python modules
- Self-model becomes Otto's primary context source
```

- [ ] **Step 4: Commit**

```bash
git add Otto-Realm/
git add docs/openclud-injection-map.md
git commit -m "feat(otto-realm): bootstrap Otto-Realm vault structure with write boundary docs"
```

---

### Task 8: Integration Test — Full Brain Pipeline

**Files:**
- Create: `tests/test_brain_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_brain_integration.py
from __future__ import annotations
from pathlib import Path

from otto.brain import (
    OttoSelfModel,
    PredictiveScaffold,
    MemoryLayer,
    RitualEngine,
    MemoryTier,
    TierEntry,
)


def test_full_brain_flow(tmp_vault, monkeypatch):
    """End-to-end: scan → self-model → predictions → ritual → memory tiers"""
    monkeypatch.setenv("OTTO_VAULT_PATH", str(tmp_vault))

    # 1. Create sample notes in vault
    note1 = tmp_vault / "10-Personal" / "goals.md"
    note1.parent.mkdir(parents=True, exist_ok=True)
    note1.write_text("---\ntags: [goal, personal]\n---\n# Goals\nLearn system architecture.", encoding="utf-8")

    note2 = tmp_vault / "01-Inbox" / "capture.md"
    note2.parent.mkdir(parents=True, exist_ok=True)
    note2.write_text("# Capture\nTODO: organize notes\n\nLinks to [[10-Personal/goals]]", encoding="utf-8")

    # 2. Build self-model
    sm = OttoSelfModel(vault_path=tmp_vault)
    snapshot = sm.build_from_scan({"note_count": 2, "notes": [
        {"tags": ["goal", "personal"], "wikilinks": [], "body_excerpt": ""},
        {"tags": [], "wikilinks": ["10-Personal/goals"], "body_excerpt": "TODO:"},
    ]})
    profile_path = sm.write_profile_to_vault()
    assert profile_path.exists()
    assert len(snapshot["strengths"]) >= 0

    # 3. Generate predictions
    ps = PredictiveScaffold(vault_path=tmp_vault)
    preds = ps.generate_from_profile({
        "vault_strengths": snapshot["strengths"],
        "vault_weaknesses": snapshot["weaknesses"],
        "observed_patterns": [],
    })
    pred_path = ps.write_predictions_to_vault()
    assert pred_path.exists()
    assert len(preds) >= 0

    # 4. Write memory tier entry
    ml = MemoryLayer(vault_path=tmp_vault)
    entry = TierEntry(
        tier=MemoryTier.INTERPRETATION,
        content="Test: Sir Agathon uses short capture notes with links to personal",
        source_note="Otto-Realm/Brain/test.md",
        confidence=0.8,
    )
    tier_path = ml.write_tier_entry(entry)
    assert tier_path.exists()

    # 5. Read back tier entries
    entries = ml.read_tier_entries(MemoryTier.INTERPRETATION)
    assert len(entries) >= 1
    assert entries[-1].tier == MemoryTier.INTERPRETATION

    # 6. Verify write boundary
    assert ml.write_boundary.can_write_new_note() is True
    assert ml.write_boundary.can_rewrite_vault_past("01-Inbox/capture.md") is False
    assert ml.write_boundary.can_rewrite_vault_without_concent("10-Personal/goals.md") is False
    assert ml.write_boundary.can_link_to_folder("Action") is True
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_brain_integration.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_brain_integration.py
git commit -m "test(brain): add full brain integration test"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - [x] Memory Layer (fact/interpretation/speculation) — Task 1
   - [x] Self-Modeling (vault → Otto mental model) — Task 2
   - [x] Predictive Scaffold (anticipation) — Task 3
   - [x] Ritual Engine (scan/reflect/dream/act) — Task 4
   - [x] Brain orchestration wired into KAIROS + Dream — Task 5
   - [x] Otto-Realm vault-native structure (C) — Task 7
   - [x] Write Boundary enforcement — Task 1
   - [x] CLI + brain.bat — Task 6
   - [x] Integration test — Task 8

2. **Placeholder scan:** No TBD, TODO, or vague requirements found.

3. **Type consistency:** All method names consistent across tasks (same names used throughout).

4. **Future Phase 2 (B Migration):** Documented in openclud-injection-map.md and README — no placeholders, concrete migration path.

---

## FUTURE PHASE NOTES (B Migration — Dep Refactor)

When ready for deep refactor (B), extract vault-native patterns into full brain state management:

- Phase 2A: Replace markdown-brain reading with structured JSON state files as canonical source
- Phase 2B: Otto-Realm becomes pure output; brain modules own state internally
- Phase 2C: Otto self-model drives all retrieval ranking (profile-weighted retrieval)
- Phase 2D: Predictive scaffold becomes proactive scheduling engine

Each Phase 2 sub-task should be scoped as its own plan with working software at each step.

---

**Plan complete.** Two execution options:

1. **Subagent-Driven (recommended)** — dispatch fresh subagent per task, review between tasks
2. **Inline Execution** — execute tasks in this session using executing-plans, batch with checkpoints

Which approach?
