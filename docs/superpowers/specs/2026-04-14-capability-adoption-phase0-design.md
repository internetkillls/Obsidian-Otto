# Capability Adoption Phase 0 — Design

## Goal

Build the capability adoption transducer foundation for Obsidian-Otto.
Phase 0 adds observability lanes and structured adoption packets.
No auto-injection into live OpenClaw. No activation without human verification.

## Positioning

```
Obsidian-Otto repo = control plane + canonical spec + curated state
OpenClaw           = gateway / runtime / orchestrator
MCP/Docker          = execution fabric
```

Repo memberi OpenClaw hal yang sudah dipilih, bukan seluruh vault. Koneksi lewat empat kontrak eksplisit:

| Kontrak | Arah | Contoh |
|---|---|---|
| `config` | repo → OpenClaw | openclaw.json sync |
| `skill` | repo → OpenClaw | skill snapshot artifact |
| `operational state` | repo → OpenClaw | reviewed/derived artifacts only: handoff, adoption packet, heartbeat reminder |
| `event` | bidirectional | repo lane actions emit internal events; OpenClaw/runtime emits runtime events back to repo |

**Phase 0 principle:** observability first, activation second.

## State Schema

```
state/
  capability_adoption/
    events.jsonl               # lane action events (append-only)
    packets/
      {ts}-{session_id}-{capability_id_slug}.json  # immutable history
    latest.json               # alias — newest packet by ts (global)
    status.json               # aggregate review status (from written packets)
```

### events.jsonl

One JSON line per lane action. Stable envelope + flexible payload.

```json
{
  "event_id": "uuid",
  "line_index": 0,
  "ts": "2026-04-14T...",
  "lane": "pull-system | sync-openclaw | refresh-skills | review-adoption",
  "source": "launcher-action | script",
  "session_id": "uuid",
  "review_requested": true,
  "payload": {}
}
```

- `line_index` is a monotonically increasing integer starting at 0. It is the append-order cursor and the safe comparison field for idempotency. `event_id` is for traceability only, not ordering.
- `review_requested: false` is allowed for informational events that don't need review.
- `lane=review-adoption` events are control events (manual review requests). They are excluded from candidate derivation — they trigger the review run but do not become candidates themselves.
- Lane actions with `review_requested: true` emit events that the review script will consume. Manual review requests are excluded from candidate derivation by lane filter.

### packets/{file}

Immutable once written. Never overwritten.

```json
{
  "packet_id": "uuid",
  "capability_id": "...",
  "ts": "...",
  "session_id": "...",
  "source_event_ids": ["uuid", ...],
  "kind": "skill | workflow | automation | mcp | launcher-update",
  "placement": "openclaw-skill | heartbeat | cron | taskflow | mcp | otto-control",
  "delta_targets": [...],
  "missing_primitives": [...],
  "activation_gate": "blocked | ready | partial",
  "confidence": 0.84,
  "verification_plan": [...],
  "notes": "..."
}
```

Filename: `packets/{ts}-{session_id}-{capability_id_slug}.json`

**`capability_id_slug` normalization rule:** lowercase, strip accents, replace non-alphanumeric chars (except `-`, `_`) with `-`, collapse multiple dashes, strip leading/trailing dashes. This produces a filesystem-safe identifier distinct from any human-readable capability label.

Example: `skill/GitHub-Review v1` → `skill-github-review-v1`
Example: `packets/2026-04-14T10-30-00-abc123-skill-github-review-v1.json`

### latest.json

Global pointer to newest packet by `ts`. Phase 1+ may add `latest_by_capability.json` as secondary index.

```json
{
  "packet_id": "...",
  "capability_id": "...",
  "ts": "...",
  "session_id": "..."
}
```

### status.json

Aggregate derived from written packets, not from raw events.

```json
{
  "ts": "...",
  "last_review_session": "...",
  "last_reviewed_line_index": 42,
  "total_packets": N,
  "gate_counts": {"blocked": N, "ready": N, "partial": N},
  "action_recommended": "none | review | activate"
}
```

`last_reviewed_line_index` is the processed cursor — the `line_index` of the most recently consumed event. It prevents re-processing the same events on reruns. Ordering is by `line_index`, not by `event_id` or `ts`.

### Idempotency & Dedup

Before writing a packet, the script checks:
1. `last_reviewed_line_index` in `status.json` — skip all events with `line_index <= last_reviewed_line_index`
2. `source_event_ids` dedup — skip if a packet with the same `capability_id` + `session_id` already exists in `packets/`

This ensures rerunning `review-adoption` is safe and does not inflate packet counts or gate counts.

## Lane Actions

