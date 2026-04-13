# Otto MCP-Native Architecture Design

## Date
2026-04-13

## Author
Otto (with Sir Agathon)

## Status
Approved — pending implementation plan

---

## 1. Architecture Target

```
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

**Plane definitions:**

- **MCP Fabric** = execution plane
- **OpenClaw** = gateway and broker
- **Obsidian-Otto** = control plane for continuity, retrieval curation, and pipeline state

**Key principle:** OpenClaw orchestrates both sides — talks to MCP Fabric for execution, and to Obsidian-Otto for state, retrieval, pipeline, and telemetry. Obsidian-Otto is not "behind" MCP; it is a parallel layer managed by the same broker.

---

## 2. Migration Matrix

### Retain in Otto (permanent — MCP does not replace)

| Item | Reason |
|---|---|
| `state/handoff/latest.json` | Continuity packet across sessions, repo-specific |
| `state/checkpoints/*` | Internal run status, not tool output |
| `state/run_journal/*` | Observability + audit trail |
| `artifacts/summaries/gold_summary.json` | Curated evidence pack, not raw tool output |
| `artifacts/reports/*` | KAIROS, Dream, profile synthesis — operational reflection |
| Bronze scan + Bronze manifest | Raw inventory, pipeline entry point |
| Silver SQLite | Normalized queryable metadata |
| Gold summary + training gate | Decision-ready + governance boundary |
| Retrieval policy (Gold → Silver → vector → raw) | Control logic, not execution |
| KAIROS / Dream / heartbeat | Telemetry + strategy synthesis |
| Thin policy/guardrail layer | Policy, guardrails, retrieval order, execution selection |

> **Note on thin policy layer:** The routing/config complexity currently in `routing.yaml`, `personas.yaml`, and `kernelization.yaml` survives only as a thin policy and safety layer. After MCP is live, parts of the current routing thickness may be simplified — the survival justification is policy/guardrail function, not legacy complexity retention.

### Temporary in Otto until MCP exists

| Item | Reason |
|---|---|
| Interactive Obsidian note access | Pipeline ingest internal — keep. User-facing execution — migrate. |
| Vault command execution | Handled by Obsidian CLI MCP when available |
| Prompt-routed tool behavior | Execution via prompt, not tool contract |

> **Distinction:** Bronze scan and Silver ingest are internal pipeline operations — they are Retain. Interactive user-facing reads/writes are Temporary. Do not conflate the two.

### Migration blockers / current infra gaps

| Item | Status |
|---|---|
| Docker | Not set up |
| Obsidian MCP container | Does not exist |
| Obsidian CLI MCP container | Does not exist |
| `launch-mcp.bat` | Placeholder, not operational |
| `config/docker.yaml` | `enabled: false` |

These are evidence that MCP infra does not yet exist, not components of the architecture.

### Move to MCP once infra is live

| Item | Reason |
|---|---|
| Read / write Obsidian notes | Handled by Obsidian MCP |
| Vault CLI commands | Handled by Obsidian CLI MCP |
| Deterministic tool execution | Tool contract via MCP, not prompt router |
| Cross-system capability access | Owned by their respective MCP servers |

---

## 3. Decision Principles

### Rule 1 — Capability access
**MCP first, if infra exists.**  
If the concern is "do an action against a system," check whether an MCP server is available. If it is not available yet, do not automatically create permanent local wrappers. Instead: decide whether a temporary local bridge is needed, and flag the item explicitly as a migration candidate. The default is not "add permanent wrapper" — it is "temporary bridge with migration note, or defer."

### Rule 2 — State, continuity, curation
**Otto owns it.**  
If the concern is long-term memory, summary, telemetry, governance, or pipeline — that is Otto's domain, not MCP's.

### Rule 3 — Default question for new features
**"Is this an execution concern or a control/state concern?"**

---

## 4. Document Ownership

| File | Role |
|---|---|
| `docs/architecture.md` | Source of truth for current architecture |
| `docs/migration-plan.md` | Why we move to MCP fabric and migration stages |
| `docs/state-model.md` | What checkpoints are and which state files are official |
| `docs/cache-stack-and-events.md` | Data-plane doc (Bronze/Silver/Gold flow), not architecture diagram |
| `docs/model-routing.md` + `config/routing.yaml` | Control policy, not architecture |
| `docs/superpowers/specs/*` | Exploratory design specs before adoption |
| `state/*` | Runtime checkpoint/status only — not architecture definition |

---

## 5. What This Design Replaces

The old `docs/architecture.md` described:
```
User / Telegram / TUI
  -> Otto Runtime
  -> Retrieval controller
  -> Bronze / Silver / Gold data stack
  -> KAIROS telemetry
  -> Dream consolidation
  -> Codex skills + AGENTS + optional custom agents
```

This was accurate when Otto was the primary execution engine. The new design reflects the split between MCP execution fabric and Otto control plane. `docs/architecture.md` will be updated to reflect this design.

---

## 6. What This Design Preserves

- Bronze/Silver/Gold pipeline — pipeline stays, MCP enhances tool access
- KAIROS, Dream, heartbeat — telemetry and reflection remain Otto's responsibility
- State externalization (`handoff`, `checkpoint`, `run_journal`) — continuity ownership stays
- Retrieval policy — control logic stays in Otto
- Training gate — governance boundary stays
- 11 skills already built — they remain, routing via OpenClaw, execution via MCP when live