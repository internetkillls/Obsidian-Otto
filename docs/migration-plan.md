# Migration Plan: Otto → MCP-Native Architecture

## Status
**MCP Fabric deployment planned** — Obsidian MCP + Obsidian CLI MCP containers defined, build/deploy pending Docker Desktop. See Phase 1a checklist.

## Phase 0: Pre-MCP (complete)

| Item | Before | After |
|---|---|---|
| Obsidian read/write (interactive) | Otto direct calls (Python) | Migrate to MCP when live |
| Vault CLI | Otto subprocess calls | Migrate to CLI MCP when live |
| Prompt-routed tool behavior | routing.yaml prompt branches | Migrate to MCP tool contract |

> **Note:** Bronze scan + Bronze manifest and Silver ingest are internal pipeline operations — they are **Retain**. Interactive user-facing reads/writes are **Temporary** and migrate to MCP.

## Phase 1: MCP Fabric Deployment (current)

### 1a. Docker Infrastructure
- [ ] docker-compose.yml extended — obsidian-mcp + obsidian-cli-mcp services
- [ ] packages/obsidian-mcp/ built
- [ ] packages/obsidian-cli-mcp/ built
- [ ] config/docker.yaml updated — `enabled: true`
- [ ] .env added MCP env vars (OBSIDIAN_VAULT_PATH etc.)
- [ ] launch-mcp.bat replaced placeholder with real startup logic

### 1b. MCP Server Verification
- [ ] Obsidian MCP container starts and responds to stdio ping
- [ ] Obsidian CLI MCP container starts and responds to stdio ping
- [ ] OpenClaw connects to both MCP servers successfully

### 1c. Migration Bridge Flagging
- [ ] config/migration-bridges.yaml created — lists all temporary bridges
- [ ] Otto source code temporary bridge locations annotated with `// MIGRATION:` comments
- [ ] docs/migration-plan.md references migration-bridges.yaml

## Phase 2: Traffic Migration

### 2a. User-Facing Read/Write Migration
- [ ] OpenClaw configured for Obsidian MCP routing — note read/write requests → Obsidian MCP
- [ ] Verify user note read/write goes through MCP path
- [ ] Otto pipeline Bronze scan still uses internal path (non-user-facing, unchanged)

### 2b. Vault CLI Migration
- [ ] OpenClaw configured for Obsidian CLI MCP routing — vault commands → Obsidian CLI MCP
- [ ] Otto subprocess vault command calls → replaced with MCP calls
- [ ] Remove subprocess vault calls from Otto

## Phase 3: Cleanup and Audit

### 3a. Routing Complexity Audit
- [ ] Compare routing.yaml complexity pre/post MCP deployment
- [ ] Identify prompt routing branches simplifiable via MCP tool contract
- [ ] Identify branches to retain as policy/guardrail
- [ ] Document audit results → docs/routing-audit.md

### 3b. Temporary Bridge Cleanup
- [ ] Check each item in config/migration-bridges.yaml
- [ ] One git commit per bridge cleanup
- [ ] When all bridges cleaned → migration-bridges.yaml marked DONE

### 3c. Documentation Updates
- [ ] docs/architecture.md confirms MCP-native architecture as current state
- [ ] Remove old architecture description (if any)
- [ ] Update docs/state-model.md to reflect MCP data flow

## Document Ownership

| File | Role |
|---|---|
| `docs/architecture.md` | Current architecture (MCP-native) |
| `docs/migration-plan.md` | This file — migration phase tracking |
| `config/migration-bridges.yaml` | Temporary bridge inventory |
| `docs/routing-audit.md` | Routing complexity audit report |
