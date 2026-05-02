# Vault-to-Dream Ingredients Pipeline

**Date:** 2026-04-17
**Status:** Design draft
**Owner:** Otto-Obsidian control plane

---

## 1. Problem Statement

Dream consolidation sekarang (`dream.py:run_dream_once()`) bahan utamanya:
- `handoff/latest.json` — goal, next actions
- `checkpoints/pipeline.json` — pipeline state
- 12-line tail `otto.log`
- 12-line tail `events.jsonl`
- `session-ingestion.json` — session corpus metadata (sudah di-digest sesi mana)
- `daily-ingestion.json` — referensi ke `memory/2026-04-13.md`, `memory/2026-04-14.md`

Vault content (`C:\Users\joshu\Josh-Obsidian`) **belum masuk sebagai bahan dreaming secara langsung**. Vault baru dipakai lewat `run_brain_self_model()` — yang **write** self-model ke vault, bukan baca vault sebagai bahan.

KAIROS profiling (`HEARTBEAT.md`) punya cadangannya sendiri, tapi dream dan KAIROS punya peran berbeda:
- **KAIROS** → operational telemetry, risk, cadence (terdekteksi di `state/kairos/`)
- **Dream** → poetic consolidation, pattern recognition, identity synthesis dari bahan vault
- **Brain/self_model** → writeback artifact, bukan bahan mentah

**Arrangement Otto-Otto ↔ .Otto-Realm:**
- OpenClaw `heartbeat.target` → **full vault** (`C:\Users\joshu\Josh Obsidian`) — Otto operates on entire vault
- .Otto-Realm → **dream queue target** — results written here by dream pipeline
- Dream pre-tools → **full vault scan** via bronze manifest (chaos, signals, ranked search)

---

## 2. Design Goals

1. **Vault content sebagai primary dreaming material** — bukan lagi hanya operational state
2. **Ingestion tracking** — hanya baca vault notes yang berubah sejak last dream cycle
3. **Dual-lane read contract** — dream ingredients tetap scoped ke canonical persona areas; full-vault scan hanya untuk diagnostics/ranking, bukan bahan naratif utama
4. **Non-blocking** — failure baca satu area tidak crash dream cycle
5. **KAIROS tetap terpisah** — heartbeat profiling tetap di `otto-profile-cycle`, dream tetap fokus di identity synthesis dan pattern recognition dari vault

---

## 3. .Otto-Realm Canonical Areas for Dreaming

Dari `.Otto-Realm/README.md`, area yang relevan untuk dreaming:

| Area | Path (relative to vault root) | Role in Dream |
|---|---|---|
| Heartbeats | `.Otto-Realm/Heartbeats/*.md` | Recent care signals, cadence, Josh state |
| Brain/self_model | `.Otto-Realm/Brain/self_model.md` | Current Otto self-model snapshot |
| Profile Snapshot | `.Otto-Realm/Profile Snapshot.md` | Sir Agathon profile |
| Central Schedule | `.Otto-Realm/Central Schedule.md` | Time structure, rhythm |
| Memory-Tiers | `.Otto-Realm/Memory-Tiers/**/*.md` | Fact/interpretation/speculation tiers |
| Rituals | `.Otto-Realm/Rituals/*.md` | Ritual outcomes |
| Predictions | `.Otto-Realm/Predictions/*.md` | Predictive scaffold outputs |

**Daily notes dan project notes TIDAK masuk** — terlalu noisy. Scope ingredients dibatasi ke `.Otto-Realm` canonical areas.
**Alias policy:** jika dokumen lama menulis `Otto-Realm/`, interpretasinya adalah `.Otto-Realm/` (dengan titik).

---

## 4. Component: `DreamIngredients`

### Location
`src/otto/orchestration/dream_ingredients.py`

### Class: `VaultDreamSource`

```
__init__(vault_path: Path)
  vault_path   — resolve ke C:\Users\joshu\Josh-Obsidian
  manifest_path — state/dream/vault_ingestion.json

ingest() -> list[DreamMaterial]
  1. Load manifest (mtime per area + last_dream_ts)
  2. For each area, scan for notes with mtime > last_dream_ts
  3. Return list of DreamMaterial fragments
```

### Class: `DreamMaterial`

```python
@dataclass
class DreamMaterial:
    area: str              # "heartbeats" | "brain" | "memory-tiers" | "rituals"
    source_path: str       # full relative path
    mtime: str             # ISO
    content_excerpt: str    # max 500 chars, stripped frontmatter
    tags: list[str]        # extracted from frontmatter
    confidence: float      # 0.8 for canonical areas
```

### Ingestion manifest: `state/dream/vault_ingestion.json`

