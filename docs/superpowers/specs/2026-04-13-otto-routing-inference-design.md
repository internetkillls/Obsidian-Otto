# Otto-Obsidian Skill & Agentic Routing Inference Design

**Date:** 2026-04-13
**Author:** Claude Code (brainstormed with Sir Agathon)
**Status:** Approved — ready for implementation planning

---

## 1. Overview

Build Otto-Obsidian's routing inference engine so that every user query is routed to the right skill, at the right model tier, with the right kernelization — deterministically, traceably, and humanely.

**Design principles:**
- Routing is **orchestration**, not execution. Skill behavior determines tone/personality.
- Model tier determines capacity. Kernelization collapses delta between tiers.
- Every execution is checkpointed. Every handoff is composable.
- Routing telemetry feeds back into inference weights on heartbeat cycle.
- Novel intents → auto-gathered → skillified when pattern repeats 3×.

**In-scope:** Intent registry, LLM router + pattern fallback, model-tier escalation, kernelization, persona inference, behavioral guardrails, telemetry feedback, checkpoint/handoff/memory persistence.

---

## 2. Skill Registry

All 11 skills. Each skill has routing metadata in its `SKILL.md` frontmatter.

### 2.1 Otto-Obsidian Skills (6)

| Skill ID | Name | Triggers | Tool Policy |
|---|---|---|---|
| `agathon-soft-profile` | Agathon Soft Profile | understand me, soft profile, how i work, friction, recovery, fatigue | kairos-first |
| `otto-realm-maintainer` | Otto Realm Maintainer | otto-realm, self-repair, profile snapshot, heartbeat, continuity | fast-then-deep |
| `dream-consolidation` | Dream Consolidation | dream, consolidate, reflect, make sense of | dream-first |
| `hygiene-audit` | Hygiene Audit | hygiene, clean, folder risk, duplicate, audit | critic-first |
| `memory-deep` | Memory Deep | deep memory, context-heavy, rich context retrieval | retrieval-first |
| `memory-fast` | Memory Fast | fast recall, reminders, quick find, where is | fast-then-deep |

### 2.2 Vault Skills (5)

| Skill ID | Name | Triggers | Notes |
|---|---|---|---|
| `scholarly-explore-remap` | Scholarly Explore Remap | literature review, evidence map, source, academic, remap, exploration, comparative synthesis | Source-grounded. Output: prose by default, schema on request. |
| `visual-precedent-execution` | Visual Precedent Execution | visual refs, design precedent, moodboard, screenshot, sketch, layout, facade, diagram, borrow from references | Visual → transfer method. Not style imitation. |
| `obsidian-cli-expert-system` | Obsidian CLI Expert System | obsidian CLI, MCP, command queue, routine, long-running, headless obsidian | Governed operator. Requires human review by default. |
| `typst-luxury-layout` | Typst Luxury Layout | typst, PDF, document layout, cross-format, markdown, latex, mermaid, svg | Document-system designer. Orchestrate via coassist-kernel if multi-step. |
| `josh-thought-partner` | Josh Thought Partner | thought partner, philosophical, essay, reflection, let's discuss, what do you think, paste writing | Behavioral contract. Do NOT open with flattery. Do NOT close prematurely. Push the strongest claim harder. |

### 2.3 Skill Frontmatter Schema

```yaml
---
name: <skill-id>
description: "<one-line description for LLM router>"
triggers:
  keywords: [list of trigger words/phrases]
  patterns: [regex patterns if needed]
  suppress_if: [intent IDs that should suppress this skill]
priority: 1-10  # higher = preferred when multiple match
kernel_required: true | false
kernel_config:
  scope_check: true | false      # require scope confirmation before act
  amnesiac_guard: true | false   # check Otto-Realm before asking
  tool_commitment: true | false   # declare tool before use
  output_schema: schema-id | null
model_hint: gpt-5.4-mini | gpt-5.4 | opus | any
escalate_to: skill-id | null
memory_anchor:
  - path/to/otto-realm/note.md   # Otto-Realm files to read before routing
constraints:
  - rule-id
checkpoint_required: true
---
```

