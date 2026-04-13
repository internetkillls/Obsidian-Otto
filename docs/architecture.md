# Architecture

## Goal

Split execution (MCP Fabric) from control plane (Obsidian-Otto). OpenClaw becomes the gateway and broker that orchestrates both sides. Build toward MCP-native execution while preserving Otto's curated state, pipeline, and retrieval core.

**Status:** MCP Fabric planned — containers defined but not yet deployed. Docker Desktop required to proceed.

See `docs/superpowers/specs/2026-04-13-otto-mcp-native-architecture-design.md` for the full approved design.

## High-level shape

```text
User / Telegram / TUI
  -> OpenClaw gateway / broker
     -> MCP Fabric (Docker)
        -> Obsidian MCP
        -> Obsidian CLI MCP
        -> [MCP lain bila perlu]
     -> Obsidian-Otto
        -> Bronze / Silver / Gold
        -> checkpoint / handoff / run_journal
        -> KAIROS / Dream / heartbeat
        -> artifacts / reports
```

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

- `docs/superpowers/specs/2026-04-13-otto-mcp-native-architecture-design.md` — source of truth for architecture
- `docs/migration-plan.md` — migration stages to MCP-native
- `docs/state-model.md` — what checkpoints are, which state files are official
- `docs/cache-stack-and-events.md` — Bronze/Silver/Gold data flow (not architecture)
- `docs/model-routing.md` — control policy, not architecture
- `config/routing.yaml` — routing intent registry
- `config/personas.yaml` — persona inference fields
- `config/kernelization.yaml` — kernelization schema