```json
{
  "version": 1,
  "last_dream_ts": "2026-04-17T10:00:00+07:00",
  "areas": {
    "heartbeats": { "mtime": "2026-04-17T09:45:00+07:00", "note_count": 12 },
    "brain":      { "mtime": "2026-04-16T22:00:00+07:00", "note_count": 1  },
    "memory-tiers": { "mtime": "2026-04-17T08:00:00+07:00", "note_count": 34 },
    "rituals":    { "mtime": "2026-04-15T20:00:00+07:00", "note_count": 5  },
    "predictions": { "mtime": "2026-04-14T12:00:00+07:00", "note_count": 3  }
  }
}
```

Ingestion logic:
- Jika `mtime` area > `last_dream_ts` → area perlu di-re-read
- Jika area mtime tidak berubah → skip, tidak masuk corpus
- `last_dream_ts` di-update setiap kali `run_dream_once()` sukses

### Error handling

- Area tidak ada (dir not exist) → log warning, skip area
- File read fails → log error, skip file, continue
- Manifest corrupted → treat as fresh start (log warning, reset)

---

## 5. Integration: `dream.py` Updated Flow

Updated `run_dream_once()` sequence:

```
1. Load state, paths, model          (existing)
2. Read operational state            (existing: handoff, checkpoint, logs)
3. [NEW] Ingest vault dream materials (DreamIngredients.ingest())
4. [NEW] Merge vault_materials into session corpus
5. Build dream report                  (existing: stable_facts, unresolved, failures)
6. [NEW] Append vault_materials to dream_summary.md sections
7. write_json(state.dream, dream_state)
8. publish EVENT_DREAM
9. run_brain_self_model()             (existing — writeback to vault)
10.[NEW] Update vault_ingestion manifest (set last_dream_ts)
```

### Updated `dream_summary.md` sections

Existing sections preserved:
- Stable facts
- Unresolved
- Repeated operational failures
- Recent log tail
- Recent event tail

**New sections:**

```
## Vault Dream Materials (since last cycle)

### Heartbeats
- 2026-04-17 09:45 — [excerpt] — [[.Otto-Realm/Heartbeats/...md]]

### Self-Model Delta
- [delta from previous self_model if changed]

### Memory-Tier Signals
- [recent tier entries, top 5 by confidence]
```

---

## 6. Separation from KAIROS

| | KAIROS (otto-profile-cycle) | Dream (vault-dream-ingredients) |
|---|---|---|
| **Trigger** | HEARTBEAT schedule (3h cadence) | dream schedule (TBD — likely 12h atau event-driven) |
| **Bahan utama** | `artifacts/summaries/gold_summary.json`, scoped raw vault reads | `.Otto-Realm` canonical areas via `VaultDreamSource` |
| **Output** | `otto_profile.md`, handoff update, run journal | `dream_summary.md` with vault sections, DREAMS.md diary |
| **Method** | RTW/IB/SDZ lens, factual profiling | Poetic synthesis, pattern recognition, identity |
| **Profiling?** | YES — strengths, weaknesses, monetizable skills | NO — itu KAIROS. Dream ADD profiling hanya lewat self_model writeback |
| **Josh-facing?** | Indirect (profile artifact) | Yes (diary entries di DREAMS.md) |

Dream **tidak** menambah profiling secara langsung. Profiling tetap di KAIROS territory. Dream ADD ke profiling hanya melalui:
- `run_brain_self_model()` yang write ke `.Otto-Realm/Brain/self_model.md`
- Self-model itu yang dibaca KAIROS di cycle berikutnya

---

## 7. VaultSignalTools — Full Vault Diagnostics Tools

### Location
`src/otto/orchestration/vault_signal_tools.py`

### Purpose
Serve Otto's main design and core values: knowing Josh deeply, surfacing what needs attention, and feeding the dream pipeline with vault-wide signals. This lane is diagnostic/governance only and does not replace scoped `.Otto-Realm` ingredients as narrative source.

### Three tools

| Tool | Method | Output |
|---|---|---|
| `list_chaos_to_order()` | Rank all 1322 notes by chaos score (missing frontmatter, no wikilinks, no scarcity, no cluster, no tags, no necessity, stale age) | Top-N chaotic notes |
| `search_signals()` | Query full vault by signal type (scarcity, tag, cluster, orientation, allocation, necessity, orphan) | Signal hits with confidence |
| `rank_vault_search()` | Free-text query ranked by term match + signal alignment | Ranked results with signal match labels |

### Chaos factors & weights
```
no_frontmatter:  1.5  (high — governance signal)
no_wikilinks:    1.0  (medium — orphan risk)
no_scarcity:     0.8  (medium — no intellectual positioning)
no_cluster:      0.7  (low-medium — not placed in 8-cluster)
no_tags:         0.6  (low — discipline gap)
no_necessity:    0.5  (low — goal clarity gap)
stale (>30d):    +0.02 per day (up to 3.0 cap)
```