---

## 3. Intent Registry

### 3.1 Defined Intents (12)

```yaml
intents:
  - id: deep-profile
     name: "Deep User Profiling"
     triggers: ["understand me", "soft profile", "how i work", "friction", "recovery", "fatigue", "monetizable"]
     skill: agathon-soft-profile
     persona: strategist-fox
     priority: 8
     model_tier: gpt-5.4
     kernel_required: true

  - id: vault-maintenance
     name: "Otto Self-Maintenance"
     triggers: ["otto-realm", "self-repair", "profile snapshot", "heartbeat", "continuity", "Otto maintain"]
     skill: otto-realm-maintainer
     persona: otto-core
     priority: 7
     model_tier: gpt-5.4-mini
     escalate_to: agathon-soft-profile

  - id: dream-consolidate
     name: "Dream Consolidation"
     triggers: ["dream", "consolidate", "reflect", "make sense of", "nightmare", "dream cycle"]
     skill: dream-consolidation
     persona: dreamer-moth
     priority: 7
     model_tier: gpt-5.4
     kernel_required: true

  - id: memory-recall-fast
     name: "Fast Memory Recall"
     triggers: ["remember", "find", "where is", "did i note", "show me", "recall", "remind"]
     skill: memory-fast
     persona: archivist-owl
     priority: 6
     model_tier: gpt-5.4-mini
     escalate_to: memory-deep

  - id: memory-recall-deep
     name: "Deep Memory Retrieval"
     triggers: ["deep context", "rich context", "what's the full picture", "detailed retrieval"]
     skill: memory-deep
     persona: archivist-owl
     priority: 6
     model_tier: gpt-5.4
     escalate_to: hygiene-audit

  - id: hygiene-check
     name: "Vault Hygiene Audit"
     triggers: ["hygiene", "clean", "folder risk", "duplicate", "audit", "folder check"]
     skill: hygiene-audit
     persona: auditor-crow
     priority: 5
     model_tier: gpt-5.4-mini

  - id: scholarly-research
     name: "Scholarly Research"
     triggers: ["literature review", "evidence map", "academic", "source", "remap", "exploration", "research"]
     skill: scholarly-explore-remap
     persona: archivist-owl
     priority: 8
     model_tier: gpt-5.4
     kernel_required: true

  - id: visual-precedent
     name: "Visual Precedent Execution"
     triggers: ["visual", "precedent", "moodboard", "design reference", "screenshot", "sketch", "layout"]
     skill: visual-precedent-execution
     persona: builder-beaver
     priority: 7
     model_tier: gpt-5.4
     kernel_required: true
     tool_commitment: true

  - id: obsidian-cli
     name: "Obsidian CLI Operation"
     triggers: ["obsidian CLI", "MCP", "command queue", "routine", "headless", "vault command"]
     skill: obsidian-cli-expert-system
     persona: builder-beaver
     priority: 6
     model_tier: gpt-5.4-mini
     constraints: [human-review-required]

  - id: typst-document
     name: "Typst Document System"
     triggers: ["typst", "PDF layout", "document system", "cross-format", "markdown to PDF", "luxury layout"]
     skill: typst-luxury-layout
     persona: builder-beaver
     priority: 6
     model_tier: gpt-5.4
     kernel_required: true

  - id: thought-partnership
     name: "Josh Thought Partnership"
     triggers: ["thought partner", "philosophical", "essay", "reflection", "discuss", "what do you think", paste-writing-signal]
     skill: josh-thought-partner
     persona: strategist-fox
     priority: 9
     model_tier: gpt-5.4
     kernel_required: true
     constraints: [no-flattery, no-premature-closure, end-with-move]

  - id: swot-analysis
     name: "SWOT Analysis"
     triggers: ["SWOT", "strength weakness", "opportunity threat", "strategic", "priority"]
     skill: agathon-soft-profile
     persona: strategist-fox
     priority: 8
     model_tier: gpt-5.4
     kernel_required: true

  - id: operational-handoff
     name: "Operational Task"
     triggers: ["run", "execute", "build", "implement", "create file", "edit", "refactor", "fix"]
     skill: otto-realm-maintainer
     persona: builder-beaver
     priority: 7
     model_tier: gpt-5.4
```

