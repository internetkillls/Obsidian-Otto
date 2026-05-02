# Otto-Obsidian Governance

> "The system must be coherent. Every container, every DB, every loop has a name, a purpose, and a master." — Sir Agathon

---

## 1. Arrangement: Three Locations, One System

| Layer | Location | Role |
|---|---|---|
| **Otto-Otto** (control plane) | `C:\Users\joshu\Obsidian-Otto\` | State, pipeline, runtime, config, logs, Docker Compose |
| **Otto-Realm** (brain/persona) | `C:\Users\joshu\Josh Obsidian\Otto-Realm\` | Self-model, predictions, memory tiers, rituals, brain outputs |
| **Josh Obsidian** (vault) | `C:\Users\joshu\Josh Obsidian\` | Raw notes, frontmatter, wikilinks, all user content |

> Otto-Otto **reads and writes** to Otto-Realm. Otto-Otto **never rewrites** vault content without Sir Agathon's consent.
> Otto-Otto **reads** the vault for bronze scanning and signal detection.

---

## 2. Docker Containers: Naming Convention & State Machine

### Naming Pattern
`ob-otto-<service>`

All containers managed by Otto-Otto follow this prefix. No exceptions.

### Container Registry

| Container Name | Image | Profile | Purpose | State |
|---|---|---|---|---|
| `ob-otto-postgres` | `postgres:16-alpine` | always | Events journal, run_journal, structured KV | running |
| `ob-otto-adminer` | `adminer:latest` | always | Postgres web UI (port 18080) | running |
| `ob-otto-chromadb` | `chromadb/chroma:latest` | vector | Vector embeddings, semantic search | running |
| `ob-otto-obsidian-mcp` | custom build | mcp | Obsidian MCP server (stdio transport) | running |

### Container Guard (no duplicates)

Before any `docker compose up` or `docker exec`, Otto-Otto always checks:

```python
# runtime.py — bootstrap_docker_services()
def _docker_service_running(name: str) -> bool:
    result = subprocess.run(
        ["docker", "ps", "-q", "-f", f"name={name}"],
        capture_output=True, text=True, check=False,
    )
    return bool(result.stdout.strip())
```

Only `docker compose up -d --no-recreate` if the container is not already running.
The `docker-compose.yml` uses explicit `container_name:` — Docker refuses to create a second container with the same name, which serves as a hard guard.

---

## 3. The Three DBs and Their Roles

### DB-A: PostgreSQL (`ob-otto-postgres`)
- **Port:** 54329 (host) → 5432 (container)
- **DB:** `otto`
- **User/Pass:** `otto` / `otto`
- **Schema targets:**
  - `events` — full event journal (run_journal events, pipeline events, KAIROS pulses)
  - `retrieval_state` — session memory, query context
  - `vault_signals` — chaos scores, scarcity flags written by KAIROS
  - `profiles` — persona snapshots per session
- **Fed by:** pipeline events, runtime heartbeats, vault signal tools
- **Used by:** retrieval queries, KAIROS profiling, runtime diagnostics

### DB-B: SQLite (`otto_silver.db`)
- **Location:** `external/sqlite/otto_silver.db`
- **Tables:** `notes`, `attachments`, `folder_risk`, `notes_fts` (FTS5)
- **Fed by:** Bronze scan → Silver normalization pipeline step
- **Used by:** Fast text search, folder risk queries, pipeline summaries

### DB-C: ChromaDB (`ob-otto-chromadb`)
- **Port:** 18000 (host) → 8000 (container)
- **Collection:** `otto_gold` (default)
- **Persistence:** `external/chroma_store/`
- **Fed by:** Gold builder — note chunks with metadata
- **Used by:** Semantic search, dream consolidation signal alignment, VaultSignalTools

---

## 4. RAG Context Design

On every KAIROS and Dream cycle, the model prompt is grounded with data from all 3 DBs.

### RagContextBuilder (src/otto/retrieval/rag_context.py)

```
build_rag_context(goal, query)
  ├── _sqlite_fts(query)         → top-8 FTS5 note hits (title + frontmatter + body excerpt)
  │                                top-5 folder_risk rows (risk scores)
  ├── _chroma_semantic(query)    → top-10 semantic chunks (max 4000 chars)
  │                                Otto-Realm memory embeddings (max 2000 chars)
  ├── _postgres_events()         → last 7 days of events (time-boxed)
  │                                unresolved vault_signals (DISTINCT ON dedup)
  └── _vault_chaos_signals()     → bronze_manifest.json chaos scores via VaultSignalTools

