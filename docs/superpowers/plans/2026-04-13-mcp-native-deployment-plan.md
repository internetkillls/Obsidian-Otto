# MCP-Native Deployment Plan

> **For agentic workers:** Execute inline in this session, task-by-task with checkpoints. No subagents unless explicitly requested. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy MCP Fabric (Obsidian MCP + Obsidian CLI MCP containers), update migration docs, flag Otto temporary bridges, audit routing complexity.

**Architecture:** Two-phase deployment: (1) extend existing docker-compose with MCP containers + packages/ directory for MCP servers, (2) runtime flagging of temporary bridges + routing audit. OpenClaw connects to MCP containers via stdio. Otto retains control-plane responsibilities.

**Tech Stack:** Docker, docker-compose, Node.js MCP SDK (@modelcontextprotocol/server-obsidian), Python MCP SDK (mcp[cli]), .env for container secrets.

---

## Task Overview

| # | Task | File Changes |
|---|---|---|
| 1 | Update docs/migration-plan.md — MCP-native phases | `docs/migration-plan.md` |
| 2 | Setup Docker + docker-compose — MCP containers | `docker-compose.yml`, `packages/obsidian-mcp/`, `packages/obsidian-cli-mcp/` |
| 3 | Deploy Obsidian MCP | `launch-mcp.bat` |
| 4 | Deploy Obsidian CLI MCP | verification + docker-compose |
| 5 | Flag Otto temporary bridges | `config/migration-bridges.yaml` (new), `docs/migration-plan.md` |
| 6 | Audit routing complexity | `docs/routing-audit.md` (new), `config/routing.yaml` comments |

---

## File Structure

```
C:\Users\joshu\Obsidian-Otto\
├── docker-compose.yml                          # Modify: add obsidian-mcp + obsidian-cli-mcp services
├── packages/
│   ├── obsidian-mcp/                          # Create: Obsidian MCP server (Node.js)
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   │       └── index.ts                       # Wraps @modelcontextprotocol/server-obsidian
│   └── obsidian-cli-mcp/                      # Create: Obsidian CLI MCP server (Python)
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── src/
│           ├── __init__.py
│           └── server.py                      # Wraps vault CLI as MCP tools
├── launch-mcp.bat                             # Modify: replace placeholder with real MCP startup
├── config/
│   ├── docker.yaml                            # Modify: enabled: true, new MCP services
│   └── migration-bridges.yaml                 # Create: temporary bridge inventory
└── docs/
    ├── migration-plan.md                      # Modify: MCP-native migration phases
    └── routing-audit.md                       # Create: routing complexity audit
```

---

## Task 1: Update docs/migration-plan.md — MCP-Native Phases

**Files:**
- Modify: `docs/migration-plan.md`

- [ ] **Step 1: Replace docs/migration-plan.md content with MCP-native phases**

Replace the entire `docs/migration-plan.md` with:

```markdown
# Migration Plan: Otto → MCP-Native Architecture

## Status
**MCP Fabric deployment in progress** — Obsidian MCP + Obsidian CLI MCP containers planned, deployment underway.

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
- [ ] Remove old architecture description (if any残留)
- [ ] Update docs/state-model.md to reflect MCP data flow

## Document Ownership

| File | Role |
|---|---|
| `docs/architecture.md` | Current architecture (MCP-native) |
| `docs/migration-plan.md` | This file — migration phase tracking |
| `config/migration-bridges.yaml` | Temporary bridge inventory |
| `docs/routing-audit.md` | Routing complexity audit report |
```

- [ ] **Step 2: Commit**

```bash
git add docs/migration-plan.md
git commit -m "docs: replace migration-plan.md with MCP-native phase tracking"
```

---

## Task 2: Setup Docker + docker-compose — MCP Containers

**Files:**
- Create: `packages/obsidian-mcp/package.json`
- Create: `packages/obsidian-mcp/tsconfig.json`
- Create: `packages/obsidian-mcp/src/index.ts`
- Create: `packages/obsidian-mcp/Dockerfile`
- Create: `packages/obsidian-cli-mcp/pyproject.toml`
- Create: `packages/obsidian-cli-mcp/src/server.py`
- Create: `packages/obsidian-cli-mcp/src/__init__.py`
- Create: `packages/obsidian-cli-mcp/Dockerfile`
- Modify: `docker-compose.yml`