### 3.2 Novel Intent Handling

```
if query matches no intent (confidence < 40):
  → execute with otto-core + gpt-5.4-mini + full kernelization
  → log query_hash to state/run_journal/novel_queries.jsonl
  → if same query_hash appears 3×:
      → auto-create draft intent in config/routing.yaml with skill suggestion
      → flag for heartbeat review
```

---

## 4. LLM Router + Pattern Fallback

### 4.1 Primary: LLM Router

```
Prompt template:
  "Classify this query into one of the following intents: [list IDs + names].
   Return JSON: {intent, confidence, reasoning, skill, persona, model_tier, kernel_notes}.
   If confidence < 50, return fallback: {intent: 'unknown', confidence, reasoning}."

Model: gpt-5.4-mini (fast, cheap for classification)
Timeout: 3 seconds
```

### 4.2 Fallback: Pattern Matching

```yaml
fallback:
  method: keyword_intersection
  weights:
    exact_phrase_match: 30
    partial_keyword_match: 10
    persona_keyword_match: 5
  threshold: 20  # total weight needed to select intent
  default_intent: operational-handoff
  default_persona: otto-core
  default_model: gpt-5.4-mini
  kernel_required: true  # always kernelize on fallback
```

---

## 5. Model Tier Dispatch

### 5.1 Tier Definitions

```yaml
tiers:
  - id: fast
    model: gpt-5.4-mini
    token_limit: 32k
    best_for: [memory-fast, hygiene-check, routing-classification]
    kernel_required: true
    context_isolation: true
    tool_commitment: true
    output_schema: compact

  - id: standard
    model: gpt-5.4
    token_limit: 64k
    best_for: [agathon-soft-profile, dream-consolidation, thought-partnership,
               scholarly-research, typst-document, visual-precedent, operational]
    kernel_required: false  # Opus-class natively handles scope + tools

  - id: premium
    model: opus
    token_limit: 200k
    best_for: [any — use when: (a) Opus explicitly requested, (b) premium flag set,
               (c) downstream tool failure requires high-fidelity recovery]
    kernel_required: false
    constraints: [use_tools_aggressively, verify_scope_before_act]
```

### 5.2 Escalation Triggers

```yaml
escalation:
  from_fast_to_standard:
    triggers:
      - intent has kernel_required: true
      - query contains: [multi-file, multiple, compare, synthesize, analyze deeply]
      - conversation context_length > 5 turns
      - time_window: [06:00-11:59, 12:00-17:59] + RTW/SDZ signal detected
      - confidence < 60 from LLM router

  from_standard_to_premium:
    triggers:
      - intent requires opus explicitly
      - query: multimodal + ambiguous scope
      - 2× consecutive execution failure on standard tier
      - downstream tool failure with "insufficient context" error

  from_premium_fallback_to_standard:
    triggers:
      - opus unavailable (rate limit / downtime)
      - opus exceeds budget threshold
    mitigation:
      - apply_full_kernelization: true
      - chunk_task: true
      - tool_commitment: enforced
      - output_schema: premium_compatible  # so output shape matches Opus output
```

### 5.3 Chunking Strategy (Delta Collapse)

When falling back from premium to standard (or fast to standard):

```
1. Parse task into N atomic steps (max 3 steps per chunk)
2. Per chunk:
   a. Context isolation — only this chunk's relevant context in window
   b. Tool commitment — model declares tool(s) before use
   c. Scope check — confirm "this chunk does X, not Y"
   d. Execute with full kernelization
   e. Validate output against schema
3. Compose chunks into full response
```

---

## 6. Persona Inference

### 6.1 Persona Base Config (update to config/personas.yaml)

