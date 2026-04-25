# State Model

## Why state is external

Codex should not rely on chat memory alone.
This repo externalizes continuity to files so sessions can resume cleanly.

## Core state files

### Otto control plane state

| File | Role |
|---|---|
| `state/handoff/latest.json` | Continuity packet — current session goal, next actions, artifacts |
| `state/handoff/from_cowork/` | Append-only bridge drops from Cowork into Otto control plane |
| `state/checkpoints/pipeline.json` | Bronze/Silver pipeline snapshot (note count, gold folders, training readiness) |
| `state/run_journal/events.jsonl` | Append-only audit trail of all significant runtime events |
| `state/kairos/heartbeat.jsonl` | Legacy-named KAIROS telemetry samples (freshness, misses, risk changes) |
| `state/kairos/mentor_latest.json` | Mentor loop snapshot: active probes, pending tasks, weakness registry, resolution history |
| `state/dream/dream_state.json` | Consolidation state (resolved facts, open blockers) |

### Interface contracts

| File | Role |
|---|---|
| `docs/interfaces/realtime-context-and-cron-report.md` | Contract for `context_pack_v1` and `cron_report_v1` payloads used in realtime and cron flows |

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

## Bridge drop minimum schema

Bridge drops under `state/handoff/from_cowork/` should stay small, structured, and append-only. Canonical shape:

```json
{
  "source": "cowork-otto-a",
  "role": "a",
  "status": "handoff",
  "updated_at": "2026-04-17T15:30:00+07:00",
  "summary": "Short high-signal cycle summary",
  "artifacts": ["Otto-Realm/Handoff/a_signal.md"],
  "next_actions": [
    "Investigate candidate 1",
    "Preserve OO product direction"
  ],
  "next_action": "Investigate candidate 1",
  "wellbeing": {
    "josh_state": "flow",
    "evidence": "Recent heartbeat plus active commit window"
  },
  "language": "id"
}
```

Compatibility rules:

- Treat `updated_at` as canonical. If an older consumer still expects `ts`, mirror `updated_at` into `ts` at the boundary adapter, not in the producer contract.
- Treat `next_actions` as canonical. If an older consumer still expects `next_action`, read the first item from `next_actions`.
- `role` should be `a`, `b`, or `c` for the Cowork loop. Other producers may use their own role values only if their consumer explicitly supports them.
- `status` should use the loop exit contract: `no_action`, `intervention_card`, `handoff`, or `escalation`.

## Continuity rules

1. Handoff is Otto's external memory — check it before asking questions.
2. Checkpoints freeze pipeline state — they are the authoritative record of what was scanned.
3. Run journal is append-only — never truncate it.
4. Launcher state is ephemeral for display — it is not the source of truth for anything else.
5. Artifact summaries are curated — only reviewed Gold goes to training export.
6. Bridge drops under `state/handoff/from_cowork/` should use the documented append-only naming pattern and stay separate from `latest.json`.
7. Mentor state is the canonical machine view of the developmental loop; human queue files remain under `.Otto-Realm/Training/`.
8. `continuity_prompts` is the canonical self-model field; `sm2_hooks` survives only as a read-compat alias.