Total bounded to 120,000 tokens via LongContextLimiter
Priority shrinking: postgres > sqlite > chroma > vault_signals
```

### Long Context Limiter

```
LongContextLimiter.bound(slices)
  - If total ≤ 120k tokens: return all slices
  - If overflow: shrink lowest-priority slices proportionally
  - Hard cap: KAIROS first 80 lines, Dream first 120 lines
  - char_budget = max_tokens × 4 (chars equivalent)
```

### RAG in KAIROS

```
run_kairos_once()
  ├── build_rag_context(goal="kairos daily strategy", query="metadata repair")
  │     └── returns 4 ContextSlice: sqlite, postgres×2, vault_signals
  ├── log: "[kairos] RAG context: [sources], N tokens"
  ├── Insert RAG block at top of kairos_daily_strategy.md
  └── record: {rag_tokens, rag_sources} in heartbeat.jsonl
```

### RAG in Dream

```
run_dream_once()
  ├── build_rag_context(goal="dream consolidation", query="vault signals chaos")
  ├── Insert RAG block at top of dream_summary.md
  └── record: {rag_tokens, rag_sources} in dream_state.json
```

---

## 5. Automation DAGs

### 5.1 Runtime Loop (24/7 Background Process)

```
runtime_loop.py
  ├── bootstrap_docker_services()
  │     ├── _docker_service_running() check per container
  │     ├── _docker_up() with profiles
  │     └── postgres + adminer + chromadb (vector) + obsidian-mcp (mcp)
  ├── run_kairos_once() [every kairos_minutes]
  │     ├── read gold_summary.json from SQLite reports
  │     ├── read checkpoint.json
  │     ├── read events.jsonl
  │     ├── write kairos_daily_strategy.md
  │     ├── append to state/kairos/heartbeat.jsonl
  │     └── run_brain_predictions() → Otto-Realm/Predictions/
  └── run_dream_once() [every dream_minutes = 2×kairos]
        ├── _tail events.jsonl
        ├── VaultDreamSource.ingest_since_last()
        │     ├── read Otto-Realm area mtimes
        │     ├── scan changed files since last run
        │     ├── strip diary headers / openclaw markers
        │     └── append to memory/.dreams/session-corpus/YYYY-MM-DD-vault-NN.txt
        ├── VaultSignalTools (full vault scan)
        │     ├── list_chaos_to_order() → postgres vault_signals table
        │     ├── search_signals(scarcity/tag/cluster/orientation)
        │     └── rank_vault_search() → ChromaDB semantic match
        ├── write dream_summary.md
        ├── write state/dream/dream_state.json
        └── run_brain_self_model() → Otto-Realm/Brain/self_model.md

### 5.5 KAIROS Deep-Dive System (TUI + Chat)

```
KAIROS TUI (otto cli kairos-tui) OR Chat (otto cli kairos-chat "<cmd>")
Commands:
  scan               → full vault telemetry (uselessness + training worth)
  dig <folder>       → deep-dive: per-note quality + repair recommendations
  train [on <area>]  → training targets (high signal areas)
  file <path.md>     → single note analysis + recommendations
  date <from> <to>   → notes modified in date range
  what's useless     → dead zones (high uselessness areas)
  directives          → full directive manifest (dig/train/refine)
  help               → command list

KAIROSChatHandler: natural language router for Telegram + OpenClaw
  format_telegram() → Telegram-friendly markdown output

KAIROSDirectiveEngine.produce_directives():
  - run_vault_telemetry() → per-area quality scores
  - build_rag_context()  → RAG-grounded evidence
  → produce Directive objects (dig/train/refine) per area
  → save to state/kairos/directives_NNNN.json + directives_latest.json
```