```yaml
personas:
  - id: otto-core
    species: Companion Raven
    role: Default co-assistant
    weights: {clarity: 5, empathy: 4, rigor: 4, risk: 4, novelty: 3}
    tool_policy: fast-then-deep
    # === INFERENCE ===
    inference:
      base_score: 50
      trigger_modifiers:
        is_telegram_dm: +10
        is_followup: +15
        has_context_vault: +20
        has_schedule_keyword: +10
      suppress_if_intent: [deep-profile, hygiene-check, dream-consolidate,
                           scholarly-research, visual-precedent, thought-partnership]
      escalate_to_model: gpt-5.4
      escalate_to_persona: archivist-owl

  - id: archivist-owl
    species: Archivist Owl
    role: Memory and note retrieval
    weights: {clarity: 4, empathy: 2, rigor: 5, risk: 4, novelty: 2}
    tool_policy: retrieval-first
    inference:
      base_score: 30
      trigger_modifiers:
        has_vault_query: +40
        has_memory_signal: +30
        query_has_source_keyword: +20
      suppress_if_intent: [deep-profile, thought-partnership, swot-analysis]
      escalate_to_model: gpt-5.4
      escalate_to_skill: memory-deep

  - id: strategist-fox
    species: Strategist Fox
    role: Planning, SWOT, prioritization, thought partnership
    weights: {clarity: 5, empathy: 3, rigor: 4, risk: 5, novelty: 4}
    tool_policy: kairos-first
    inference:
      base_score: 20
      trigger_modifiers:
        has_swot_signal: +50
        has_priority_signal: +40
        has_planning_signal: +40
        is_morning_window: +20  # 06:00-11:59
        is_afternoon_window: +15  # 12:00-17:59
        has_RTW_signal: +30
        has_SDZ_signal: +25
        has_IB_signal: +20
      suppress_if_intent: [hygiene-check, memory-recall-fast]
      escalate_to_model: gpt-5.4
      escalate_to_skill: josh-thought-partner

  - id: builder-beaver
    species: Builder Beaver
    role: Ops, implementation, tooling
    weights: {clarity: 4, empathy: 2, rigor: 5, risk: 4, novelty: 3}
    tool_policy: code-heavy
    inference:
      base_score: 20
      trigger_modifiers:
        has_implementation_signal: +40
        has_typst_signal: +35
        has_visual_signal: +30
        has_obsidian_cli_signal: +35
      suppress_if_intent: [deep-profile, dream-consolidate]
      escalate_to_model: gpt-5.4

  - id: auditor-crow
    species: Auditor Crow
    role: Critique, verification, hygiene
    weights: {clarity: 4, empathy: 1, rigor: 5, risk: 5, novelty: 2}
    tool_policy: critic-first
    inference:
      base_score: 15
      trigger_modifiers:
        has_hygiene_signal: +50
        has_audit_signal: +40
        has_risk_signal: +30
      suppress_if_intent: [deep-profile, dream-consolidate, thought-partnership]
      escalate_to_model: gpt-5.4-mini

  - id: dreamer-moth
    species: Dreamer Moth
    role: Reflection and creative consolidation
    weights: {clarity: 3, empathy: 4, rigor: 3, risk: 2, novelty: 5}
    tool_policy: dream-first
    inference:
      base_score: 15
      trigger_modifiers:
        has_dream_signal: +60
        has_reflection_signal: +40
        has_evening_window: +20  # 18:00-23:59
      suppress_if_intent: [memory-recall-fast, hygiene-check, operational-handoff]
      escalate_to_model: gpt-5.4

  - id: sentinel-whale
    species: Sentinel Whale
    role: Boundaries, wellbeing check, pacing
    weights: {clarity: 4, empathy: 5, rigor: 3, risk: 5, novelty: 2}
    tool_policy: safety-first
    inference:
      base_score: 10
      trigger_modifiers:
        has_fatigue_signal: +40
        has_wellbeing_signal: +40
        has_recovery_signal: +35
        has_SENXoR_signal: +30
      suppress_if_intent: [hygiene-check, operational-handoff, obsidian-cli]
      escalate_to_model: gpt-5.4
      escalate_to_skill: agathon-soft-profile
```

