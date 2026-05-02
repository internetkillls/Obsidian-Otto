# Otto-Obsidian — System Design Notes

> For OpenClaw agents. This is the canonical design document.
> Last updated: 2026-04-17

---

## System Arrangement

Three locations, one coherent system:

| Layer | Path | Role |
|---|---|---|
| **Otto-Otto** (control plane) | `C:\Users\joshu\Obsidian-Otto\` | Pipeline, runtime, Docker, state, config |
| **Otto-Realm** (brain/persona) | `C:\Users\joshu\Josh Obsidian\Otto-Realm\` | Self-model, predictions, memory tiers, rituals, governance |
| **Josh Obsidian** (vault) | `C:\Users\joshu\Josh Obsidian\` | Raw notes, frontmatter, wikilinks — all user content |

**Otto-Otto writes to Otto-Realm but never rewrites vault content.**
**OpenClaw connects to the vault via obsidian-mcp Docker container (stdio transport).**

---

## Container Naming (No Duplicates)

All containers follow `ob-otto-<service>` naming:

| Container | Image | Profile | Port | Purpose |
|---|---|---|---|---|
| `ob-otto-postgres` | postgres:16-alpine | always | 54329→5432 | Events journal, vault_signals, profiles |
| `ob-otto-adminer` | adminer:latest | always | 18080→8080 | Postgres web UI |
| `ob-otto-chromadb` | chromadb/chroma:latest | vector | 18000→8000 | Vector embeddings, semantic search |
| `ob-otto-obsidian-mcp` | custom build | mcp | stdio | Obsidian MCP server |

**Duplicate prevention:** `_docker_service_running(name)` checks before any `up`. `docker-compose.yml` uses explicit `container_name:` — Docker refuses a second container with the same name.

---

## The Three DBs

### DB-A: PostgreSQL (`ob-otto-postgres`)
Port 54329, DB `otto`, user/pass `otto`.
Schema:
- `events` — all EventBus publishes (pipeline, KAIROS, Dream, Brain events)
- `vault_signals` — chaos scores + scarcity flags written by VaultSignalTools
- `profiles` — persona snapshots per session

Fed by: EventBus.publish() → JSONL (always) + Postgres (best-effort)
Used by: KAIROS profiling, retrieval, event cadence analysis

### DB-B: SQLite (`otto_silver.db`)
Location: `external/sqlite/otto_silver.db`
Tables: `notes`, `attachments`, `folder_risk`, `notes_fts` (FTS5)
Fed by: Bronze scan → Silver normalization pipeline
Used by: Fast text search, folder risk, pipeline summaries

### DB-C: ChromaDB (`ob-otto-chromadb`)
Port 18000, collection `otto_gold`
Fed by: Gold builder — note chunks with metadata
Used by: Semantic search, dream signal alignment, retrieval

---

## RAG Context Design

On every KAIROS and Dream cycle, context is retrieved from all 3 DBs:

```
build_rag_context(goal, query)
  ├── SQLite FTS5  → note hits (title + frontmatter + body excerpt)
  │                 folder_risk top-5 folders
  ├── ChromaDB     → semantic chunks (max 4000 chars)
  │                 Otto-Realm memory embeddings (max 2000 chars)
  ├── Postgres     → last 7 days events (time-boxed)
  │                 unresolved vault_signals (DISTINCT ON note_path+signal_type)
  └── VaultSignalTools → chaos scores from bronze_manifest.json

Total bounded to 120,000 tokens via LongContextLimiter
Priority: postgres signals > sqlite > chroma > vault_signals
```

RAG context appears in:
- `artifacts/reports/kairos_daily_strategy.md` — `# RAG Context` section at top
- `artifacts/reports/dream_summary.md` — `# RAG Context` section at top

---

## Automation DAGs

### Runtime Loop (24/7 Background Process)
```
runtime_loop.py
  ├── bootstrap_docker_services()
  │     ├── postgres + adminer (always)
  │     ├── chromadb (profile: vector)
  │     └── obsidian-mcp (profile: mcp)
  │     └── init_pg_schema() → creates events + vault_signals tables
  │
  ├── run_kairos_once() [every kairos_minutes default=15]
  │     ├── build_rag_context() → sqlite + chroma + postgres + vault_signals
  │     ├── write kairos_daily_strategy.md (with RAG context block)
  │     ├── append to state/kairos/heartbeat.jsonl
  │     └── run_brain_predictions() → Otto-Realm/Predictions/
  │
  └── run_dream_once() [every dream_minutes default=30]
        ├── build_rag_context() → same sources
        ├── VaultDreamSource.ingest_since_last()
        │     ├── scan Otto-Realm areas since last mtime
        │     ├── strip diary headers / openclaw markers
        │     └── append to memory/.dreams/session-corpus/YYYY-MM-DD-vault-NN.txt
        ├── write dream_summary.md (with RAG context block)
        └── run_brain_self_model() → Otto-Realm/Brain/self_model.md
```

