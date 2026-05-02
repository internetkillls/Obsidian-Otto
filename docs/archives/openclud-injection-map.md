# OpenClud Injection Map

## Boundary

The uploaded `OpenClud-code-source-code-patch-1.zip` identifies itself as:

- `UNLICENSED`
- leaked / proprietary in its own notice

So this rebuild does **not** copy code from it.

## What was injected clean-room

### 1. Control-room mindset
Adopted as:
- `tui.bat`
- `status.bat`
- live dashboard
- operator-first repo structure

### 2. KAIROS heartbeat idea
Adopted as:
- `src/otto/orchestration/kairos.py`
- `config/kairos.yaml`
- daily strategy artifacts

### 3. Dreaming-mode consolidation
Adopted as:
- `src/otto/orchestration/dream.py`
- `artifacts/reports/dream_summary.md`

### 4. task / worker discipline
Adopted as:
- `tasks/`
- custom Codex agents
- run journal + handoff packets

### 5. tool registry / event telemetry discipline
Adopted as:
- `src/otto/events.py`
- `logs/`
- `state/run_journal/`

### 6. Otto Brain Architecture (Phase 1)
Adopted as:
- `src/otto/brain/` — modular brain modules
  - `memory_layer.py` — fact/interpretation/speculation tiers
  - `self_model.py` — vault scan to Otto mental model
  - `predictive_scaffold.py` — anticipation engine
  - `ritual_engine.py` — scan/reflect/dream/act cycle
- `src/otto/orchestration/brain.py` — brain orchestration
- `src/otto/brain_cli.py` + `brain.bat` — CLI launcher
- `Otto-Realm/` — vault-native brain notes
  - Brain/ — self-model notes
  - Predictions/ — anticipatory notes
  - Memory-Tiers/ — fact/interpretation/speculation
  - Rituals/ — ritual cycle notes
- Wired into KAIROS + Dream loops via events

### 7. Phase 2 — B Migration (Future)
When deeper refactor is needed:
- Phase 2A: Replace markdown-brain reading with structured JSON state files as canonical source
- Phase 2B: Otto-Realm becomes pure output; brain modules own state internally
- Phase 2C: Otto self-model drives all retrieval ranking (profile-weighted retrieval)
- Phase 2D: Predictive scaffold becomes proactive scheduling engine