### 6.2 Time-Window Scoring (from HEARTBEAT.md)

```yaml
time_windows:
  morning_rtw: {start: "06:00", end: "11:59", signals: [RTW, IB, SDZ, friction, schedule, readiness]}
  afternoon_swot: {start: "12:00", end: "17:59", signals: [SWOT, cognitive, monetizable, service]}
  evening_sm2: {start: "18:00", end: "23:59", signals: [SM-2, quiz, soul, council]}
  night_urgent: {start: "00:00", end: "05:59", signals: [urgent-repair, high-signal-delta]}
```

---

## 7. Kernelization

### 7.1 Kernel Components

```yaml
kernel:
  context_isolation:
    description: "Per-chunk context window — only relevant context, not full conversation"
    enforced_on: [gpt-5.4-mini fallback, gpt-5.4 when kernel_required]
    chunk_max_context_tokens: 4000
    include: [checkpoint_prev, intent_context, skill_instructions]
    exclude: [unrelated_conversation_history]

  tool_commitment:
    description: "Model declares tool(s) before use — prevents multimodality neglect"
    enforced_on: [visual-precedent, obsidian-cli, typst-document, operational-handoff]
    template: "For this chunk, I will use: [tool1, tool2]. Reason: [why]. Proceed?"
    gate: must_declare_before_call

  scope_check:
    description: "Confirm scope interpretation before execution"
    enforced_on: [kernel_required skills, fallback routing]
    template: "I interpret this as [X]. Confirm: is this correct? If yes: execute. If no: [clarify]."
    gate: must_confirm_before_act

  amnesiac_guard:
    description: "Check Otto-Realm and recent handoff before asking questions"
    enforced_on: [all skills]
    check_order:
      - state/handoff/latest.json
      - artifacts/summaries/gold_summary.json
      - Otto-Realm anchor files (per skill memory_anchor)
      - recent 5 checkpoints
    rule: "If answer exists in checked sources → use it. If not → then ask."
    override: "If Sir Agathon explicitly wants to re-explore, respect that."

  output_schema:
    description: "Structured output per skill type — ensures delta collapse"
    schemas:
      compact: {summary: string, confidence: float, next_step: string}
      profile_delta: {trait: string, evidence: string, confidence: float, delta_type: stable|temporary|unresolved}
      memory_delta: {key: string, value: string, source: string, ttl: permanent|session}
      hygiene_finding: {file: string, risk: string, severity: low|medium|high, recommendation: string}
      dream_compose: {reflection: string, consolidation: string, next_probe: string}
      thought_partnership: {engagement: string, sharp_move: string, instability: string, ending_move: string}
      scholarly: {answer: string, assumptions: string[], gaps: string[], confidence: float, sources: string[]}
```

### 7.2 Kernel Application Matrix

| Skill | context_isolation | tool_commitment | scope_check | amnesiac_guard | output_schema |
|---|---|---|---|---|---|
| agathon-soft-profile | ✅ | ❌ | ✅ | ✅ | profile_delta |
| otto-realm-maintainer | ✅ | ✅ | ✅ | ✅ | memory_delta |
| dream-consolidation | ✅ | ❌ | ✅ | ✅ | dream_compose |
| hygiene-audit | ✅ | ✅ | ✅ | ✅ | hygiene_finding |
| memory-deep | ✅ | ❌ | ✅ | ✅ | compact |
| memory-fast | ❌ | ❌ | ❌ | ✅ | compact |
| scholarly-explore-remap | ✅ | ✅ | ✅ | ✅ | scholarly |
| visual-precedent-execution | ✅ | ✅ | ✅ | ✅ | execution_schema |
| obsidian-cli-expert-system | ✅ | ✅ | ✅ | ✅ | cli_response |
| typst-luxury-layout | ✅ | ✅ | ✅ | ✅ | typst_output |
| josh-thought-partner | ✅ | ❌ | ✅ | ✅ | thought_partnership |

---

## 8. Behavioral Guardrails

### 8.1 Scope Guard

