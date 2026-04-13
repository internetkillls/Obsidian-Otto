# Routing Audit Report — Post-MCP Deployment

**Date:** 2026-04-13
**Status:** Pre-MCP audit (baseline before migration)

## Audit Scope

Assess complexity of `config/routing.yaml`, `config/personas.yaml`, `config/kernelization.yaml`.
Determine which branches can be simplified to thin policy/guardrail after MCP is live.

## Baseline: Current Routing Complexity

### config/routing.yaml

| Section | Entries | Post-MCP |
|---|---|---|
| backends | 2 (openai-codex, claude-cli) | ADD: MCP backends for obsidian-read/write/vault |
| tiers | 4 (fast, standard, sonnet, premium) | Keep (model tier selection, not execution) |
| intents | 13 (deep-profile, vault-maintenance, dream-consolidate, memory-recall-fast, memory-recall-deep, hygiene-check, scholarly-research, visual-precedent, obsidian-cli, typst-document, thought-partnership, swot-analysis, operational-handoff) | obsidian-cli intent — update skill execution from CLI to MCP |
| llm_router | 1 (gpt-5.4-mini, 3s timeout) | Keep (intent classification is control plane) |
| fallback | keyword_intersection, 3 defaults | Keep (fallback routing is control plane) |
| novel_intent | skillification_threshold: 3, auto_create_draft: true | Keep (Otto policy) |
| escalation | 7 escalation rules (fast→standard, standard→sonnet, etc.) | Keep (OpenClaw broker escalation) |
| time_windows | 4 windows (morning_rtw, afternoon_swot, evening_sm2, night_urgent) | Keep (temporal routing policy) |

### config/personas.yaml

| Persona | Role | Tool Policy | Post-MCP |
|---|---|---|---|
| otto-core | Default co-assistant | fast-then-deep | Keep |
| archivist-owl | Memory and note retrieval | retrieval-first | Keep — retrieval policy stays Otto |
| strategist-fox | Planning, SWOT, thought partnership | kairos-first | Keep |
| builder-beaver | Ops, implementation, tooling | code-heavy | Keep — tool list extends with MCP |
| auditor-crow | Critique, verification, hygiene | critic-first | Keep |
| dreamer-moth | Reflection and creative consolidation | dream-first | Keep |
| sentinel-whale | Boundaries, wellbeing, pacing | safety-first | Keep |

### config/kernelization.yaml

| Component | Purpose | Post-MCP |
|---|---|---|
| context_isolation | Per-chunk context window management | Keep — Otto pipeline control |
| tool_commitment | Model declares tools before use | Keep — applies to MCP tool calls too |
| scope_check | Confirm scope before execution | Keep — policy gate |
| amnesiac_guard | Check Otto-Realm/handoff before asking | Keep — Otto internal policy |
| output_schema | Structured output per skill (10 schemas) | Keep — skill output contracts |
| constraints | Per-intent behavior rules (thought-partnership, obsidian-cli, hygiene-audit) | Keep — policy rules |

## Simplification Candidates

| Branch | Current Behavior | Post-MCP Behavior | Keep? |
|---|---|---|---|
| obsidian-cli intent execution | Codex/Claude CLI executes obsidian-cli-expert-system skill → vault CLI subprocess | MCP tool contract via obsidian-cli-mcp | **Update** — change execution path, keep intent/triggers |
| vault-read intent (none currently) | Currently reads via Bronze scan → Silver SQLite | MCP tool contract for direct vault reads | **ADD** — new backend entry in routing.yaml when user-facing vault read migrates |
| vault-write intent (none currently) | No direct vault write path | MCP tool contract for direct vault writes | **ADD** — new backend entry when Phase 2a migrates |
| tool_contract template (kernelization) | Currently Codex/Claude CLI tool calls | MCP tool calls via obsidian-mcp | **Update** — tool commitment template for MCP |

## Policy/Guardrail Branches to Preserve (Thin Layer)

These survive MCP migration as policy/guardrail, not execution:

- `escalation.fast_to_standard` — tier escalation (OpenClaw broker)
- `escalation.standard_to_sonnet/premium` — model escalation (OpenClaw broker)
- `constraints.thought-partnership` — no-flattery, no-premature-closure, end-with-move
- `constraints.obsidian-cli` — human-review-required, explain-before-act
- `constraints.hygiene-audit` — no-false-confidence, cite-specifics
- `constraints.general` — not-amnesiac, not-misunderstand-scope, not-skip-tools
- `amnesiac_guard` — check Otto-Realm/handoff before asking
- `scope_check` — confirm scope before execution (kernel gate)
- `context_isolation` — chunk token limits per tier
- `time_windows` — RTW, SWOT, SM-2, night-urgent routing signals
- `novel_intent` — skillification_threshold, auto_create_draft
- All `suppress_if_intent` rules in personas.yaml
- All `escalate_to_skill/persona/model` rules in personas.yaml

## Action Items

- [ ] Post-MCP Phase 1b: Add `obsidian-mcp` and `obsidian-cli-mcp` as new backends in routing.yaml
- [ ] Post-MCP Phase 1b: Update `obsidian-cli` intent — change skill execution from CLI to MCP tool contract
- [ ] Post-MCP Phase 2a: Add vault-read/vault-write intents with MCP backend routing
- [ ] Post-MCP Phase 2b: Remove vault-cli subprocess logic from obsidian-cli-expert-system skill
- [ ] Post-MCP Phase 3a: Remove prompt-routed tool execution branches from routing.yaml if replaced by MCP tool contracts
- [ ] Post-MCP Phase 3a: Keep all policy/guardrail branches — simplify to comment references

## Files to Modify Post-MCP

| File | Change |
|---|---|
| `config/routing.yaml` | ADD: mcp-obsidian and mcp-obsidian-cli backends. UPDATE: obsidian-cli intent execution |
| `config/personas.yaml` | Keep unchanged — persona inference is control plane |
| `config/kernelization.yaml` | Keep unchanged — kernelization is policy layer |
| `config/migration-bridges.yaml` | Mark BRIDGE-004, 005, 006, 007 as DONE as phases complete |

## Routing Complexity Assessment

**Before MCP:** ~356 lines across 3 files (routing.yaml ~354, personas.yaml ~110, kernelization.yaml ~356)
**After MCP:** Routing inference + persona inference + kernelization are **Otto control plane** — they decide *which MCP tool* to call, not *how* the tool executes. Complexity stays, intent changes.

The migration reduces complexity in **execution** (prompt-routed tool calls → MCP tool contracts) but keeps complexity in **policy** (intent classification, persona inference, escalation rules, kernelization gates). This is the correct split per the MCP-native architecture design.