| Action | Description | review_requested |
|---|---|---|
| `pull-system` | git fetch + status (pull only if explicitly flagged) | true |
| `sync-openclaw` | sync openclaw.json + write skill snapshot + write heartbeat candidate artifact | true |
| `refresh-skills` | scan skill folders → compute added/removed/changed | true |
| `review-adoption` | manual review request — emits a control event, excluded from candidate derivation | true (control event) |

Each lane action:
1. Does its primary work (existing behavior unchanged)
2. Appends one event to `state/capability_adoption/events.jsonl`
3. Sets `review_requested: true` in the event
4. Does NOT auto-inject anything into live OpenClaw

### skill snapshot artifact

Written by `sync-openclaw`. Read by OpenClaw or operator for awareness.

```
artifacts/openclaw/skill_snapshot.json
```

```json
{
  "ts": "...",
  "skills": [
    {
      "name": "agathon-soft-profile",
      "path": ".agents/skills/agathon-soft-profile",
      "status": "ready | draft | blocked",
      "routing_intent": "deep-profile",
      "persona": "strategist-fox"
    }
  ]
}
```

### heartbeat candidate artifact

Written by `sync-openclaw`. Not auto-injected in Phase 0.

```
artifacts/openclaw/heartbeat_reminder_candidates.json
```

```json
{
  "ts": "...",
  "reminders": [
    {
      "id": "capability-review-stale",
      "message": "review unactivated adoption packets",
      "interval_hours": 4,
      "requires": ["state/capability_adoption/packets"]
    }
  ]
}
```

## review-adoption Script

**Inputs:**
- `state/capability_adoption/events.jsonl`
- Optional: `--session-id` to scope to one session

**Algorithm:**
1. Load events, filter `review_requested: true` AND `lane != "review-adoption"`
2. Skip events where `line_index <= last_reviewed_line_index` (idempotency cursor)
3. Group remaining events by `session_id`
4. For each session, derive one or more capability candidates:
   a. Derive `capability_id` first (unique identifier; derived from lane + payload heuristics; needed for dedup, packet naming, latest.json)
   b. Classify `kind`
   c. Determine `placement`
   d. Compute `delta_targets`
   e. Identify `missing_primitives`
   f. Compute `activation_gate`:
      - `ready` — all primitives present, no conflicts
      - `blocked` — missing critical primitive or placement unclear
      - `partial` — some primitives present, others missing or uncertain
   g. Score `confidence` (0.0–1.0)
   h. Generate `verification_plan`
5. For each candidate, check dedup: if a packet with same `capability_id` + `session_id` exists, skip writing
6. Write one immutable packet per candidate
7. Update `latest.json` alias (points to newest packet by ts)
8. Update `status.json` from written packets

**Output:** adoption packet artifact only. No activation. No injection.

**Invocation:** `review-adoption.bat` or `main.bat → review-adoption`

## Launcher Integration

### New actions to add

- `pull-system` — git fetch + status
- `refresh-skills` — skill folder scan + event emit
- `review-adoption` — run review script

### Extended state fields

Add to `state/launcher/current.json` and `last_action.json`:

- `git_branch`
- `git_dirty`
- `skill_snapshot_status`
- `capability_review_status`

### BAT files

- `pull-system.bat`
- `refresh-skills.bat`
- `review-adoption.bat`

All follow the existing BAT shim pattern (resolve venv → delegate to Python).

## Files to create/modify

### New files

- `state/capability_adoption/` (directory — created by scripts)
- `state/capability_adoption/status.json` (initialized by first run)
- `scripts/manage/review_adoption.py`
- `scripts/manage/refresh_skills.py`
- `scripts/manage/pull_system.py`
- `scripts/manage/skill_snapshot.py` (extracted from sync-openclaw for clarity)
- `artifacts/openclaw/skill_snapshot.json` (written by sync-openclaw)
- `artifacts/openclaw/heartbeat_reminder_candidates.json` (written by sync-openclaw)
- `pull-system.bat`
- `refresh-skills.bat`
- `review-adoption.bat`

### Files to modify

- `src/otto/app/launcher.py` — add handlers for new actions
- `src/otto/launcher_state.py` — add `git_branch`, `git_dirty`, `skill_snapshot_status`, `capability_review_status`
- `src/otto/openclaw_support.py` — extend `sync_openclaw_config` to write skill snapshot + heartbeat candidate artifact + emit lane event
- `docs/launcher.md` — document new actions and state fields
- `docs/architecture.md` — note Phase 0 capability adoption transducer

## What is NOT in scope for Phase 0

- Auto-injection of artifacts into live OpenClaw
- Folder watchers or background monitors
- Heartbeat as primary review trigger
- Skill Maker, Automation Maker, Workflow Maker UI
- Auto-improvement loop
- Guarded git push to remote
- Activation of any capability without human verification
- `latest_by_capability.json` secondary index
