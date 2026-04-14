# Architecture

## Goal

Split execution (MCP Fabric) from control plane (Obsidian-Otto). OpenClaw becomes the gateway and broker that orchestrates both sides. Build toward MCP-native execution while preserving Otto's curated state, pipeline, and retrieval core.

**Status:** MCP Fabric scaffolded — `obsidian-mcp` (read-only) defined; `obsidian-cli-mcp` deferred until real external CLI backend selected. Docker Desktop required for runtime verification.

See `docs/superpowers/specs/2026-04-13-otto-mcp-native-architecture-design.md` for the full approved design.

## High-level shape

```
User / Telegram / TUI
  -> OpenClaw gateway / broker
     -> MCP Fabric (Docker)
        -> obsidian-mcp (read-only, active)
        -> obsidian-cli-mcp (deferred — awaiting real CLI backend)
        -> [future MCP servers as needed]
     -> Obsidian-Otto
        -> Bronze / Silver / Gold
        -> checkpoint / handoff / run_journal
        -> KAIROS / Dream / heartbeat
        -> artifacts / reports
```

## Operator Launcher

Otto exposes a unified operator launcher at `main.bat`:

```
main.bat          -> interactive home/advanced menu (Python launcher)
  start.bat      -> background runtime loop
  stop.bat       -> stop runtime
  status.bat     -> JSON status report
  doctor.bat     -> health + sanity checks
  tui.bat        -> live monitoring TUI
  reindex.bat    -> pipeline (full or scoped)
  query.bat      -> memory query
  kairos.bat     -> KAIROS telemetry (one-shot)
  dream.bat      -> Dream consolidation (one-shot)
  sync-openclaw.bat -> OpenClaw config sync
  brain.bat      -> Otto Brain CLI
  launch-mcp.bat -> MCP Fabric launch (stdio, obsidian-mcp only)
  docker-up.bat  -> bring up Docker stack
  docker-clean.bat -> clean Docker stack
```

All BAT files are thin shims: they only resolve venv, then delegate to `scripts/manage/run_launcher.py`. All operator logic lives in Python.

Runtime state is externalized to `state/launcher/`:
- `current.json` — live snapshot (runtime status, MCP config, vault path, recommended actions)
- `last_action.json` — last operator action with duration and exit code
- `mcp_last_run.json` — last MCP launch attempt with exit codes and notes

## Plane ownership

| Plane | Owner | Role |
|---|---|---|
| Execution | MCP Fabric (Docker) | Tool execution, capability access, Obsidian operations |
| Gateway/Broker | OpenClaw | Request routing, model selection, MCP orchestration, auth |
| Control + Curated Data | Obsidian-Otto | State continuity, pipeline, retrieval curation, telemetry, governance |

## Core loops

### 1. Retrieval loop

User query → OpenClaw → Gold summary (fast) → Silver SQLite → optional vector → raw Bronze only if evidence still insufficient

### 2. Dataset loop

Raw vault → Bronze scan → Silver normalization → Gold curation → training export candidate (Gold reviewed only)

### 3. Operational loop

Runtime start → logs → OpenClaw routing → MCP execution (or Otto state retrieval) → KAIROS heartbeat → Dream consolidation → next batch strategy

### 4. MCP migration loop

MCP infra not yet live → Otto holds execution temporarily → temporary bridge flagged as migration candidate → when MCP live, move execution to MCP → audit routing/policy thickness

## Supporting docs

- `docs/architecture.md` — this file — current architecture
- `docs/superpowers/specs/2026-04-13-otto-mcp-native-architecture-design.md` — source of truth for MCP-native design
- `docs/migration-plan.md` — migration stages to MCP-native
- `docs/state-model.md` — what checkpoints are, which state files are official
- `docs/cache-stack-and-events.md` — Bronze/Silver/Gold data flow
- `docs/model-routing.md` — control policy, not architecture
- `docs/routing-audit.md` — routing complexity audit (pre-MCP baseline)
- `docs/cli-mcp-deferred.md` — why obsidian-cli-mcp is deferred
- `config/routing.yaml` — routing intent registry
- `config/personas.yaml` — persona inference fields
- `config/kernelization.yaml` — kernelization schema
- `config/docker.yaml` — Docker/MCP configuration (enabled: false until runtime verified)
- `config/migration-bridges.yaml` — temporary bridge inventory
