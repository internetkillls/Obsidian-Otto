# State Model

## Why state is external

Codex should not rely on chat memory alone.
This repo externalizes continuity to files so sessions can resume cleanly.

## Core state files

### Otto control plane state

| File | Role |
|---|---|
| `state/handoff/latest.json` | Continuity packet — current session goal, next actions, artifacts |
| `state/checkpoints/pipeline.json` | Bronze/Silver pipeline snapshot (note count, gold folders, training readiness) |
| `state/run_journal/events.jsonl` | Append-only audit trail of all significant runtime events |
| `state/kairos/heartbeat.jsonl` | Periodic telemetry samples (freshness, misses, risk changes) |
| `state/dream/dream_state.json` | Consolidation state (resolved facts, open blockers) |

### Launcher state

| File | Role |
|---|---|
| `state/launcher/current.json` | Live operator snapshot: runtime status, vault path, MCP config, recommended actions |
| `state/launcher/last_action.json` | Last operator action: name, screen, exit code, duration ms |
| `state/launcher/mcp_last_run.json` | Last MCP launch: mode (stdio_run/build_only), vault paths, exit codes, notes |

### Runtime process state

| File | Role |
|---|---|
| `state/pids/runtime.pid` | Background runtime PID (checked for staleness on startup) |
| `state/bootstrap/latest.json` | Bootstrap result snapshot |
| `state/openclaw/sync_status.json` | OpenClaw config sync status |
| `state/openclaw/fallback_events.jsonl` | OpenClaw provider fallback events |

### Artifact state

| File | Role |
|---|---|
| `artifacts/summaries/gold_summary.json` | Gold curation bundle (folder risk, training readiness, next actions) |
| `artifacts/reports/kairos_daily_strategy.md` | KAIROS daily strategy output |
| `artifacts/reports/dream_summary.md` | Dream consolidation output |
| `data/bronze/bronze_manifest.json` | Bronze scan manifest (raw inventory) |

## Continuity rules

1. Handoff is Otto's external memory — check it before asking questions.
2. Checkpoints freeze pipeline state — they are the authoritative record of what was scanned.
3. Run journal is append-only — never truncate it.
4. Launcher state is ephemeral for display — it is not the source of truth for anything else.
5. Artifact summaries are curated — only reviewed Gold goes to training export.
