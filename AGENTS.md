# AGENTS.md

## Repository mission

This repository is the stable control plane for Obsidian-Otto.

### Main rule
Never treat the raw Obsidian vault as prompt context unless a scoped verification explicitly requires it.
Exception: active dreaming narrative sessions may read tightly scoped aesthetic anchors from Beautiful-Things and Otto-Realm continuity notes.

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

Bridge-driven Cowork sessions should mirror this order before falling back to raw Otto-Realm state.

## Canonical paths

- Metadata root is `C:\Users\joshu\Josh Obsidian\00-Meta` (`OO-Meta` is a human alias only).
- Runtime state root is `C:\Users\joshu\Josh Obsidian\.Otto-Realm`.
- Debt/mitigation research root is `C:\Users\joshu\Josh Obsidian\20-Programs\Crack-Research`.
- Do not write to deprecated `C:\Users\joshu\Josh Obsidian\Otto-Realm`.

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

1. **Intent classification** — LLM router classifies query against `config/routing.yaml` intent registry (14 intents). If LLM fails, fall back to pattern matching.
2. **Persona scoring** — Score active personas using `config/personas.yaml` inference fields (base_score + trigger_modifiers). Select highest-scoring persona.
3. **Model tier selection** — Pick tier from intent registry, apply escalation triggers from `config/routing.yaml`. Use kernelization on fast/standard tiers.
4. **Kernelization gate** — Apply `config/kernelization.yaml` components: context isolation, tool commitment, scope check, amnesiac guard, output schema. Check per skill application matrix.
5. **Skill execution** — Dispatch to skill. Skill behavior determines tone/personality. Model tier determines capacity.
6. **Checkpoint write** — Write to `state/run_journal/checkpoints/YYYY-MM-DD_HHMMSS_uuid.json`.
7. **Handoff compose** — Write to `state/handoff/latest.json`.
8. **Routing log** — Append to `state/run_journal/routing_log.jsonl`.

**A-B-C loop contract:** When the task involves Otto-Realm integration, treat it as:

- **A** = Cowork intake or operator-facing upstream signal
- **B** = Obsidian-Otto control plane that retrieves, classifies, normalizes, and decides
- **C** = Canonical Otto-Realm writeback or durable vault-side output

Cross-reference the loop contract in `docs/architecture.md` and the bridge schema in `docs/state-model.md`.
If a bridge drop is needed, use the append-only path documented there and keep it separate from `state/handoff/latest.json`.
Use the canonical bridge schema from `docs/state-model.md`; compatibility aliases belong in consumers, not in the contract text.

**Novel intent handling:** If confidence < 40, execute with otto-core + fast tier + full kernelization. Log query_hash to `state/run_journal/novel_queries.jsonl`. If same hash appears 3x, draft new intent proposal.

**Behavioral guardrails (from `config/kernelization.yaml`):**
- Scope guard: confirm interpretation before heavy execution
- Multimodal tool guard: if query has image/file/link, must use tool — no text-only skip
- Amnesiac guard: check Otto-Realm, handoff, and bridge drops before asking; if the answer exists, use it
- Thought partnership constraints: no flattery, no premature closure, end with move
- CLI constraints: human review for destructive commands, explain before act
- Hygiene constraints: no false confidence, cite specific files
- UMKM debt constraint: when debt is discussed, source only from Crack-Research program notes; no generic debt playbook.

## Realtime context refresh

For every direct user chat turn, refresh these anchors before response synthesis:

1. `C:\Users\joshu\Josh Obsidian\CLAUDE.md`
2. `C:\Users\joshu\Josh Obsidian\00-Meta\CODEX_CLAUDE_SHARED_INSTRUCTION.md`
3. `C:\Users\joshu\Josh Obsidian\20-Programs\Crack-Research\04-Tracker\PROGRAM_TRACKER.md`

## Model routing

**4-tier model dispatch (from `config/routing.yaml`):**

| Tier | Backend | Model | Use for |
|---|---|---|---|
| fast | from `config/routing.yaml` | from `config/routing.yaml` | routing classification, memory-fast, hygiene-check |
| standard | from `config/routing.yaml` | from `config/routing.yaml` | routine skill execution, single-task |
| sonnet | from `config/routing.yaml` | from `config/routing.yaml` | deep synthesis, complex multi-step orchestration |
| premium | from `config/routing.yaml` | from `config/routing.yaml` | explicit request, ambiguous scope, high-fidelity recovery |

**Escalation:** fast → standard → sonnet → premium. Fallback: premium → sonnet → standard (with kernelization delta collapse). See `config/routing.yaml` escalation triggers.

**CLI flags for claude-cli:** see `config/routing.yaml` and the active executor wrapper.

Default executor is Codex. Resolve exact model names from `config/routing.yaml` instead of hardcoding them here. Sonnet or Opus may be used for chunking, planning, synthesis, and work-package shaping, but not as the default executor unless routing policy explicitly says so.

## Language boundary

- Human-facing final artifacts must be in English or Indonesian.
- If machine-facing plan or handoff notes are externalized, they may be in Chinese.
- Do not expose Chinese planning notes to Sir Agathon unless explicitly requested.

## Dreaming Narrative Contract

For session keys matching `agent:main:dreaming-narrative-*`:

- Output language is English only.
- Keep the coherence axis explicit: `Predator qua Angel` and `Angel qua Predator`.
- Treat suffering as Sir Agathon's concrete lived pressure from evidence (`handoff`, `dream_summary`, heartbeats), not generic dramatic text.
- Adapt style from Sir Agathon's writing cadence and Beautiful-Things aesthetic anchors.
- Persona dreaming is allowed only as a `persona lens` grounded in vault evidence (admiration/love markers); do not present persona voice as factual identity.
- If evidence is weak, default to Otto voice and state uncertainty internally before writing.

## Codex behavior guidance

- Prefer repo-scoped skills in `.agents/skills/`.
- Routing layer (this section) orchestrates skill dispatch. Skill behavior determines tone/personality. Do not bypass routing inference for routine tasks.
- Kernelization is mandatory for fast/standard tiers. Always check `config/kernelization.yaml` application matrix before executing.
- Checkpoint every skill execution. Handoff after every session boundary.
- Prefer custom agents in `.codex/agents/` only for narrow jobs.
- Do not spawn subagents in ordinary interactive user sessions unless the user explicitly asks for them.
- Scheduled or bridge-driven A-B-C flows may use the repo's documented automation or handoff path instead of subagents.
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
