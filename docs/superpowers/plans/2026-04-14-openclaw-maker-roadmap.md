# OpenClaw Maker Roadmap for Obsidian-Otto

## Goal

Adopt `Workflow Maker -> Skill Maker -> Automation Maker -> Auto-improvement` into Obsidian-Otto without turning Otto into ad hoc prompt glue.

The target shape is:

- OpenClaw remains the gateway, automation substrate, and skill runtime.
- Docker MCP remains the execution fabric for external capabilities.
- Obsidian-Otto remains the control plane for curated state, retrieval order, delta measurement, and approval-aware transduction.

## Current reality

Current repo state is strong on control-plane continuity, but not yet ready for scalable capability adoption:

- `docs/architecture.md` already splits execution plane vs control plane.
- `src/otto/openclaw_support.py` only syncs OpenClaw config and fallback state; it does not manage skill/workflow/automation lifecycle.
- `src/otto/app/launcher.py` has no `pull`, `push`, `update`, or kernel-refresh actions.
- `src/otto/launcher_state.py` tracks runtime and MCP state only; it does not track capability rollout state.
- `src/otto/runtime.py` runs only `kairos` and `dream`; there is no adoption-review loop.

This means Otto can observe and summarize, but cannot yet safely decide:

1. where a new capability belongs,
2. what substrate it should run on,
3. what script or server is still missing,
4. whether activation should be blocked.

## External docs to anchor the design

### OpenClaw

- Skills are folder-based and centered on `SKILL.md`, with metadata gates and loader precedence.
  - Source: <https://docs.openclaw.ai/tools/creating-skills>
  - Source: <https://docs.openclaw.ai/tools/skills>
- ClawHub is the public skill registry; `openclaw skills install/update` and `clawhub sync` are the native distribution paths.
  - Source: <https://docs.openclaw.ai/tools/skills>
- Heartbeat is a main-session periodic turn, not a detached task ledger.
  - Source: <https://docs.openclaw.ai/gateway/heartbeat>
- `HEARTBEAT.md` supports a small `tasks:` block for due-only periodic checks inside heartbeat.
  - Source: <https://docs.openclaw.ai/gateway/heartbeat>
- Cron is for exact timing and creates background task records.
  - Source: <https://docs.openclaw.ai/automation/cron-jobs>
- Background Tasks are records, not schedulers.
  - Source: <https://docs.openclaw.ai/automation/tasks>
- Task Flow is the durable orchestration layer for multi-step flows.
  - Source: <https://docs.openclaw.ai/automation/index>
- Webhooks can create and drive managed TaskFlows from trusted external systems.
  - Source: <https://docs.openclaw.ai/plugins/webhooks>
- Standing orders belong in bootstrap files such as `AGENTS.md`, not arbitrary subfiles.
  - Source: <https://docs.openclaw.ai/es/automation/standing-orders>

### MCP and Docker

- MCP officially supports `stdio` for local deployments and Streamable HTTP for remote deployments.
  - Source: <https://modelcontextprotocol.io/specification/2025-11-25/basic/transports>
- Docker MCP Gateway provides centralized lifecycle, auth, routing, and container isolation for MCP servers.
  - Source: <https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/>
- Docker MCP Toolkit organizes servers into profiles and can add servers dynamically.
  - Source: <https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/>
  - Source: <https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/>

### OpenHub

- OpenHub is most useful here as a schema and governance reference, not as an immediate runtime dependency.
- The valuable patterns are: capability listings, interface contracts, policy labels, metering, routing, and reputation.
  - Source: <https://resources.openhub.ai/>

## Decision rule for new capabilities

Every proposed capability should be forced through one placement decision:

### 1. OpenClaw Skill

Use when the capability is mainly:

- promptable behavior,
- tool selection guidance,
- lightweight execution policy,
- local to agent context.

### 2. OpenClaw Heartbeat task

Use when the capability is:

- periodic,
- lightweight,
- due-only,
- main-session aware,
- acceptable without task ledger history.

### 3. OpenClaw Cron job

Use when the capability needs:

- exact timing,
- isolated execution,
- task records,
- delivery or retry behavior.

### 4. OpenClaw TaskFlow

Use when the capability is:

- multi-step,
- durable,
- revision-aware,
- resumable,
- possibly driven by webhook or ACP/subagent child tasks.

### 5. MCP server via Docker

Use when the capability is:

- an external system/tool boundary,
- reusable across agents,
- better isolated from Otto internals,
- deserving a typed tool contract rather than prompt glue.

### 6. Otto transducer/control plane

Use when the capability is about:

- curated retrieval,
- delta scoring,
- placement decisions,
- policy checks,
- handoff/checkpoint/report generation,
- approval-aware governance.

## The missing layer: capability adoption transducer

Otto needs one new transducer layer before we build any maker UI:

`proposed capability -> inspect -> classify -> delta packet -> placement -> implementation queue -> verification -> activation`

This layer should output a structured adoption packet, not free text.

## Proposed base artifact

Add one new internal artifact family:

- `state/capability_adoption/*.json`

Each packet should contain:

```json
{
  "capability_id": "skill-maker.github-review-v1",
  "source": "maker_request | clawhub_install | repo_change | manual",
  "kind": "skill | workflow | automation | mcp | launcher-update",
  "placement": "openclaw-skill | heartbeat | cron | taskflow | mcp | otto-control",
  "delta_targets": [
    "workspace skill folder",
    "openclaw.json",
    "HEARTBEAT.md",
    "cron jobs",
    "docker profile",
    "launcher actions",
    "python script"
  ],
  "missing_primitives": [
    "script: scripts/manage/review_capability.py",
    "state file: state/capability_adoption/latest.json"
  ],
  "activation_gate": "blocked | ready | partial",
  "verification_plan": [
    "load check",
    "dry run",
    "task record check",
    "handoff update"
  ]
}
```

## The first automation to build

Build one automation only:

`Capability Adoption Review`

It should run whenever:

- a new skill is added or changed under `.agents/skills/` or workspace `skills/`,
- a maker request proposes a new capability,
- a ClawHub install/update occurs,
- a launcher or MCP profile changes.

It should answer five questions only:

1. What kind of capability is this?
2. Where should it live?
3. What script/server/config is still missing?
4. Is activation safe now?
5. What is the next smallest runnable wedge?

If this exists, Otto stops guessing and starts producing bounded rollout packets.

## Heartbeat strategy

Do not overload heartbeat with orchestration.

Heartbeat should only do:

- lightweight due checks,
- urgent surfacing,
- minimal session-aware reminders,
- escalation into cron or TaskFlow when real work begins.

Use `HEARTBEAT.md` `tasks:` blocks only for:

- inbox triage,
- upcoming calendar checks,
- capability adoption reminders such as "review unactivated packets every 4h".

Do not use heartbeat for:

- heavy multi-step workflow execution,
- deployment actions,
- repo mutation,
- MCP provisioning.

## Launcher gap that must be closed first

The launcher currently lacks a system update lane. Before automation maker is credible, add explicit non-destructive update actions:

### Required launcher actions

- `pull-system` — fetch/pull repo updates
- `pull-kernel` — refresh routing/kernelization/skill policy bundle
- `push-system` — optional guarded push for approved local changes
- `refresh-skills` — refresh skill snapshot and validate loadability
- `refresh-mcp-profile` — verify Docker MCP profile/gateway readiness
- `review-adoption` — inspect latest capability adoption packets

### Required launcher state additions

Extend `state/launcher/current.json` and `last_action.json` with:

- `git_branch`
- `git_dirty`
- `last_pull_at`
- `last_kernel_pull_at`
- `skill_snapshot_status`
- `mcp_profile_status`
- `capability_review_status`

Without this, the maker stack can author capabilities but not reliably operationalize them.

## Suggested phase order

### Phase 0

Close the launcher and state gap.

- add update/pull actions
- add capability review action
- add capability adoption state files

### Phase 1

Build the transducer, not the UI.

- ingest proposed capability
- classify placement
- produce adoption packet
- block unsafe activation

### Phase 2

Build Skill Maker.

- scaffold OpenClaw-compatible `SKILL.md`
- compute metadata gates
- propose required bins/env/config
- decide workspace vs shared vs managed install path

### Phase 3

Build Automation Maker.

- choose heartbeat vs cron vs taskflow vs webhook
- generate the smallest valid config or script
- register verification checks

### Phase 4

Build Workflow Maker.

- compose multiple approved capabilities into TaskFlow-backed workflows
- use webhook or ACP child runtimes only when needed

### Phase 5

Build Auto-improvement.

- read `state/run_journal/events.jsonl`
- detect recurring friction
- propose refinements to skills, launcher actions, or automation placement
- never auto-rewrite constitutional policy without review

## Repo files most relevant to the next implementation pass

- [docs/architecture.md](/C:/Users/joshu/Obsidian-Otto/docs/architecture.md)
- [docs/launcher.md](/C:/Users/joshu/Obsidian-Otto/docs/launcher.md)
- [docs/cli-mcp-deferred.md](/C:/Users/joshu/Obsidian-Otto/docs/cli-mcp-deferred.md)
- [docs/superpowers/specs/2026-04-13-otto-mcp-native-architecture-design.md](/C:/Users/joshu/Obsidian-Otto/docs/superpowers/specs/2026-04-13-otto-mcp-native-architecture-design.md)
- [config/routing.yaml](/C:/Users/joshu/Obsidian-Otto/config/routing.yaml)
- [config/kernelization.yaml](/C:/Users/joshu/Obsidian-Otto/config/kernelization.yaml)
- [src/otto/app/launcher.py](/C:/Users/joshu/Obsidian-Otto/src/otto/app/launcher.py)
- [src/otto/launcher_state.py](/C:/Users/joshu/Obsidian-Otto/src/otto/launcher_state.py)
- [src/otto/openclaw_support.py](/C:/Users/joshu/Obsidian-Otto/src/otto/openclaw_support.py)
- [src/otto/runtime.py](/C:/Users/joshu/Obsidian-Otto/src/otto/runtime.py)
- [src/otto/orchestration/kairos.py](/C:/Users/joshu/Obsidian-Otto/src/otto/orchestration/kairos.py)
- [src/otto/events.py](/C:/Users/joshu/Obsidian-Otto/src/otto/events.py)

## Recommended immediate next move

Implement Phase 0 only:

- extend launcher actions,
- add capability adoption state schema,
- add one `review-adoption` script,
- wire one lightweight reminder into heartbeat,
- stop there and verify the loop.