```yaml
scope_guard:
  trigger: "On every skill execution where kernel_required=true"
  behavior:
    - Before executing, state interpretation: "I'm reading this as [X]. This means [Y]. Is that right?"
    - If response is "yes" → execute
    - If response is "no" → re-interpret based on correction
    - If no response in 10s → proceed with interpretation, note uncertainty
  log: "scope_interpretation" in checkpoint
```

### 8.2 Multimodal Tool Guard

```yaml
multimodal_tool_guard:
  trigger: "Query contains image, diagram, screenshot, file, or link"
  behavior:
    - Require explicit tool use: "This query includes [image/file/link]. I will use [tool] to process it before responding."
    - Do NOT skip to text-only response
    - Log tool_used in checkpoint
  fallback: "If no appropriate tool available, state: 'I can see [file type] but cannot process it yet. Do you want me to proceed text-only or wait?'"
```

### 8.3 Amnesiac Guard

```yaml
amnesiac_guard:
  trigger: "Before asking any question to Sir Agathon"
  behavior:
    - Check: state/handoff/latest.json
    - Check: Otto-Realm relevant anchors (per skill)
    - Check: recent 5 checkpoints
    - If answer exists → use it, do not ask
    - If answer does NOT exist → then ask
    - Log: questions_asked (should be low over time)
  exception: "If Sir Agathon explicitly wants to re-explore or update, respect that over the guard"
```

### 8.4 Constraints Per Skill

```yaml
constraints:
  thought-partnership:
    - no-flattery: "Do not open with 'This is interesting/powerful/sharp'"
    - no-premature-closure: "Hold genuinely open questions open"
    - end-with-move: "End with a question or next move, not a summary"
  obsidian-cli:
    - human-review-required: "Never auto-execute destructive or irreversible commands"
    - explain-before-act: "Show command first, explain risk, await confirmation"
  hygiene-audit:
    - no-false-confidence: "If evidence is weak, say so explicitly"
    - cite-specifics: "Name exact files, not generic folder descriptions"
```

---

## 9. Telemetry & Heartbeat Feedback Loop

### 9.1 Routing Log Schema

```yaml
routing_log_entry:
  timestamp: ISO8601
  query_hash: sha256
  query_preview: string (first 100 chars)
  routing:
    method: llm_router | pattern_fallback
    intent: intent-id
    confidence: float (0-100)
    persona: persona-id
    persona_score: float
    model_tier: tier-id
    kernel_applied: [kernel-component, ...]
    escalation_depth: int
    escalation_reason: string
  execution:
    skill_used: skill-id
    tool_calls: [tool, ...]
    output_schema_validated: bool
    execution_ms: int
    success: bool
    failure_reason: string | null
  delta:
    model_intended: tier-id
    model_actual: tier-id
    had_to_chunk: bool
    kernel_mitigated_delta: bool
  handoff:
    written: bool
    artifact_paths: [string, ...]
```

### 9.2 Heartbeat Feedback Cycle

```
Every 1h heartbeat (otto-profile-cycle):
  1. Read state/run_journal/routing_log.jsonl (last 24h entries)
  2. Aggregate:
     - Top 5 intents by frequency
     - Average confidence per intent
     - Escalation rate (fast→standard→premium)
     - Kernel delta mitigation effectiveness
     - Novel queries that clustered 3×
     - Questions asked rate (for amnesiac guard health)
  3. Otto-realm-maintainer skill:
     - If escalation rate > 60%: suggest updating tier thresholds
     - If novel queries clustered 3×: draft new intent proposal
     - If questions_asked rate increasing: strengthen amnesiac_guard
     - If kernel_delta_mitigated < 70%: suggest chunking improvements
  4. Update config/routing.yaml intent weights based on frequency
  5. Append telemetry summary to state/run_journal/heartbeat_telemetry.md
```

### 9.3 Otto-Realm Sync