### Alignment to Otto's core values
- Warm + rigorous: chaos surfacing is care, not judgment
- AuDHD-aware: surface what needs tending without overwhelming
- Theoretical spine: scarcity signals reveal Josh's intellectual agenda
- Governance: frontmatter completeness = respect for the system

## 8. Full Dream Pipeline Flow

```
run_dream_once()
  1. Load operational state          (handoff, checkpoint, logs, events) — existing
  2. VaultDreamSource.ingest_since_last()   → DreamMaterial[] from .Otto-Realm areas (scoped ingredients lane)
  3. VaultSignalTools.list_chaos_to_order()  → ChaosScore[] from full vault (diagnostics lane)
  4. VaultSignalTools.search_signals()       → SignalHit[] from full vault (diagnostics lane)
  5. Build dream_summary.md          (stable facts, unresolved, failures + vault sections)
  6. Write vault corpus file        (memory/.dreams/session-corpus/2026-*-vault-*.txt)
  7. run_brain_self_model()         → write .Otto-Realm/Brain/self_model.md
  8. Update vault_ingestion manifest (set last_dream_ts per area)
```

Dream writeback target: `.Otto-Realm/` (Brain, Heartbeats, Memory-Tiers, Predictions, Rituals)
Vault pre-tools source: full vault bronze manifest (`data/bronze/bronze_manifest.json`)

### 8.1 Telemetry Mapping to Triad A→B→C Contract

Extension flow `run_dream_once()` wajib emit/propagate field telemetry berikut agar kompatibel dengan `2026-04-17-kairos-morpheus-otto-design.md` §6.2:

| `run_dream_once()` step | Required telemetry field(s) | Contract |
|---|---|---|
| Step 1 (load operational state) | `phase=A`, `source=heartbeat|vault` | intake source tercatat |
| Step 2 (scoped ingest) | `phase=B`, `source=vault`, `morpheus_layer=continuity` | narrative continuity dari `.Otto-Realm` |
| Step 3-4 (full-vault diagnostics) | `phase=B`, `source=vault`, `morpheus_layer=none` | diagnostics tidak dianggap naratif dream |
| Step 5-6 (build/write dream artifacts) | `phase=C`, `morpheus_layer=aesthetic|continuity` | output dream layer teridentifikasi |
| Step 7 (self model writeback) | `phase=C`, `source=council|vault`, `morpheus_layer=embodiment|continuity` | writeback persona/identity tercatat |
| Step 8 (manifest update) | `phase=C`, `next_action`, `duration_ms` | loop integrity + timing |

Minimal envelope event tetap mengikuti schema triad: `ts`, `cycle_id`, `phase`, `source`, `kairos_score`, `gold_promoted`, `council_triggered`, `morpheus_layer`, `openclaw_fetch`, `meta_gov_flag`, `next_action`, `duration_ms`.

## 9. Otto-Otto ↔ .Otto-Realm Arrangement (canonical)

| Concern | Location |
|---|---|
| OpenClaw `heartbeat.target` | `C:\Users\joshu\Josh Obsidian` (full vault) |
| Otto control plane state | `C:\Users\joshu\Obsidian-Otto\state\` |
| Otto brain / persona | `C:\Users\joshu\Josh Obsidian\.Otto-Realm\` |
| `vault_path` (paths.yaml) | `C:\Users\joshu\Josh Obsidian` |
| Dream ingredients source (.Otto-Realm areas) | `.Otto-Realm/Brain`, `Heartbeats`, `Memory-Tiers`, `Rituals`, `Predictions` |
| Dream writeback target | `.Otto-Realm/` |
| Vault pre-tools source | Bronze manifest (`data/bronze/bronze_manifest.json`) |

## 10. File Changes

### New files
- `src/otto/orchestration/dream_ingredients.py` — `VaultDreamSource`, `DreamMaterial`, `VaultIngestionManifest`
- `src/otto/orchestration/vault_signal_tools.py` — `VaultSignalTools`, `ChaosScore`, `SignalHit`, `RankedResult`
- `config/dream.yaml`

### Modified files
- `.openclaw/openclaw.json` — `heartbeat.target` → full vault, `memory-core` config
- `src/otto/orchestration/dream.py` — integrate vault ingestion + vault signal tools
- `config/paths.yaml` — `vault_path` → `C:\Users\joshu\Josh Obsidian`
- `.Otto-Realm/README.md` — canonical arrangement

### State
- `state/dream/vault_ingestion.json`

## 11. Not in Scope

- Bronze scan frontmatter parsing fix (separate issue)
- Changing DREAMS.md diary format
- KAIROS cadence modification
- MCP integration for vault reads
