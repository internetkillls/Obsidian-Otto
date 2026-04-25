# Architecture

## Goal

Split execution (MCP Fabric) from control plane (Obsidian-Otto). OpenClaw becomes the gateway and broker that orchestrates both sides. Build toward MCP-native execution while preserving Otto's curated state, pipeline, and retrieval core.

**Status:** MCP Fabric scaffolded — `config/docker.yaml` is the canonical enablement switch and currently sets Docker/MCP `enabled: true`; `obsidian-cli-mcp` remains deferred until a real external CLI backend is selected. Docker Desktop is still required for runtime verification.

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
        -> KAIROS telemetry / Dream / Otto-Realm heartbeat outputs
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
  training queue -> read mentor probes/tasks from launcher home screen
  resolve task   -> move one pending mentor task into done/skipped
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

Runtime start → logs → OpenClaw routing → MCP execution (or Otto state retrieval) → KAIROS telemetry → Dream consolidation → next batch strategy

### 3A. Mentor loop

Profile risk → probe note in `.Otto-Realm/Training/probes/` → answered probe classified into `theory_gap | application_gap | resolved` → bounded training task in `.Otto-Realm/Training/pending/` only for non-resolved gaps → human resolution through `done/` or `skipped/` → machine writeback to `state/kairos/mentor_latest.json`

Current mentoring rules:

- `continuity_prompts` is the canonical self-model naming; legacy `SM-2` surfaces are compatibility-only.
- Probe classification is deterministic and derived from probe content, not Gold/vault hygiene scores.
- The launcher exposes the queue, but probe answers still live in Obsidian notes.

Current OpenClaw boundary rule:

- MORPHEUS output is not a durable memory write by default.
- Otto must bridge MORPHEUS into `investigative-memory-candidate` state first.
- OpenClaw dreaming or promotion may only consume reviewed or verified candidates.
- Raw dreaming artifacts and session corpus remain generated evidence lanes, not canonical memory lanes.

### 4. MCP migration loop

MCP infra not yet live → Otto holds execution temporarily → temporary bridge flagged as migration candidate → when MCP live, move execution to MCP → audit routing/policy thickness

### 5. A→B→C→A loop contract

Obsidian-Otto should treat the Otto-Realm integration as a three-role loop with return continuity:

- **A** = Cowork intake or operator-facing upstream signal
- **B** = Obsidian-Otto control plane: retrieve, classify, normalize, and decide
- **C** = Canonical Otto-Realm writeback or durable vault-side output

Contract rules:

- A can enter as a task, note, or prompt fragment.
- B must not assume raw vault context unless scoped verification requires it.
- C is the only place where durable vault-side artifacts are committed.
- After C writes complete, the next A pass should consume the freshest structured handoff rather than re-open broad raw context.
- The bridge write path should be explicit and append-only:
  - `state/handoff/from_cowork/<YYYYMMDDTHHmm>_<role>_<status>.json`

This keeps the control plane separated from the canonical vault while still allowing a documented bridge for scheduled or operator-driven flows.

## Supporting docs

- `docs/architecture.md` — this file — current architecture
- `docs/OPENCLAW_OTTO_BRIDGE.md` — current OpenClaw bridge contract, runtime status, and latest constraints
- `docs/superpowers/specs/2026-04-13-otto-mcp-native-architecture-design.md` — source of truth for MCP-native design
- `docs/superpowers/plans/2026-04-25-mentor-feedback-loop-phase1-checkpoint.md` — checkpoint for the closed-loop mentoring rebuild
- `docs/migration-plan.md` — migration stages to MCP-native
- `docs/state-model.md` — what checkpoints are, which state files are official
- `Otto-Realm/README.md` — in-repo sample mirror and canonical pointer
- `docs/cache-stack-and-events.md` — Bronze/Silver/Gold data flow
- `docs/model-routing.md` — control policy, not architecture
- `docs/routing-audit.md` — routing complexity audit (pre-MCP baseline)
- `docs/cli-mcp-deferred.md` — why obsidian-cli-mcp is deferred
- `config/routing.yaml` — routing intent registry
- `config/personas.yaml` — persona inference fields
- `config/kernelization.yaml` — kernelization schema
- `config/docker.yaml` — Docker/MCP configuration (enabled: true; CLI backend still deferred)
- `config/migration-bridges.yaml` — temporary bridge inventory
