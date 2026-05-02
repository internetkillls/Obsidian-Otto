# Realtime Context + Cron Interfaces

## `context_pack_v1` (internal)

Purpose: per-chat refresh pack for money/debt/product reasoning.

```json
{
  "source_meta": ["C:/Users/joshu/Josh Obsidian/00-Meta/..."],
  "active_programs": ["Crack-Research"],
  "active_projects": ["CrackResearch-SME"],
  "primary_research_root": "C:/Users/joshu/Josh Obsidian/20-Programs/Crack-Research",
  "debt_strategy_ref": "C:/Users/joshu/Josh Obsidian/20-Programs/Crack-Research/04-Tracker/PROGRAM_TRACKER.md#Layer-2--Debt-to-Business-Bridge",
  "today_cash_actions": ["..."],
  "major_product_commitments": ["..."]
}
```

Required fields:
- `source_meta`
- `active_programs`
- `active_projects`
- `primary_research_root`
- `debt_strategy_ref`
- `today_cash_actions`
- `major_product_commitments`

## `cron_report_v1` (internal)

Purpose: delivery contract for 14:00, 18:30, and Sunday 18:30 runs.

```json
{
  "top3": [
    {"opportunity": "...", "why_now": "...", "evidence_path": "..."}
  ],
  "next_action": "...",
  "evidence_links": ["C:/Users/joshu/Josh Obsidian/..."],
  "debt_move": "...",
  "program_gate_status": "tier1_active|tier2_blocked|tier3_prep"
}
```

Required fields:
- `top3`
- `next_action`
- `evidence_links`
- `debt_move`
- `program_gate_status`

## Delivery rule

- Send summary to Telegram (`Otto` account/channel flow).
- Persist same payload to vault note under Crack-Research tracker lane.
