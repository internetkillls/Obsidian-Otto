# Glossary

## Data pipeline

### Bronze
Raw extracted vault inventory. Discovered notes, attachments, frontmatter, links, tags. Minimal parsing — assumptions minimized.

### Silver
Normalized relational data store. SQLite-backed. Folder risk tables, FTS search, queryable metadata.

### Gold
Decision-ready curated data bundle. Folder risk scoring, training readiness, retrieval summaries, KAIROS inputs.

## State and continuity

### Handoff
Structured external memory packet between sessions. Written to `state/handoff/latest.json`. Check before asking questions.

### Checkpoint
Pipeline snapshot at a point in time. Written to `state/checkpoints/*.json`. Authoritative record of what was scanned.

### Run journal
Append-only event log. `state/run_journal/*.jsonl`. Never truncate.

## Operator

### Launcher
Python-based operator console at `main.bat`. Thin BAT shims delegate to `scripts/manage/run_launcher.py`. Two screens: home and advanced.

### Runtime
Background loop managed by `runtime_loop.py`. PID stored in `state/pids/runtime.pid`. Launcher checks for staleness on startup.

## Telemetry

### KAIROS
Heartbeat and strategic refinement layer. Runs on a daily cadence (configurable). Inputs: retrieval misses, hygiene drift, recurring problems.

### Dream
Nightly consolidation layer. Compresses stable facts, resolves blockers, surfaces open questions.

## Routing

### Intent
Classified user query type. Determined by `config/routing.yaml` trigger matching or LLM router.

### Persona
Behavioral mode for the active session. 7 personas defined in `config/personas.yaml`.

### Kernelization
Delta-collapse mechanism for non-premium model tiers. Ensures consistent output structure across tier changes.