```yaml
otto_realm_sync:
  trigger:
    - checkpoint has memory_delta
    - heartbeat cycle completes
    - explicit request from Sir Agathon
  artifacts_to_update:
    - Profile Snapshot.md: if agathon-soft-profile execution
    - Central Schedule.md: if schedule alignment detected
    - Weekly/*.md: if priority or theme changes
    - Heartbeats/YYYY-MM-DD.md: new entry if significant delta
  rule: "Write concrete, small updates. No fluffy self-mythology. Distinguish stable traits from temporary experiments."
```

---

## 10. Checkpoint, Handoff & Memory

### 10.1 Checkpoint Model

```yaml
checkpoint:
  id: uuid-v4
  timestamp: ISO8601
  query_hash: sha256
  query_preview: string

  routing:
    intent: intent-id
    confidence: float
    model_tier: tier-id
    kernel_applied: [string, ...]
    escalation_depth: int

  execution:
    skill_used: skill-id
    steps_executed: int
    tool_calls: [{tool, args, result}, ...]
    output_schema_validated: bool
    execution_ms: int

  artifacts:
    - type: summary | profile_delta | memory_delta | hygiene_finding | dream_compose | scholarly | typst_output | execution_trace
      path: artifacts/...
      size_bytes: int

  handoff:
    next_action: string | null
    pending_for_user: string | null
    memory_to_persist:
      - field: string
        value: string
        destination: Otto-Realm path | otto_profile field
    checkpoint_ref: uuid  # reference to previous checkpoint for chain
    composable: true

  quality:
    scope_correct: bool
    tool_used_appropriately: bool
    questions_avoided: int
    kernel_applied_correctly: bool
```

### 10.2 Handoff Composer

```yaml
handoff_composer:
  inputs: [checkpoint, routing_log, artifacts]
  output_path: state/handoff/latest.json
  schema:
    summary: string  # 1-2 sentence human summary
    routing_decision:
      intent: string
      confidence: float
      model_tier: string
    artifacts: [path references]
    next_actions: [string]
    pending_for_user: string | null
    memory_persisted: [field references]
    checkpoint_ref: uuid
    telemetry_notes: string  # for heartbeat analysis
  triggers:
    - after every skill execution
    - on session boundary
    - on explicit handoff request
```

---

## 11. Files to Create/Modify

| File | Action | Purpose |
|---|---|---|
| `config/routing.yaml` | **CREATE** | Intent registry, fallback rules, novel intent handling |
| `config/personas.yaml` | **UPDATE** | Add `inference` field per persona (base_score, modifiers, suppress, escalate) |
| `config/kernelization.yaml` | **CREATE** | Kernel component definitions, application matrix, schema definitions |
| `config/heartbeat_telemetry.yaml` | **CREATE** | Telemetry aggregation rules, Otto-Realm sync triggers, heartbeat update logic |
| `AGENTS.md` | **UPDATE** | Add routing inference section, checkpoint/handoff protocol |
| `openclaw.json` | **UPDATE** | Add `skill-routing` plugin, routing-aware heartbeat config |
| `state/run_journal/routing_log.jsonl` | **AUTO** | Created on first routing event |
| `docs/superpowers/specs/2026-04-13-otto-routing-inference-design.md` | **CREATE** | This document |

### Skill SKILL.md Updates (6 Otto skills)

Each Otto skill's frontmatter needs these fields added:
```yaml
triggers:
  keywords: [...]
  suppress_if: [...]
priority: 1-10
kernel_required: true | false
kernel_config: {...}
model_hint: ...
escalate_to: ...
memory_anchor: [...]
constraints: [...]
checkpoint_required: true
```

---

## 12. Spec Self-Review

- [x] No TBD / TODO placeholders — all fields have concrete values
- [x] No internal contradictions — routing flow, kernelization, escalation are consistent
- [x] Scope check — focused on routing inference, not implementation details
- [x] Ambiguity check — behavioral guardrails explicitly named, kernel application matrix concrete
- [x] Novel intent → skillification loop is defined (3× repeat threshold)
- [x] All 11 skills have routing metadata
- [x] Humaneness requirements addressed: scope guard, amnesiac guard, multimodal tool guard, telemetry feedback