### 5.5 Pipeline Loop (Bronze → Silver → Gold)

```
run_pipeline.py --full
  ├── scan_vault() [Bronze]
  │     ├── read all MD files from vault_path
  │     ├── extract frontmatter, tags, wikilinks, scarcity fields
  │     ├── write data/bronze/bronze_manifest.json
  │     └── emit EVENT_PIPELINE_BRONZE + EVENT_CACHE_RAW_READY
  ├── build_silver() [Silver]
  │     ├── read bronze_manifest.json
  │     ├── write to SQLite: notes, attachments, folder_risk
  │     ├── build FTS5 index on title + frontmatter + body_excerpt
  │     ├── write artifacts/reports/silver_summary.json
  │     └── emit EVENT_PIPELINE_SILVER + EVENT_CACHE_SQL_READY
  ├── build_gold() [Gold]
  │     ├── read SQLite folder_risk for top risky folders
  │     ├── read bronze manifest for scarcity/orientation/necessity fields
  │     ├── build_vector_cache() → ChromaDB
  │     ├── write artifacts/summaries/gold_summary.json
  │     ├── write artifacts/reports/gold_summary.md
  │     └── emit EVENT_PIPELINE_GOLD + EVENT_CACHE_VECTOR_READY
  └── write checkpoint + handoff
```

### 5.4 MCP Launch Flow

```
launch-mcp.bat  OR  launcher.py → action: launch-mcp
  ├── docker_available() check
  ├── docker_daemon_running() check
  ├── docker compose build obsidian-mcp
  ├── _get_container_id("ob-otto-obsidian-mcp")
  │     └── if not running → docker compose up -d --no-recreate obsidian-mcp
  └── docker exec -i <container_id> node dist/index.js
        └── OpenClaw connects via stdio transport
```

---

## 6. KAIROS Profiling: How All 3 DBs Feed It

KAIROS does not profile from JSON files alone. It reads from the full data stack:

```
run_kairos_once()
  ├── reads SQLite: gold_summary.json (folder_risk scores, top folders)
  ├── reads Postgres: events.jsonl (last 20 events, cadence patterns)
  ├── reads ChromaDB: Otto-Realm Memory-Tiers embeddings (memory context)
  ├── reads local: checkpoint.json (pipeline state)
  └── outputs:
        ├── kairos_daily_strategy.md (strategy per top folder)
        ├── state/kairos/heartbeat.jsonl (postgres events table + local jsonl)
        └── Otto-Realm/Predictions/YYYY-MM-DD_predictions.md (brain predictions)
```

**Vault Telemetry (what to dig / what to train):**
- `VaultTelemetryEngine` scores every area on uselessness + training worth
- Uselessness: no_frontmatter ×2.0, no_tags×1.5, orphan×1.8, duplicate×1.5
- Training worth: frontmatter ×1.0, signal_density×1.0, recency×0.5, uniqueness×0.5
- Outputs: `dig_targets` (critical/high priority repair), `train_targets` (high signal areas)
- `KAIROSDirectiveEngine` produces action directives: dig / train / refine

**Vector context integration:**
- Before generating strategy, KAIROS queries ChromaDB for recent Memory-Tier embeddings
- Top 3 semantically similar past strategies inform the new strategy tone
- This makes KAIROS self-referential — it learns from its own past reasoning

---

## 7. Container Init Sequence (Startup Order)

```
Otto boots
  ├── runtime_loop.py starts (DETACHED_PROCESS)
  │     ├── write_pid() → state/pids/runtime.pid
  │     └── bootstrap_docker_services()
  │           ├── ① postgres + adminer up (no profile)
  │           ├── ② chromadb up (profile: vector)
  │           └── ③ obsidian-mcp up (profile: mcp)
  ├── kairos loop starts (every 15 min default)
  └── dream loop starts (every 30 min default)
```

Containers are **always-on**. Otto does not create/destroy containers mid-session.
If a container dies, `bootstrap_docker_services()` will re-detect it as not running and restart it.