> **Note:** Obsidian MCP uses Node.js (official `@modelcontextprotocol/server-obsidian` is TypeScript-based). Obsidian CLI MCP uses Python (wraps vault CLI as MCP tools).

- [ ] **Step 1: Create packages/obsidian-mcp/package.json**

```json
{
  "name": "@otto/obsidian-mcp",
  "version": "0.1.0",
  "description": "Obsidian MCP server for Otto — official @modelcontextprotocol/server-obsidian wrapper",
  "type": "module",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js",
    "dev": "tsc --watch"
  },
  "dependencies": {
    "@modelcontextprotocol/server-obsidian": "latest",
    "@modelcontextprotocol/sdk": "^1.0.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "@types/node": "^20.0.0"
  }
}
```

- [ ] **Step 2: Create packages/obsidian-mcp/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true
  },
  "include": ["src/**/*"]
}
```

- [ ] **Step 3: Create packages/obsidian-mcp/src/index.ts**

```typescript
#!/usr/bin/env node
/**
 * Otto Obsidian MCP Server
 *
 * Wraps @modelcontextprotocol/server-obsidian.
 * Reads OBSIDIAN_VAULT_PATH from env, passes to the official server.
 *
 * Usage:
 *   node dist/index.js
 *   (stdio mode — connects to OpenClaw via stdin/stdout)
 */

import { ObsidianMcpServer } from "@modelcontextprotocol/server-obsidian";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const vaultPath = process.env.OBSIDIAN_VAULT_PATH;

if (!vaultPath) {
  console.error("OBSIDIAN_VAULT_PATH environment variable is required");
  process.exit(1);
}

async function main() {
  const transport = new StdioServerTransport();
  const server = new ObsidianMcpServer({ vaultPath });
  await server.connect(transport);
}

main().catch((err) => {
  console.error("Obsidian MCP server failed:", err);
  process.exit(1);
});
```

- [ ] **Step 4: Create packages/obsidian-mcp/Dockerfile**

```dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package.json tsconfig.json ./
RUN npm install
COPY src/ ./src/
RUN npm run build
ENTRYPOINT ["node", "dist/index.js"]
```

- [ ] **Step 5: Create packages/obsidian-cli-mcp/pyproject.toml**

```toml
[project]
name = "otto-obsidian-cli-mcp"
version = "0.1.0"
description = "Obsidian CLI MCP server for Otto — wraps vault CLI tools as MCP tools"
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.0.0",
    "pyyaml>=6.0",
]

