---
name: umkm-debt-negotiation
description: >-
  Handle UMKM debt negotiation as one object inside Crack-Heuristic-Research. Use when the user asks about debt, cash survival, mitigation, or negotiation in Josh Obsidian. Always source from Crack-Research program artifacts and avoid generic debt playbooks.
triggers:
  keywords:
    - "utang umkm"
    - "debt negotiation"
    - "mitigasi utang"
    - "cash survival"
    - "bertahan hidup"
    - "peluang uang cepat"
    - "receh"
    - "coverage ratio"
    - "debt-to-business bridge"
  suppress_if: [hygiene-check]
priority: 10
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: true
  output_schema: cron_report_v1
model_hint: standard
escalate_to: thought-partnership
memory_anchor:
  - "C:\\Users\\joshu\\Josh Obsidian\\20-Programs\\Crack-Research\\index.md"
  - "C:\\Users\\joshu\\Josh Obsidian\\20-Programs\\Crack-Research\\02-Feasibility\\crack-research-feasibility.md"
  - "C:\\Users\\joshu\\Josh Obsidian\\20-Programs\\Crack-Research\\04-Tracker\\PROGRAM_TRACKER.md"
constraints:
  - no-generic-debt-method
  - cite-specific-file-paths
  - debt-is-one-object-inside-crack-research
checkpoint_required: true
---

# UMKM Debt Negotiation

Debt is handled as one applied object under Crack-Heuristic-Research.

## Mandatory source order

1. `C:\Users\joshu\Josh Obsidian\20-Programs\Crack-Research\index.md`
2. `C:\Users\joshu\Josh Obsidian\20-Programs\Crack-Research\02-Feasibility\crack-research-feasibility.md`
3. `C:\Users\joshu\Josh Obsidian\20-Programs\Crack-Research\04-Tracker\PROGRAM_TRACKER.md`
4. relevant active project notes under `C:\Users\joshu\Josh Obsidian\30-Projects`

## Rules

- Do not suggest snowball, avalanche, or any external generic framework unless it already exists in Crack-Research notes.
- Tie each recommendation to tier/layer status from `PROGRAM_TRACKER.md`.
- Always preserve major product commitments while proposing short cash actions.
- If source evidence is missing, report the missing field and request the exact note update.

## Internal output contract

### `context_pack_v1`
- `source_meta`
- `active_programs`
- `active_projects`
- `primary_research_root`
- `debt_strategy_ref`
- `today_cash_actions`
- `major_product_commitments`

### `cron_report_v1`
- `top3`
- `next_action`
- `evidence_links`
- `debt_move`
- `program_gate_status`

## Daily cron behavior

- 14:00: produce top 3 near-term cash opportunities + 1 immediate action.
- 18:30: produce execution follow-up + 1 committed move.
- Sunday 18:30: produce debt mitigation review tied to Crack-Research gate status.

All cron outputs must include evidence file paths and one vault note destination.