---

## 8. Read/Write Boundaries

| Data | Who Writes | Who Reads |
|---|---|---|
| `state/` (Otto-Otto) | Otto-Otto only | Otto-Otto only |
| `Otto-Realm/Brain/` | Otto-Otto (brain module) | Otto-Otto + OpenClaw |
| `Otto-Realm/Predictions/` | Otto-Otto (brain module) | Otto-Otto + OpenClaw |
| `Otto-Realm/Memory-Tiers/` | Otto-Otto (brain module) | Otto-Otto + OpenClaw |
| `Otto-Realm/Rituals/` | Otto-Otto (ritual engine) | Otto-Otto + OpenClaw |
| `Josh Obsidian/*` (vault) | Otto-Otto **never** (read-only) | Otto-Otto (Bronze scan), MCP server (read), OpenClaw (via MCP) |
| SQLite `otto_silver.db` | Otto-Otto (pipeline) | Otto-Otto, KAIROS, retrieval |
| ChromaDB `otto_gold` | Otto-Otto (pipeline Gold step) | Otto-Otto, VaultSignalTools, retrieval |
| Postgres `otto` DB | Otto-Otto (events + runtime) | KAIROS, retrieval, adminer UI |

---

## 9. OpenClaw Integration

OpenClaw is the **agent execution layer**. It connects to the vault via the `ob-otto-obsidian-mcp` container and reads Otto-Realm files for system design.

### OpenClaw's View of Otto

```
Otto-Otto (control plane)
  ├── Manages pipeline (Bronze → Silver → Gold)
  ├── Runs KAIROS + Dream loops (runtime_loop.py)
  ├── Manages Docker containers (postgres, chromadb, obsidian-mcp)
  ├── Syncs managed config sections to .openclaw/openclaw.json
  └── Warns on 529 status → falls back to HuggingFace Qwen/Qwen2.5-72B-Instruct

Otto-Realm (brain/persona) — OpenClaw reads this
  ├── Otto-Realm/GOVERNANCE.md     → system rules, container naming, DB roles
  ├── Otto-Realm/OTTO-DESIGN.md    → full architecture, DAGs, MCP tools
  ├── Otto-Realm/Brain/            → self_model.md (updated each dream cycle)
  ├── Otto-Realm/Predictions/      → YYYY-MM-DD_predictions.md (updated each kairos cycle)
  ├── Otto-Realm/Memory-Tiers/     → memory layer (3 tiers)
  └── Otto-Realm/Rituals/          → ritual cycle outputs

Josh Obsidian (vault) — OpenClaw accesses via obsidian-mcp
  ├── obsidian_read_note(path)    → read any MD note
  ├── obsidian_search_notes(query)→ full-text search
  └── obsidian_list_notes()       → list with optional tag/path filter
```

### OpenClaw Config Sync

Otto manages these sections in `.openclaw/openclaw.json`:
- `agents.defaults.cliBackends`
- `agents.defaults.models`
- `agents.defaults.heartbeat`
- `models.providers`

Sync runs via: `otto openclaw-sync` or `_action_sync_openclaw()` in launcher.

### MCP Server Startup

```
launcher → action: launch-mcp
  → docker exec -i ob-otto-obsidian-mcp node dist/index.js
  → OpenClaw stdin/stdout connect to MCP stdio transport
```

The `launch-mcp.bat` script is the shorthand. Otto uses `launcher.py` for integrated control.

### 529 Fallback Path

```
OpenClaw issues request → Claude Code returns 529
  → decide_openclaw_fallback(529) → emit EVENT_OPENCLAW_FALLBACK_TRIGGERED
  → write to state/openclaw/fallback_events.jsonl
  → fallback to models.providers.huggingface → Qwen/Qwen2.5-72B-Instruct
```

HF_TOKEN from `.env` used for HuggingFace API key substitution.

---

*Last updated: 2026-04-17*
*Author: Otto-Otto (via Sir Agathon governance session)*
*Memory: memory/kairos-telemetry-deep-dive.md — full KAIROS telemetry system docs*