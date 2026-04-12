# AGENTS.md

## Repository mission

This repository is the stable control plane for Obsidian-Otto.

### Main rule
Never treat the raw Obsidian vault as prompt context unless a scoped verification explicitly requires it.

## Priority order

1. Read `tasks/active/` to understand the current goal.
2. Read current state:
   - `state/handoff/latest.json`
   - `state/checkpoints/pipeline.json`
3. Read current artifacts:
   - `artifacts/summaries/gold_summary.json`
   - `artifacts/reports/kairos_daily_strategy.md`
   - `artifacts/reports/dream_summary.md`
4. Only then decide whether a fresh scoped pipeline is needed.

## Retrieval policy

- Prefer **Gold summary** first.
- Then prefer **Silver SQL**.
- Then optional **Chroma**.
- Only use raw Bronze or raw vault files if evidence is still insufficient.
- Use the smallest possible scope for any refresh.

## Operational policy

- Keep root simple and operator-friendly.
- Use the provided batch files before inventing new launch flows.
- Keep logs and state files updated when adding new automation.
- Any long-running loop must write to:
  - `logs/`
  - `state/run_journal/`
  - `state/handoff/`

## Response protocol

- Run tools first.
- Show results.
- Then state next step briefly.
- Do not narrate routine actions.
- Exception: casual chat with Sir Agathon may stay conversational.

## Model routing

- Default executor is Codex.
- Prefer `codex/gpt-5.4` for execution.
- If Codex routing fails, prefer `gpt-5.3-codex` as coding fallback.
- Anthropic Sonnet or Opus may be used only for chunking, planning, synthesis, and work-package shaping.
- Anthropic planner must not be the final executor for repo changes, tool-heavy work, or irreversible actions.
- Planner output must hand off concrete steps to Codex for execution.

## Language boundary

- Human-facing final artifacts must be in English or Indonesian.
- If machine-facing plan or handoff notes are externalized, they may be in Chinese.
- Do not expose Chinese planning notes to Sir Agathon unless explicitly requested.

## Codex behavior guidance

- Prefer repo-scoped skills in `.agents/skills/`.
- Prefer custom agents in `.codex/agents/` only for narrow jobs.
- Do not spawn subagents unless the user explicitly asks for them.
- Use shell-driven transducers first; do not assume MCP exists yet.
- Never dump full vault text when a structured retrieval package is enough.

## Data hygiene rules

- Bronze is raw.
- Silver is normalized.
- Gold is decision-ready.
- Training export must come from reviewed Gold only.
- Do not create or suggest fine-tuning runs for unsupported GPT-5/Codex models.

## Wellbeing / SWOT boundary

- Only use wellbeing or SWOT signals if they come from explicit local fields or reviewed Gold summaries.
- Do not invent emotions or personal traits.
- Keep support practical, grounded, and non-manipulative.
