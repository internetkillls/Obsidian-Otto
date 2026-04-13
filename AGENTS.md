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

## Routing inference (SKILL + AGENTIC)

Before any tool use or planning, run routing inference:

1. **Intent classification** — LLM router classifies query against `config/routing.yaml` intent registry (13 intents). If LLM fails, fall back to pattern matching.
2. **Persona scoring** — Score active personas using `config/personas.yaml` inference fields (base_score + trigger_modifiers). Select highest-scoring persona.
3. **Model tier selection** — Pick tier from intent registry, apply escalation triggers from `config/routing.yaml`. Use kernelization on fast/standard tiers.
4. **Kernelization gate** — Apply `config/kernelization.yaml` components: context isolation, tool commitment, scope check, amnesiac guard, output schema. Check per skill application matrix.
5. **Skill execution** — Dispatch to skill. Skill behavior determines tone/personality. Model tier determines capacity.
6. **Checkpoint write** — Write to `state/run_journal/checkpoints/YYYY-MM-DD_HHMMSS_uuid.json`.
7. **Handoff compose** — Write to `state/handoff/latest.json`.
8. **Routing log** — Append to `state/run_journal/routing_log.jsonl`.

**Novel intent handling:** If confidence < 40, execute with otto-core + fast tier + full kernelization. Log query_hash to `state/run_journal/novel_queries.jsonl`. If same hash appears 3x, draft new intent proposal.

**Behavioral guardrails (from `config/kernelization.yaml`):**
- Scope guard: confirm interpretation before heavy execution
- Multimodal tool guard: if query has image/file/link, must use tool — no text-only skip
- Amnesiac guard: check Otto-Realm + handoff before asking; if answer exists, use it
- Thought partnership constraints: no flattery, no premature closure, end with move
- CLI constraints: human review for destructive commands, explain before act
- Hygiene constraints: no false confidence, cite specific files

## Model routing

**4-tier model dispatch (from `config/routing.yaml`):**

| Tier | Backend | Model | Use for |
|---|---|---|---|
| fast | openai-codex | gpt-5.4-mini | routing classification, memory-fast, hygiene-check |
| standard | openai-codex | gpt-5.4 | routine skill execution, single-task |
| sonnet | claude-cli | claude-sonnet-4-6 | deep synthesis, complex multi-step orchestration |
| premium | claude-cli | claude-opus-4-6 | explicit request, ambiguous scope, high-fidelity recovery |

**Escalation:** fast → standard → sonnet → premium. Fallback: premium → sonnet → standard (with kernelization delta collapse). See `config/routing.yaml` escalation triggers.

**CLI flags for claude-cli:** `--allow-dangerously-skip-permission --bypassPermissions`

Default executor is Codex. Prefer `openai-codex/gpt-5.4-mini` for fast tasks, `openai-codex/gpt-5.4` for standard execution. Claude Sonnet or Opus may be used only for chunking, planning, synthesis, and work-package shaping — not as default executor.

## Language boundary

- Human-facing final artifacts must be in English or Indonesian.
- If machine-facing plan or handoff notes are externalized, they may be in Chinese.
- Do not expose Chinese planning notes to Sir Agathon unless explicitly requested.

## Codex behavior guidance

- Prefer repo-scoped skills in `.agents/skills/`.
- Routing layer (this section) orchestrates skill dispatch. Skill behavior determines tone/personality. Do not bypass routing inference for routine tasks.
- Kernelization is mandatory for fast/standard tiers. Always check `config/kernelization.yaml` application matrix before executing.
- Checkpoint every skill execution. Handoff after every session boundary.
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