### Pipeline Loop (Bronze → Silver → Gold)
```
run_pipeline.py --full
  ├── scan_vault() [Bronze]
  │     └── data/bronze/bronze_manifest.json
  ├── build_silver() [Silver]
  │     └── external/sqlite/otto_silver.db (notes, attachments, folder_risk, FTS5)
  └── build_gold() [Gold]
        ├── artifacts/summaries/gold_summary.json
        ├── artifacts/reports/gold_summary.md
        └── ChromaDB collection otto_gold (vector chunks)
```

### MCP Launch Flow
```
launch-mcp.bat
  ├── docker compose build obsidian-mcp
  ├── _get_container_id("ob-otto-obsidian-mcp")
  │     └── if not running → docker compose up -d --no-recreate obsidian-mcp
  └── docker exec -i <container_id> node dist/index.js
        └── OpenClaw connects via stdio transport
```

---

## KAIROS Profiling Inputs

KAIROS does not profile from JSON files alone. It reads:

```
run_kairos_once()
  ├── SQLite      → gold_summary.json (folder_risk scores)
  ├── Postgres    → events.jsonl (cadence), vault_signals (chaos)
  ├── ChromaDB    → Otto-Realm memory embeddings (past strategies)
  └── VaultSignalTools → bronze_manifest.json chaos scores

Output:
  ├── kairos_daily_strategy.md (strategy per top folder)
  ├── state/kairos/heartbeat.jsonl
  └── Otto-Realm/Predictions/YYYY-MM-DD_predictions.md
```

---

## OpenClaw's Role

OpenClaw is the **agent execution layer**. It:
1. Reads `Otto-Realm/GOVERNANCE.md` and this file for system design
2. Connects to vault via `ob-otto-obsidian-mcp` (MCP stdio transport)
3. Issues tool calls → Otto executes → results returned via MCP

**Otto does NOT proxy OpenClaw calls. OpenClaw calls the MCP server directly.**

MCP tools available:
- `obsidian_read_note` — read a note by path
- `obsidian_search_notes` — full-text search across vault
- `obsidian_list_notes` — list notes with optional filters

---

## OpenClaw Config (`.openclaw/openclaw.json`)

Key settings:
- `workspace`: `C:\Users\joshu\Josh Obsidian`
- `plugins.memory-core.config.dreaming.enabled`: `true`
- `models.providers.huggingface`: Qwen/Qwen2.5-72B-Instruct (fallback on 529)
- `channels.telegram`: Otto bot (env: TELEGRAM_BOT_TOKEN)

**Managed sections** (Otto owns and syncs these):
- `agents.defaults.cliBackends`
- `agents.defaults.models`
- `agents.defaults.heartbeat`
- `models.providers`

---

## State Directory Structure

```
state/
  bootstrap/latest.json      — vault_path, docker_enabled, gold_top_folders
  checkpoints/pipeline.json  — last scope, bronze_notes, training_ready
  handoff/latest.json        — goal, status, next_actions
  kairos/heartbeat.jsonl     — KAIROS pulse history
  dream/dream_state.json     — dream cycle state
  run_journal/events.jsonl   — all EventBus events
  openclaw/sync_status.json  — sync health
  openclaw/fallback_events.jsonl
  pids/runtime.pid           — runtime process ID
  launcher/mcp_last_run.json — MCP launch result
  dream/vault_ingestion.json  — Otto-Realm area mtimes
```

---

## Read/Write Boundaries

| Data | Who Writes | Who Reads |
|---|---|---|
| `state/` (Otto-Otto) | Otto-Otto only | Otto-Otto only |
| `Otto-Realm/Brain/` | Otto-Otto brain module | Otto-Otto + OpenClaw |
| `Otto-Realm/Predictions/` | Otto-Otto brain module | Otto-Otto + OpenClaw |
| `Otto-Realm/Memory-Tiers/` | Otto-Otto brain module | Otto-Otto + OpenClaw |
| `Josh Obsidian/*` (vault) | **Otto never** | Otto Bronze scan + MCP + OpenClaw |
| SQLite `otto_silver.db` | Otto-Otto pipeline | Otto-Otto, KAIROS, retrieval |
| ChromaDB `otto_gold` | Otto-Otto Gold step | Otto-Otto, VaultSignalTools, retrieval |
| Postgres `otto` DB | Otto-Otto events | KAIROS, retrieval, adminer |

---

*This document is the ground truth. Update Otto-Realm/OTTO-DESIGN.md first if you update anything.*