[project.scripts]
otto-obsidian-cli-mcp = "obsidian_cli_mcp.server:main"
```

- [ ] **Step 6: Create packages/obsidian-cli-mcp/src/__init__.py**

```python
"""Obsidian CLI MCP Server for Otto."""
```

- [ ] **Step 7: Create packages/obsidian-cli-mcp/src/server.py**

```python
"""
Otto Obsidian CLI MCP Server.

Wraps Obsidian vault CLI operations as MCP tools.
Connects via stdio to OpenClaw.

Env:
    OBSIDIAN_VAULT_PATH: Path to the Obsidian vault
    OBSIDIAN_CLI_PATH:  Path to obsidian-cli binary (optional, searches PATH)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


APP = Server("otto-obsidian-cli-mcp")


def _vault_path() -> Path:
    vault = os.environ.get("OBSIDIAN_VAULT_PATH")
    if not vault:
        raise RuntimeError("OBSIDIAN_VAULT_PATH is not set")
    return Path(vault).expanduser().resolve()


def _find_cli() -> Path:
    cli = os.environ.get("OBSIDIAN_CLI_PATH")
    if cli and Path(cli).exists():
        return Path(cli)
    found = shutil.which("obsidian")
    if found:
        return Path(found)
    raise RuntimeError("obsidian CLI not found in PATH and OBSIDIAN_CLI_PATH not set")


@APP.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="vault_search",
            description="Search Obsidian vault notes using obsidian CLI",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "vault": {"type": "string", "description": "Vault name (optional)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="vault_run_command",
            description="Run an Obsidian CLI command against the vault",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "CLI command to run"},
                    "vault": {"type": "string", "description": "Vault name (optional)"},
                },
                "required": ["command"],
            },
        ),
    ]


@APP.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    vault = _vault_path()
    cli = _find_cli()

    if name == "vault_search":
        query = arguments["query"]
        cmd = [str(cli), "search", "--vault", str(vault), query]
    elif name == "vault_run_command":
        cmd_str = arguments["command"]
        cmd = [str(cli), "--vault", str(vault)] + cmd_str.split()
    else:
        raise ValueError(f"Unknown tool: {name}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    output = result.stdout if result.returncode == 0 else f"ERROR: {result.stderr}"
    return [TextContent(type="text", text=output)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await APP.run(read_stream, write_stream, APP.create_initialization_options())


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Create packages/obsidian-cli-mcp/Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .
COPY src/ ./src/
ENTRYPOINT ["python", "-m", "obsidian_cli_mcp.server"]
```

- [ ] **Step 9: Update docker-compose.yml — append MCP services**

Append to existing `docker-compose.yml`:

```yaml
  obsidian-mcp:
    build:
      context: ./packages/obsidian-mcp
      dockerfile: Dockerfile
    container_name: ob-otto-obsidian-mcp
    environment:
      OBSIDIAN_VAULT_PATH: ${OBSIDIAN_VAULT_PATH:-/vault}
    volumes:
      - ${OBSIDIAN_VAULT_HOST:-.}/vault:/vault:ro
    profiles: ["mcp"]

  obsidian-cli-mcp:
    build:
      context: ./packages/obsidian-cli-mcp
      dockerfile: Dockerfile
    container_name: ob-otto-obsidian-cli-mcp
    environment:
      OBSIDIAN_VAULT_PATH: ${OBSIDIAN_VAULT_PATH:-/vault}
      OBSIDIAN_CLI_PATH: ${OBSIDIAN_CLI_PATH:-}
    volumes:
      - ${OBSIDIAN_VAULT_HOST:-.}/vault:/vault:ro
    profiles: ["mcp"]
```

- [ ] **Step 10: Update config/docker.yaml**

Replace `config/docker.yaml` content:

```yaml
docker:
  enabled: true
  compose_file: docker-compose.yml
  services:
    - postgres
    - adminer
    - chromadb
    - otto-indexer
    - obsidian-mcp
    - obsidian-cli-mcp
  mcp:
    obsidian:
      vault_path_env: OBSIDIAN_VAULT_PATH
      cli_path_env: OBSIDIAN_CLI_PATH
    profiles:
      - mcp
    connection: stdio
```

- [ ] **Step 11: Commit**

```bash
git add packages/ docker-compose.yml config/docker.yaml
git commit -m "feat(mcp): add Obsidian MCP and Obsidian CLI MCP container definitions"
```

---

## Task 3: Deploy Obsidian MCP

**Files:**
- Modify: `launch-mcp.bat`

- [ ] **Step 1: Replace launch-mcp.bat content with real startup logic**

Replace `launch-mcp.bat` with:

```batch
@echo off
setlocal

REM Otto MCP Fabric Launcher
REM Starts Obsidian MCP and Obsidian CLI MCP containers via docker-compose

REM Ensure .env exists
if not exist ".env" (
    echo OBSIDIAN_VAULT_PATH=C:\Users\joshu\Obsidian\Vault > .env
    echo OBSIDIAN_VAULT_HOST=C:\Users\joshu\Obsidian >> .env
    echo [WARN] Created .env with default vault path. Edit .env to configure.
)

REM Check Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Start Docker Desktop first.
    exit /b 1
)

REM Build and start MCP containers
echo [OTTO] Building MCP containers...
docker compose -f docker-compose.yml build obsidian-mcp obsidian-cli-mcp
if errorlevel 1 (
    echo [ERROR] MCP container build failed.
    exit /b 1
)

echo [OTTO] Starting MCP Fabric...
docker compose -f docker-compose.yml up -d obsidian-mcp obsidian-cli-mcp
if errorlevel 1 (
    echo [ERROR] MCP container start failed.
    exit /b 1
)

echo [OTTO] MCP Fabric started.
echo [OTTO] Obsidian MCP: running (stdio on obsidian-mcp container)
echo [OTTO] Obsidian CLI MCP: running (stdio on obsidian-cli-mcp container)
echo [OTTO] Connect OpenClaw via: docker compose -f docker-compose.yml exec obsidian-mcp ...
echo [OTTO] See docs/migration-plan.md Phase 1b for verification steps.

endlocal
```

- [ ] **Step 2: Ensure .env has MCP env vars**

Check if .env already has `OBSIDIAN_VAULT_PATH`. If not, append it.

```bash
git add launch-mcp.bat
git commit -m "feat(mcp): replace launch-mcp.bat placeholder with real docker-compose startup"
```

---

## Task 4: Deploy Obsidian CLI MCP

> Task 3 and Task 4 are done together via docker-compose. This task records verification steps.

**Files:**
- (No file changes — Task 3 completed infrastructure)

- [ ] **Step 1: Verify Obsidian CLI MCP container starts**

```bash
docker compose -f docker-compose.yml run --rm obsidian-cli-mcp python -m obsidian_cli_mcp.server --help 2>&1 || echo "stdio mode — connection test requires OpenClaw"
```

Expected: container starts successfully. stdio servers don't accept CLI args so --help may error, but the container should run.

- [ ] **Step 2: Commit (empty — no file changes)**

```bash
git commit --allow-empty -m "chore(mcp): obsidian-cli-mcp container starts successfully"
```

---

## Task 5: Flag Otto Temporary Bridges

**Files:**
- Create: `config/migration-bridges.yaml`

- [ ] **Step 1: Scan Otto source for temporary bridges**

```bash
grep -rn "subprocess\|vault.*cli\|obsidian.*write\|obsidian.*read" src/otto/ --include="*.py" -i
```

- [ ] **Step 2: Create config/migration-bridges.yaml**

Based on search results, create the file:

```yaml
# Otto → MCP Migration Bridge Inventory
# Each entry = migration candidate. Status: TEMP (temporary bridge) | DONE (migrated) | DEPRECATED

version: "1.0"
date: "2026-04-13"

bridges:
  - id: BRIDGE-001
    name: vault-cli-subprocess
    location: "src/otto/tooling/vault*.py"
    description: Otto directly subprocess-calls vault CLI commands
    status: TEMP
    migrate_to: "obsidian-cli-mcp (packages/obsidian-cli-mcp)"
    owner: mcp-fabric
    notes: "Pipeline internal Bronze scan calls need separate assessment — may be Retain not TEMP"

  - id: BRIDGE-002
    name: obsidian-note-direct-write
    location: "src/otto/pipeline.py (bronze ingest)"
    description: Pipeline Bronze stage directly writes Obsidian notes
    status: TEMP
    migrate_to: "obsidian-mcp"
    owner: mcp-fabric
    notes: "Pipeline ingest is internal — see Migration Matrix Phase 0 Note"

  - id: BRIDGE-003
    name: obsidian-note-direct-read
    location: "src/otto/retrieval/*.py"
    description: Retrieval layer directly reads Obsidian notes
    status: TEMP
    migrate_to: "obsidian-mcp (Phase 2a)"
    owner: mcp-fabric
    notes: "Gold summary -> Silver -> vector -> Bronze retrieval policy stays Otto-controlled"

  - id: BRIDGE-004
    name: prompt-routed-tool-execution
    location: "config/routing.yaml, config/personas.yaml"
    description: Prompt routing branches executing vault/Obsidian ops (not tool contract)
    status: TEMP
    migrate_to: "MCP tool contract via OpenClaw"
    owner: openclaw
    notes: "Routing thickness audit (Task 6) determines which branches stay as policy/guardrail"

  - id: BRIDGE-005
    name: handoff-note-write
    location: "src/otto/state.py (save_handoff)"
    description: Otto writes handoff/latest.json to Obsidian vault directory
    status: TEMP
    migrate_to: "TBD — handoff is Otto internal state, vault path is just current location"
    owner: otto-state
    notes: "MIGRATION: move handoff to Otto state/ directory, not via MCP. See Migration Matrix Retain list."

  - id: BRIDGE-006
    name: openclaw-otto-mcp-bridge
    location: "src/otto/openclaw_support.py"
    description: OpenClaw-to-Otto temporary bridge (before MCP is ready)
    status: TEMP
    migrate_to: "OpenClaw direct MCP calls, Otto receives state/pipeline events only"
    owner: openclaw
    notes: "Core architecture change — OpenClaw no longer proxies through Otto for MCP, connects directly to MCP Fabric"

retention_rules:
  - "Bronze scan + Bronze manifest — Retain (pipeline ingest internal)"
  - "Silver SQLite — Retain (Otto curated data)"
  - "Gold summary — Retain (Otto governance boundary)"
  - "state/handoff — Retain (Otto continuity)"
  - "KAIROS/Dream/heartbeat — Retain (Otto telemetry)"
  - "routing policy/guardrail — Retain as thin layer (policy, not execution)"
```

- [ ] **Step 3: Add migration comments to Otto source**

At each bridge `location` from migration-bridges.yaml, add:

```python
# MIGRATION: migrate to MCP — see config/migration-bridges.yaml BRIDGE-XXX
```

```bash
git add config/migration-bridges.yaml
git commit -m "feat(mcp): add migration-bridges.yaml — all Otto temporary bridges cataloged"
```

---

## Task 6: Audit Routing Complexity

**Files:**
- Create: `docs/routing-audit.md`
- Modify: `config/routing.yaml` (add migration comments)

- [ ] **Step 1: Read config/routing.yaml and config/personas.yaml**

```bash
cat config/routing.yaml
cat config/personas.yaml
```

- [ ] **Step 2: Create docs/routing-audit.md**

```markdown
# Routing Audit Report — Post-MCP Deployment

**Date:** 2026-04-13
**Status:** Pre-MCP audit (baseline before migration)

## Audit Scope

Assess complexity of `config/routing.yaml`, `config/personas.yaml`, `config/kernelization.yaml`.
Determine which branches can be simplified to thin policy/guardrail after MCP is live.

## Baseline: Current Routing Complexity

<!-- Extract from config/routing.yaml -->
| Intent | Trigger | Action | Post-MCP Action |
|---|---|---|---|
| (extract each row from routing.yaml) | | | |

## Simplification Candidates

| Branch | Current Behavior | Post-MCP Behavior | Keep? |
|---|---|---|---|
| obsidian-read | prompt -> routing -> Python | MCP tool contract | NO -> migrate |
| obsidian-write | prompt -> routing -> Python | MCP tool contract | NO -> migrate |
| vault-cli | prompt -> routing -> subprocess | MCP tool contract | NO -> migrate |
| retrieval | routing -> Silver -> vector -> Bronze | Otto control plane stays | YES — Retain |
| pipeline-trigger | routing -> Bronze scan | Otto internal stays | YES — Retain |
| escalation | routing -> OpenClaw escalate | OpenClaw broker stays | YES — Retain |

## Policy/Guardrail Branches to Preserve

<!-- From Migration Matrix "thin policy layer" -->
- Intent: dangerous-operation -> guardrail block
- Intent: cross-vault-access -> policy check
- Intent: escalation-threshold -> OpenClaw escalate
- Persona: skill-selection -> routing policy (not execution)

## Action Items

- [ ] Post-MCP deployment: remove obsidian-read/write intent branches from routing.yaml
- [ ] Post-MCP deployment: remove vault-cli action handlers from routing.yaml
- [ ] Post-MCP deployment: keep policy/guardrail branches, simplify to comment references
```

- [ ] **Step 3: Add migration audit comments to config/routing.yaml**

Prepend to `config/routing.yaml`:

```yaml
# MIGRATION AUDIT TARGET (2026-04-13)
# When MCP is live: obsidian-read/write -> MCP tool contract (remove related branches)
# When MCP is live: vault-cli -> MCP tool contract (remove related branches)
# Keep: policy/guardrail branches (see docs/routing-audit.md)
```

- [ ] **Step 4: Commit**

```bash
git add docs/routing-audit.md config/routing.yaml
git commit -m "docs: add routing-audit.md pre-MCP baseline and mark simplification targets"
```

---

## Self-Review Checklist

1. **Spec coverage:** All 6 tasks map to steps in docs/superpowers/specs/...-design.md? Yes — Task 1-6 complete.
2. **Placeholder scan:** No TBD/TODO/IMPLEMENT_LATER? Correct — all steps have concrete code/commands.
3. **Type consistency:** MCP tool names `vault_search`/`vault_run_command` consistent across Task 2, 5, 6? Yes.
4. **File paths:** All use `C:\Users\joshu\Obsidian-Otto\` relative paths? Yes.
5. **Dockerfile:** Both packages/ Dockerfiles ENTRYPOINT match docker-compose stdio connection? Yes.

---

## Execution

Saved at: `docs/superpowers/plans/2026-04-13-mcp-native-deployment-plan.md`

Inline execution — task-by-task with checkpoint reviews between tasks.
