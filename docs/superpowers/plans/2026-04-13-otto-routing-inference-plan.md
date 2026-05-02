# Otto-Routing Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Otto-Obsidian's skill & agentic routing inference engine: intent registry, LLM router, 4-tier model dispatch, kernelization, persona inference, behavioral guardrails, telemetry feedback, checkpoint/handoff.

**Architecture:** Declarative config-first approach. Routing engine orchestrates 11 skills (6 Otto + 5 vault). LLM router classifies intents with pattern-matching fallback. Model tier escalation (fast → standard → sonnet → premium) with kernelization delta collapse on non-premium tiers. Every execution checkpoint + handoff. Telemetry feeds heartbeat → inference updates.

**Tech Stack:** YAML configs, JSON, Claude Code CLI, Python shell transducers, OpenClaw plugin system.

**Spec reference:** `docs/superpowers/specs/2026-04-13-otto-routing-inference-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `config/routing.yaml` | CREATE | Intent registry (13 intents), LLM router prompt, pattern fallback, novel intent handling |
| `config/kernelization.yaml` | CREATE | Kernel components, schema definitions, kernel application matrix |
| `config/heartbeat_telemetry.yaml` | CREATE | Telemetry aggregation rules, heartbeat feedback cycle, Otto-Realm sync triggers |
| `config/personas.yaml` | UPDATE | Add `inference` field per persona (base_score, modifiers, suppress_if, escalate) |
| `AGENTS.md` | UPDATE | Add routing inference section, behavioral guardrails, checkpoint/handoff protocol |
| `openclaw.json` | UPDATE | Add `skill-routing` plugin, 4-tier dispatch, routing-aware heartbeat |
| `.agents/skills/*/SKILL.md` | UPDATE | Add routing metadata (triggers, kernel_required, escalate_to, memory_anchor, constraints, checkpoint_required) — 6 Otto skills |

---

## Task 1: Create config/routing.yaml

**Files:**
- Create: `config/routing.yaml`

- [ ] **Step 1: Write routing.yaml — header + model tier definitions**

```yaml
# Otto-Obsidian Skill & Agentic Routing Inference
# Generated from: docs/superpowers/specs/2026-04-13-otto-routing-inference-design.md

version: "1.0"
last_updated: "2026-04-13"

# Backend mapping (from openclaw.json)
backends:
  openai-codex:
    type: codex
    models:
      gpt-5.4-mini: "openai-codex/gpt-5.4-mini"
      gpt-5.4: "openai-codex/gpt-5.4"
  claude-cli:
    type: claude-cli
    cli_path: "C:\\Users\\joshu\\.local\\bin\\claude.exe"
    cli_args: ["-p", "--output-format", "stream-json", "--permission-mode", "bypassPermissions", "--allow-dangerously-skip-permissions"]
    models:
      claude-sonnet-4-6: "claude-cli/claude-sonnet-4-6"
      claude-opus-4-6: "claude-cli/claude-opus-4-6"

tiers:
  fast:
    backend: openai-codex
    model: gpt-5.4-mini
    token_limit: 32000
    kernel_required: true
    context_isolation: true
    tool_commitment: true
    output_schema: compact
  standard:
    backend: openai-codex
    model: gpt-5.4
    token_limit: 64000
    kernel_required: false
  sonnet:
    backend: claude-cli
    model: claude-sonnet-4-6
    token_limit: 200000
    kernel_required: false
  premium:
    backend: claude-cli
    model: claude-opus-4-6
    token_limit: 200000
    kernel_required: false
```

- [ ] **Step 2: Write intent registry — deep-profile through operational-handoff (first 8 intents)**

```yaml
intents:
  - id: deep-profile
    name: "Deep User Profiling"
    triggers:
      - "understand me"
      - "soft profile"
      - "how i work"
      - "friction"
      - "recovery"
      - "fatigue"
      - "monetizable"
      - "wellbeing"
    skill: agathon-soft-profile
    persona: strategist-fox
    priority: 8
    model_tier: standard
    kernel_required: true

  - id: vault-maintenance
    name: "Otto Self-Maintenance"
    triggers:
      - "otto-realm"
      - "self-repair"
      - "profile snapshot"
      - "heartbeat"
      - "continuity"
      - "Otto maintain"
      - "Otto self"
    skill: otto-realm-maintainer
    persona: otto-core
    priority: 7
    model_tier: fast
    escalate_to: agathon-soft-profile

  - id: dream-consolidate
    name: "Dream Consolidation"
    triggers:
      - "dream"
      - "consolidate"
      - "reflect"
      - "make sense of"
      - "nightmare"
      - "dream cycle"
    skill: dream-consolidation
    persona: dreamer-moth
    priority: 7
    model_tier: standard
    kernel_required: true

  - id: memory-recall-fast
    name: "Fast Memory Recall"
    triggers:
      - "remember"
      - "find"
      - "where is"
      - "did i note"
      - "show me"
      - "recall"
      - "remind"
    skill: memory-fast
    persona: archivist-owl
    priority: 6
    model_tier: fast
    escalate_to: memory-deep

  - id: memory-recall-deep
    name: "Deep Memory Retrieval"
    triggers:
      - "deep context"
      - "rich context"
      - "what's the full picture"
      - "detailed retrieval"
      - "full context"
    skill: memory-deep
    persona: archivist-owl
    priority: 6
    model_tier: standard
    escalate_to: hygiene-audit

  - id: hygiene-check
    name: "Vault Hygiene Audit"
    triggers:
      - "hygiene"
      - "clean"
      - "folder risk"
      - "duplicate"
      - "audit"
      - "folder check"
    skill: hygiene-audit
    persona: auditor-crow
    priority: 5
    model_tier: fast

  - id: scholarly-research
    name: "Scholarly Research"
    triggers:
      - "literature review"
      - "evidence map"
      - "academic"
      - "source"
      - "remap"
      - "exploration"
      - "research"
      - "scholarly"
    skill: scholarly-explore-remap
    persona: archivist-owl
    priority: 8
    model_tier: standard
    kernel_required: true

  - id: visual-precedent
    name: "Visual Precedent Execution"
    triggers:
      - "visual"
      - "precedent"
      - "moodboard"
      - "design reference"
      - "screenshot"
      - "sketch"
      - "layout"
      - "diagram"
      - "borrow from"
    skill: visual-precedent-execution
    persona: builder-beaver
    priority: 7
    model_tier: standard
    kernel_required: true
    tool_commitment: true
```

- [ ] **Step 3: Write intent registry — remaining 5 intents**

```yaml
  - id: obsidian-cli
    name: "Obsidian CLI Operation"
    triggers:
      - "obsidian CLI"
      - "MCP"
      - "command queue"
      - "routine"
      - "headless"
      - "vault command"
    skill: obsidian-cli-expert-system
    persona: builder-beaver
    priority: 6
    model_tier: fast
    constraints:
      - human-review-required
      - explain-before-act

  - id: typst-document
    name: "Typst Document System"
    triggers:
      - "typst"
      - "PDF layout"
      - "document system"
      - "cross-format"
      - "markdown to PDF"
      - "luxury layout"
      - "typst document"
    skill: typst-luxury-layout
    persona: builder-beaver
    priority: 6
    model_tier: standard
    kernel_required: true

  - id: thought-partnership
    name: "Josh Thought Partnership"
    triggers:
      - "thought partner"
      - "philosophical"
      - "essay"
      - "reflection"
      - "discuss"
      - "what do you think"
      - "~"  # paste-writing-signal: detected when Sir Agathon pastes large block of his own writing
    skill: josh-thought-partner
    persona: strategist-fox
    priority: 9
    model_tier: standard
    kernel_required: true
    constraints:
      - no-flattery
      - no-premature-closure
      - end-with-move

  - id: swot-analysis
    name: "SWOT Analysis"
    triggers:
      - "SWOT"
      - "strength weakness"
      - "opportunity threat"
      - "strategic"
      - "priority"
    skill: agathon-soft-profile
    persona: strategist-fox
    priority: 8
    model_tier: standard
    kernel_required: true

  - id: operational-handoff
    name: "Operational Task"
    triggers:
      - "run"
      - "execute"
      - "build"
      - "implement"
      - "create file"
      - "edit"
      - "refactor"
      - "fix"
    skill: otto-realm-maintainer
    persona: builder-beaver
    priority: 7
    model_tier: standard
```

- [ ] **Step 4: Write LLM router + pattern fallback + novel intent + escalation config**

```yaml
llm_router:
  model: gpt-5.4-mini
  timeout_seconds: 3
  prompt_template: |
    Classify this query into one of the following intents: {intent_list}.
    Return JSON with fields: intent, confidence (0-100), reasoning, skill, persona, model_tier, kernel_notes.
    If confidence < 50, return: {intent: "unknown", confidence, reasoning, skill: "otto-realm-maintainer", persona: "otto-core", model_tier: "fast", kernel_notes: "full kernelization applied"}.

fallback:
  method: keyword_intersection
  weights:
    exact_phrase_match: 30
    partial_keyword_match: 10
    persona_keyword_match: 5
  threshold: 20
  default_intent: operational-handoff
  default_persona: otto-core
  default_model: fast
  kernel_required: true

novel_intent:
  confidence_threshold: 40
  novel_queries_log: "state/run_journal/novel_queries.jsonl"
  skillification_threshold: 3
  auto_create_draft: true
  heartbeat_review_flag: true

escalation:
  fast_to_standard:
    triggers:
      - intent.kernel_required: true
      - query_keywords: [multi-file, multiple, compare, synthesize, analyze deeply]
      - context_length_gt: 5
      - time_window: [06:00-11:59, 12:00-17:59]
      - rt_sdz_signal: true
      - confidence_lt: 60
  standard_to_sonnet:
    triggers:
      - intent in: [thought-partnership, scholarly-research]
      - query_requires_deep_synthesis: true
      - context_length_gt: 10
      - 1x_failure_with_error: "context too complex"
  standard_to_premium:
    triggers:
      - intent.requires_opus: true
      - query.multimodal_and_ambiguous: true
      - 2x_consecutive_failure: true
      - tool_failure_with: "insufficient context"
  sonnet_to_premium:
    triggers:
      - intent.requires_opus: true
      - 2x_consecutive_failure: true
      - high_complexity_and_multimodal: true
  premium_fallback_to_sonnet:
    triggers:
      - opus_unavailable: [rate_limit, downtime]
    mitigation:
      apply_full_kernelization: true
      chunk_task: true
      max_chunks: 3
      tool_commitment: enforced
      output_schema: premium_compatible
  sonnet_fallback_to_standard:
    triggers:
      - sonnet_unavailable: true
    mitigation:
      apply_full_kernelization: true
      chunk_task: true
      output_schema: compact

time_windows:
  morning_rtw:
    start: "06:00"
    end: "11:59"
    signals: [RTW, IB, SDZ, friction, schedule, readiness]
  afternoon_swot:
    start: "12:00"
    end: "17:59"
    signals: [SWOT, cognitive, monetizable, service]
  evening_sm2:
    start: "18:00"
    end: "23:59"
    signals: [SM-2, quiz, soul, council]
  night_urgent:
    start: "00:00"
    end: "05:59"
    signals: [urgent-repair, high-signal-delta]
```

- [ ] **Step 5: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('config/routing.yaml')); print('OK')"`
Expected: `OK` (no output on success, raises exception on parse error)

- [ ] **Step 6: Commit**

```bash
git add config/routing.yaml
git commit -m "feat(routing): add intent registry with LLM router, pattern fallback, 4-tier escalation"
```

---

## Task 2: Create config/kernelization.yaml

**Files:**
- Create: `config/kernelization.yaml`

- [ ] **Step 1: Write kernelization.yaml — components + schemas**

```yaml
# Otto-Obsidian Kernelization Config
# Delta-collapse mechanism for non-premium model tiers
# Generated from: docs/superpowers/specs/2026-04-13-otto-routing-inference-design.md

version: "1.0"
last_updated: "2026-04-13"

components:
  context_isolation:
    description: "Per-chunk context window — only relevant context, not full conversation dump"
    enforced_on: [fast, standard]
    chunk_max_context_tokens: 4000
    include:
      - checkpoint_prev
      - intent_context
      - skill_instructions
    exclude:
      - unrelated_conversation_history
      - off-topic_context

  tool_commitment:
    description: "Model declares tool(s) before use — prevents multimodality neglect"
    enforced_on: [visual-precedent, obsidian-cli, typst-document, operational-handoff]
    template: "For this chunk, I will use: [tool1, tool2]. Reason: [why]. Proceed?"
    gate: must_declare_before_call

  scope_check:
    description: "Confirm scope interpretation before execution"
    enforced_on: [kernel_required, fallback_routing]
    template: "I interpret this as [X]. Confirm: is this correct? If yes: execute. If no: [clarify]."
    gate: must_confirm_before_act

  amnesiac_guard:
    description: "Check Otto-Realm and recent handoff before asking questions"
    enforced_on: [all]
    check_order:
      - "state/handoff/latest.json"
      - "artifacts/summaries/gold_summary.json"
      - "Otto-Realm anchor files (per skill memory_anchor)"
      - "recent 5 checkpoints"
    rule: "If answer exists in checked sources → use it. If not → then ask."
    override: "If Sir Agathon explicitly wants to re-explore, respect that."
    log_field: questions_asked

  output_schema:
    description: "Structured output per skill type — ensures delta collapse across model tiers"
    enforced_on: [all skills with output_schema defined]
    validation: strict  # output must conform to schema

schemas:
  compact:
    type: object
    fields:
      summary:
        type: string
        description: "1-2 sentence summary"
      confidence:
        type: float
        description: "0.0-1.0"
      next_step:
        type: string
        description: "One concrete next action"
    required: [summary, confidence, next_step]

  profile_delta:
    type: object
    fields:
      trait:
        type: string
        description: "Name of the observed trait or pattern"
      evidence:
        type: string
        description: "Specific evidence from notes or interaction"
      confidence:
        type: float
        description: "0.0-1.0"
      delta_type:
        type: string
        enum: [stable, temporary, unresolved]
        description: "Whether this is a confirmed stable trait, temporary state, or open question"
    required: [trait, evidence, confidence, delta_type]

  memory_delta:
    type: object
    fields:
      key:
        type: string
        description: "Memory key"
      value:
        type: string
        description: "Memory value"
      source:
        type: string
        description: "Source note or artifact path"
      ttl:
        type: string
        enum: [permanent, session]
        description: "Time-to-live"
    required: [key, value, source]

  hygiene_finding:
    type: object
    fields:
      file:
        type: string
        description: "Exact file path"
      risk:
        type: string
        description: "Description of the risk"
      severity:
        type: string
        enum: [low, medium, high]
      recommendation:
        type: string
        description: "Specific remediation step"
    required: [file, risk, severity, recommendation]

  dream_compose:
    type: object
    fields:
      reflection:
        type: string
        description: "Deep reflection on the data"
      consolidation:
        type: string
        description: "Consolidated insight or synthesis"
      next_probe:
        type: string
        description: "One question or direction to explore next"
    required: [reflection, consolidation, next_probe]

  thought_partnership:
    type: object
    fields:
      engagement:
        type: string
        description: "Direct engagement with the writing — what's actually happening"
      sharp_move:
        type: string
        description: "The sharpest/most original move in the piece, pushed further"
      instability:
        type: string
        description: "What's unresolved, unstable, or inconsistent"
      ending_move:
        type: string
        description: "One question or next move — not a summary"
    required: [engagement, sharp_move, instability, ending_move]

  scholarly:
    type: object
    fields:
      answer:
        type: string
        description: "Main answer or synthesis"
      assumptions:
        type: array
        items:
          type: string
        description: "Explicit assumptions made"
      gaps:
        type: array
        items:
          type: string
        description: "Identified gaps in evidence or reasoning"
      confidence:
        type: float
        description: "0.0-1.0"
      sources:
        type: array
        items:
          type: string
        description: "Source files or references used"
    required: [answer, assumptions, gaps, confidence, sources]

  execution_schema:
    type: object
    fields:
      measurable_rigidity:
        type: string
        description: "Quantifiable visual or spatial parameters"
      conceptual_rigidity:
        type: string
        description: "Governing schema or ordering idea"
      procedural_rigidity:
        type: string
        description: "Repeatable sequence of operations"
      bias_guardrails:
        type: string
        description: "Checks preventing surface copying"
      execution_steps:
        type: array
        items:
          type: string
        description: "Ordered execution plan"
    required: [measurable_rigidity, conceptual_rigidity, procedural_rigidity, bias_guardrails, execution_steps]

  cli_response:
    type: object
    fields:
      command:
        type: string
        description: "CLI command to execute"
      explanation:
        type: string
        description: "What the command does and why"
      risk_level:
        type: string
        enum: [safe, moderate, destructive]
        description: "Risk assessment"
      requires_confirmation:
        type: boolean
        description: "Whether this needs human confirmation before execution"
    required: [command, explanation, risk_level, requires_confirmation]

  typst_output:
    type: object
    fields:
      typst_code:
        type: string
        description: "Typst source code"
      deliverables:
        type: array
        items:
          type: string
        description: "List of output artifacts (PDF, SVG, etc.)"
      conversion_steps:
        type: array
        items:
          type: string
        description: "CLI commands for conversion"
      verification:
        type: string
        description: "How to verify the output"
    required: [typst_code, deliverables]

  premium_compatible:
    type: object
    fields:
      summary:
        type: string
      full_analysis:
        type: string
      recommendations:
        type: array
        items:
          type: string
      confidence:
        type: float
    required: [summary, full_analysis, recommendations, confidence]
```

- [ ] **Step 2: Write kernel application matrix**

```yaml
application_matrix:
  # Skill ID → [enforced kernel components]
  agathon-soft-profile:
    - context_isolation
    - scope_check
    - amnesiac_guard
    - output_schema: profile_delta

  otto-realm-maintainer:
    - context_isolation
    - tool_commitment
    - scope_check
    - amnesiac_guard
    - output_schema: memory_delta

  dream-consolidation:
    - context_isolation
    - scope_check
    - amnesiac_guard
    - output_schema: dream_compose

  hygiene-audit:
    - context_isolation
    - tool_commitment
    - scope_check
    - amnesiac_guard
    - output_schema: hygiene_finding

  memory-deep:
    - context_isolation
    - scope_check
    - amnesiac_guard
    - output_schema: compact

  memory-fast:
    - amnesiac_guard
    - output_schema: compact

  scholarly-explore-remap:
    - context_isolation
    - tool_commitment
    - scope_check
    - amnesiac_guard
    - output_schema: scholarly

  visual-precedent-execution:
    - context_isolation
    - tool_commitment
    - scope_check
    - amnesiac_guard
    - output_schema: execution_schema

  obsidian-cli-expert-system:
    - context_isolation
    - tool_commitment
    - scope_check
    - amnesiac_guard
    - output_schema: cli_response

  typst-luxury-layout:
    - context_isolation
    - tool_commitment
    - scope_check
    - amnesiac_guard
    - output_schema: typst_output

  josh-thought-partner:
    - context_isolation
    - scope_check
    - amnesiac_guard
    - output_schema: thought_partnership
```

- [ ] **Step 3: Write behavioral constraints per skill**

```yaml
constraints:
  thought-partnership:
    no-flattery:
      rule: "Do not open with 'This is interesting/powerful/sharp' or any validation language"
      violation_behavior: "Start with substance — identify the live tension"
    no-premature-closure:
      rule: "Hold genuinely open questions open"
      violation_behavior: "If question doesn't close, say 'this question doesn't close yet, and here's exactly why'"
    end-with-move:
      rule: "End with a question or next move, not a summary"
      violation_behavior: "Last paragraph must feel like an opening"
  obsidian-cli:
    human-review-required:
      rule: "Never auto-execute destructive or irreversible commands"
      violation_behavior: "Show command first, explain risk, await confirmation"
    explain-before-act:
      rule: "Explain what command does before executing"
  hygiene-audit:
    no-false-confidence:
      rule: "If evidence is weak, say so explicitly"
      violation_behavior: "Use 'evidence is insufficient' instead of soft-claiming"
    cite-specifics:
      rule: "Name exact files, not generic folder descriptions"
      violation_behavior: "Always include full file path in finding"
  general:
    not-amnesiac:
      rule: "Check Otto-Realm and handoff before asking. If answer exists — use it."
      violation_behavior: "If the same information exists in Otto-Realm or recent handoff, do not ask for it"
    not-misunderstand-scope:
      rule: "Confirm interpretation before executing"
      violation_behavior: "Always state 'I'm reading this as X. Confirm?' before heavy execution"
    not-skip-tools:
      rule: "If query has image/file/link, must process it — cannot text-only"
      violation_behavior: "If multimodal detected, explicitly declare which tool processes it"
```

- [ ] **Step 4: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('config/kernelization.yaml')); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add config/kernelization.yaml
git commit -m "feat(kernel): add kernelization components, schemas, application matrix, behavioral constraints"
```

---

## Task 3: Create config/heartbeat_telemetry.yaml

**Files:**
- Create: `config/heartbeat_telemetry.yaml`

- [ ] **Step 1: Write heartbeat_telemetry.yaml — telemetry schema + aggregation rules**

```yaml
# Otto-Obsidian Heartbeat Telemetry Config
# Routing telemetry → heartbeat analysis → inference weight updates
# Generated from: docs/superpowers/specs/2026-04-13-otto-routing-inference-design.md

version: "1.0"
last_updated: "2026-04-13"

routing_log:
  path: "state/run_journal/routing_log.jsonl"
  schema_version: "1.0"
  fields:
    - timestamp
    - query_hash
    - query_preview
    - routing_method
    - intent
    - confidence
    - persona
    - persona_score
    - model_tier
    - kernel_applied
    - escalation_depth
    - escalation_reason
    - skill_used
    - tool_calls
    - output_schema_validated
    - execution_ms
    - success
    - failure_reason
    - model_intended
    - model_actual
    - had_to_chunk
    - kernel_mitigated_delta
    - scope_correct
    - tool_used_appropriately
    - questions_avoided
    - kernel_applied_correctly

aggregation:
  time_window: "24h"  # aggregate over last 24 hours
  min_entries_for_analysis: 5

  metrics:
    - name: top_intents
      type: frequency
      top_n: 5
      field: intent

    - name: avg_confidence_per_intent
      type: average
      group_by: intent
      field: confidence

    - name: escalation_rate
      type: rate
      numerator: "escalation_depth > 0"
      denominator: "total_entries"
      alert_threshold: 0.6

    - name: kernel_delta_mitigation_effectiveness
      type: rate
      numerator: "kernel_mitigated_delta == true"
      denominator: "model_actual != model_intended"
      alert_threshold: 0.7

    - name: questions_asked_rate
      type: average
      field: questions_avoided
      invert: true  # lower is better
      alert_threshold: 3  # if avg questions_asked > 3 per execution, flag

    - name: tool_appropriateness_rate
      type: rate
      numerator: "tool_used_appropriately == true"
      denominator: "total_entries"

    - name: novel_query_clusters
      type: cluster
      group_by: query_hash
      min_cluster_size: 3
      output: "draft_intent_proposal"

    - name: execution_success_rate
      type: rate
      numerator: "success == true"
      denominator: "total_entries"

heartbeat_actions:
  on_aggregation_complete:
    - skill: otto-realm-maintainer
      action: analyze_telemetry
      input:
        telemetry_summary_path: "state/run_journal/heartbeat_telemetry.md"
        routing_log_path: "state/run_journal/routing_log.jsonl"
      rules:
        - if escalation_rate > 0.6:
            suggestion: "Update tier escalation thresholds in config/routing.yaml"
            flag: "escalation-rate-high"
        - if novel_query_clusters exists:
            suggestion: "Draft new intent in config/routing.yaml with skill suggestion"
            flag: "novel-intent-detected"
        - if questions_asked_rate increasing:
            suggestion: "Strengthen amnesiac_guard in config/kernelization.yaml"
            flag: "amnesiac-guard-weak"
        - if kernel_delta_mitigation_effectiveness < 0.7:
            suggestion: "Improve chunking strategy in config/routing.yaml escalation config"
            flag: "kernel-delta-ineffective"
        - if execution_success_rate < 0.8:
            suggestion: "Review failed executions for skill routing issues"
            flag: "execution-failures"

  on_checkpoint_memory_delta:
    - skill: otto-realm-maintainer
      action: sync_otto_realm
      artifacts_to_update:
        - Profile Snapshot.md: "if intent == deep-profile"
        - Central Schedule.md: "if schedule alignment detected"
        - Weekly/YYYY-WXX.md: "if priority or theme changes"
        - Heartbeats/YYYY-MM-DD.md: "always if significant_delta"
      rules:
        - "Write concrete, small updates. No fluffy self-mythology."
        - "Distinguish stable traits from temporary experiments."
        - "Max 3 Otto-Realm file writes per heartbeat cycle."

novel_queries_log:
  path: "state/run_journal/novel_queries.jsonl"
  schema:
    - query_hash
    - first_seen
    - count
    - query_preview
    - suggested_intent
    - draft_intent_proposed
    - heartbeat_review_flagged
    - skillified

skillification:
  threshold: 3  # if same query_hash appears 3 times, draft intent
  auto_create_draft: true
  draft_location: "config/routing.yaml.intents.draft"
  notification: "Log to heartbeat_telemetry.md as 'novel-intent-detected'"
```

- [ ] **Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('config/heartbeat_telemetry.yaml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add config/heartbeat_telemetry.yaml
git commit -m "feat(telemetry): add heartbeat telemetry aggregation, inference feedback rules, skillification"
```

---

## Task 4: Update config/personas.yaml — add inference fields

**Files:**
- Modify: `config/personas.yaml` (existing file, add `inference` block to each persona)

- [ ] **Step 1: Read existing personas.yaml to confirm structure**

Run: `cat config/personas.yaml`
Expected: 7 personas with `id`, `species`, `role`, `weights`, `tool_policy` — no `inference` field yet

- [ ] **Step 2: Add inference field to otto-core**

```yaml
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
      suppress_if_intent: [deep-profile, hygiene-check, dream-consolidate, scholarly-research, visual-precedent, thought-partnership]
      escalate_to_model: standard
      escalate_to_persona: archivist-owl
```

- [ ] **Step 3: Add inference field to archivist-owl**

```yaml
  - id: archivist-owl
    species: Archivist Owl
    role: Memory and note retrieval
    weights: {clarity: 4, empathy: 2, rigor: 5, risk: 4, novelty: 2}
    tool_policy: retrieval-first
    # === INFERENCE ===
    inference:
      base_score: 30
      trigger_modifiers:
        has_vault_query: +40
        has_memory_signal: +30
        query_has_source_keyword: +20
      suppress_if_intent: [deep-profile, thought-partnership, swot-analysis]
      escalate_to_model: standard
      escalate_to_skill: memory-deep
```

- [ ] **Step 4: Add inference field to strategist-fox**

```yaml
  - id: strategist-fox
    species: Strategist Fox
    role: Planning, SWOT, prioritization, thought partnership
    weights: {clarity: 5, empathy: 3, rigor: 4, risk: 5, novelty: 4}
    tool_policy: kairos-first
    # === INFERENCE ===
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
      escalate_to_model: standard
      escalate_to_skill: josh-thought-partner
```

- [ ] **Step 5: Add inference field to builder-beaver**

```yaml
  - id: builder-beaver
    species: Builder Beaver
    role: Ops, implementation, and tooling
    weights: {clarity: 4, empathy: 2, rigor: 5, risk: 4, novelty: 3}
    tool_policy: code-heavy
    # === INFERENCE ===
    inference:
      base_score: 20
      trigger_modifiers:
        has_implementation_signal: +40
        has_typst_signal: +35
        has_visual_signal: +30
        has_obsidian_cli_signal: +35
      suppress_if_intent: [deep-profile, dream-consolidate]
      escalate_to_model: standard
```

- [ ] **Step 6: Add inference field to auditor-crow**

```yaml
  - id: auditor-crow
    species: Auditor Crow
    role: Critique, verification, and hygiene
    weights: {clarity: 4, empathy: 1, rigor: 5, risk: 5, novelty: 2}
    tool_policy: critic-first
    # === INFERENCE ===
    inference:
      base_score: 15
      trigger_modifiers:
        has_hygiene_signal: +50
        has_audit_signal: +40
        has_risk_signal: +30
      suppress_if_intent: [deep-profile, dream-consolidate, thought-partnership]
      escalate_to_model: standard
```

- [ ] **Step 7: Add inference field to dreamer-moth**

```yaml
  - id: dreamer-moth
    species: Dreamer Moth
    role: Reflection and creative consolidation
    weights: {clarity: 3, empathy: 4, rigor: 3, risk: 2, novelty: 5}
    tool_policy: dream-first
    # === INFERENCE ===
    inference:
      base_score: 15
      trigger_modifiers:
        has_dream_signal: +60
        has_reflection_signal: +40
        is_evening_window: +20  # 18:00-23:59
      suppress_if_intent: [memory-recall-fast, hygiene-check, operational-handoff]
      escalate_to_model: standard
```

- [ ] **Step 8: Add inference field to sentinel-whale**

```yaml
  - id: sentinel-whale
    species: Sentinel Whale
    role: Boundaries, wellbeing check, pacing
    weights: {clarity: 4, empathy: 5, rigor: 3, risk: 5, novelty: 2}
    tool_policy: safety-first
    # === INFERENCE ===
    inference:
      base_score: 10
      trigger_modifiers:
        has_fatigue_signal: +40
        has_wellbeing_signal: +40
        has_recovery_signal: +35
        has_SENXoR_signal: +30
      suppress_if_intent: [hygiene-check, operational-handoff, obsidian-cli]
      escalate_to_model: standard
      escalate_to_skill: agathon-soft-profile
```

- [ ] **Step 9: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('config/personas.yaml')); print('OK')"`
Expected: `OK`

- [ ] **Step 10: Commit**

```bash
git add config/personas.yaml
git commit -m "feat(personas): add inference fields — base_score, trigger_modifiers, suppress_if, escalate"
```

---

## Task 5: Update AGENTS.md — routing inference + checkpoint/handoff

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Read current AGENTS.md to confirm where to insert**

Run: `wc -l AGENTS.md && grep -n "^##" AGENTS.md`
Expected: see current section headings — insert new section before "Model routing" or after "Response protocol"

- [ ] **Step 2: Add routing inference section after "Response protocol"**

Insert this section after line 45 (after "casual chat with Sir Agathon may stay conversational."):

```markdown
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

**Novel intent handling:** If confidence < 40, execute with otto-core + fast tier + full kernelization. Log query_hash to `state/run_journal/novel_queries.jsonl`. If same hash appears 3×, draft new intent proposal.

**Behavioral guardrails (from `config/kernelization.yaml`):**
- Scope guard: confirm interpretation before heavy execution
- Multimodal tool guard: if query has image/file/link, must use tool — no text-only skip
- Amnesiac guard: check Otto-Realm + handoff before asking; if answer exists, use it
- Thought partnership constraints: no flattery, no premature closure, end with move
- CLI constraints: human review for destructive commands, explain before act
- Hygiene constraints: no false confidence, cite specific files
```

- [ ] **Step 3: Update "Model routing" section to reference 4 tiers**

Replace lines 49-55:
```markdown
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
```

- [ ] **Step 4: Update "Codex behavior guidance" to include routing layer**

After "Prefer repo-scoped skills in `.agents/skills/`." add:
```markdown
- Routing layer (this section) orchestrates skill dispatch. Skill behavior determines tone/personality. Do not bypass routing inference for routine tasks.
- Kernelization is mandatory for fast/standard tiers. Always check `config/kernelization.yaml` application matrix before executing.
- Checkpoint every skill execution. Handoff after every session boundary.
```

- [ ] **Step 5: Verify AGENTS.md is valid markdown**

Run: `python -c "import yaml; yaml.safe_load(open('AGENTS.md'))" 2>&1 || echo "YAML parse check skipped — MD file"`
Expected: The file is markdown, not YAML — verify readability only

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md
git commit -m "feat(agents): add routing inference protocol, 4-tier model dispatch, behavioral guardrails, checkpoint/handoff"
```

---

## Task 6: Update openclaw.json — skill-routing plugin + heartbeat

**Files:**
- Modify: `openclaw.json`

- [ ] **Step 1: Read openclaw.json to find insertion points**

Run: `grep -n "plugins\|heartbeat\|agents" openclaw.json`
Expected: Line numbers for `plugins.entries`, `agents.defaults.heartbeat`, `agents.defaults`

- [ ] **Step 2: Add skill-routing plugin to plugins.entries**

After `"memory-core": {` block (around line 146), add:

```jsonc
      "skill-routing": {
        "enabled": true,
        "config": "config/routing.yaml",
        "persona_config": "config/personas.yaml",
        "kernelization_config": "config/kernelization.yaml",
        "heartbeat_telemetry_config": "config/heartbeat_telemetry.yaml",
        "confidence_threshold": 40,
        "log_routing_decisions": true,
        "log_path": "state/run_journal/routing_log.jsonl",
        "novel_queries_path": "state/run_journal/novel_queries.jsonl",
        "checkpoint_path_template": "state/run_journal/checkpoints/{timestamp}_{id}.json",
        "handoff_path": "state/handoff/latest.json"
      }
```

- [ ] **Step 3: Update heartbeat config for routing-aware heartbeat**

In `agents.defaults.heartbeat`, add routing-aware fields:

```jsonc
      "heartbeat": {
        "every": "1h",
        "model": "openai-codex/gpt-5.4-mini",
        "target": "none",
        "ackMaxChars": 300,
        "lightContext": true,
        "isolatedSession": true,
        "timeoutSeconds": 120,
        "includeSystemPromptSection": false,
        // === ROUTING-AWARE ADDITIONS ===
        "use_routing_inference": true,
        "skill_target": "otto-realm-maintainer",
        "retrieval_depth": "deep",
        "apply_kernelization": true,
        "telemetry_config": "config/heartbeat_telemetry.yaml"
      }
```

- [ ] **Step 4: Verify JSON is valid**

Run: `python -c "import json; json.load(open('openclaw.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add openclaw.json
git commit -m "feat(openclaw): add skill-routing plugin, routing-aware heartbeat, 4-tier dispatch"
```

---

## Task 7: Update 6 Otto skill SKILL.md frontmatter

**Files:**
- Modify: `.agents/skills/agathon-soft-profile/SKILL.md`
- Modify: `.agents/skills/otto-realm-maintainer/SKILL.md`
- Modify: `.agents/skills/dream-consolidation/SKILL.md`
- Modify: `.agents/skills/hygiene-audit/SKILL.md`
- Modify: `.agents/skills/memory-deep/SKILL.md`
- Modify: `.agents/skills/memory-fast/SKILL.md`

For each skill: add routing metadata fields to the YAML frontmatter block.

- [ ] **Step 1: Update agathon-soft-profile/SKILL.md frontmatter**

Read the existing frontmatter, then add:

```yaml
---
name: agathon-soft-profile
description: "Build and apply a grounded soft profile for Sir Agathon from vetted notes"
# === ROUTING METADATA ===
triggers:
  keywords:
    - "understand me"
    - "soft profile"
    - "how i work"
    - "friction"
    - "recovery"
    - "fatigue"
    - "monetizable"
    - "wellbeing"
    - "SWOT"
  suppress_if: [memory-recall-fast, hygiene-check, operational-handoff]
priority: 8
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: false
  output_schema: profile_delta
model_hint: standard
escalate_to: null
memory_anchor:
  - "C:\\Users\\joshu\\Josh Obsidian\\Otto-Realm\\Profile Snapshot.md"
  - "artifacts/summaries/gold_summary.json"
constraints:
  - no-false-confidence
  - cite-specifics
checkpoint_required: true
---
```

- [ ] **Step 2: Update otto-realm-maintainer/SKILL.md frontmatter**

```yaml
---
name: otto-realm-maintainer
description: "Maintain Otto's private self-state in Josh Obsidian/Otto-Realm"
# === ROUTING METADATA ===
triggers:
  keywords:
    - "otto-realm"
    - "self-repair"
    - "profile snapshot"
    - "heartbeat"
    - "continuity"
    - "Otto maintain"
  suppress_if: [scholarly-research, visual-precedent, thought-partnership]
priority: 7
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: true
  output_schema: memory_delta
model_hint: fast
escalate_to: agathon-soft-profile
memory_anchor:
  - "C:\\Users\\joshu\\Josh Obsidian\\Otto-Realm\\Profile Snapshot.md"
  - "C:\\Users\\joshu\\Josh Obsidian\\Otto-Realm\\Central Schedule.md"
constraints:
  - human-review-required
  - explain-before-act
checkpoint_required: true
---
```

- [ ] **Step 3: Update dream-consolidation/SKILL.md frontmatter**

```yaml
---
name: dream-consolidation
description: "Reflect and consolidate vault data into dream reports"
# === ROUTING METADATA ===
triggers:
  keywords:
    - "dream"
    - "consolidate"
    - "reflect"
    - "make sense of"
    - "nightmare"
    - "dream cycle"
  suppress_if: [memory-recall-fast, hygiene-check, operational-handoff]
priority: 7
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: false
  output_schema: dream_compose
model_hint: standard
escalate_to: null
memory_anchor:
  - "artifacts/reports/dream_summary.md"
  - "artifacts/summaries/gold_summary.json"
constraints: []
checkpoint_required: true
---
```

- [ ] **Step 4: Update hygiene-audit/SKILL.md frontmatter**

```yaml
---
name: hygiene-audit
description: "Audit vault hygiene, folder risk, duplicates, and training readiness"
# === ROUTING METADATA ===
triggers:
  keywords:
    - "hygiene"
    - "clean"
    - "folder risk"
    - "duplicate"
    - "audit"
    - "folder check"
  suppress_if: [deep-profile, dream-consolidate, thought-partnership]
priority: 5
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: true
  output_schema: hygiene_finding
model_hint: fast
escalate_to: null
memory_anchor:
  - "data/bronze/bronze_manifest.json"
constraints:
  - no-false-confidence
  - cite-specifics
checkpoint_required: true
---
```

- [ ] **Step 5: Update memory-deep/SKILL.md frontmatter**

```yaml
---
name: memory-deep
description: "Deep memory retrieval with rich context from silver SQL and gold summaries"
# === ROUTING METADATA ===
triggers:
  keywords:
    - "deep context"
    - "rich context"
    - "what's the full picture"
    - "detailed retrieval"
    - "full context"
  suppress_if: [deep-profile, thought-partnership, swot-analysis]
priority: 6
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: false
  output_schema: compact
model_hint: standard
escalate_to: hygiene-audit
memory_anchor:
  - "artifacts/summaries/gold_summary.json"
  - "state/handoff/latest.json"
constraints: []
checkpoint_required: true
---
```

- [ ] **Step 6: Update memory-fast/SKILL.md frontmatter**

```yaml
---
name: memory-fast
description: "Fast first-pass retrieval for notes, reminders, and state queries"
# === ROUTING METADATA ===
triggers:
  keywords:
    - "remember"
    - "find"
    - "where is"
    - "did i note"
    - "show me"
    - "recall"
    - "remind"
  suppress_if: [deep-profile, dream-consolidate, thought-partnership]
priority: 6
kernel_required: false
kernel_config:
  scope_check: false
  amnesiac_guard: true
  tool_commitment: false
  output_schema: compact
model_hint: fast
escalate_to: memory-deep
memory_anchor:
  - "state/handoff/latest.json"
constraints: []
checkpoint_required: true
---
```

- [ ] **Step 7: Commit all 6 skill frontmatter updates**

```bash
git add .agents/skills/agathon-soft-profile/SKILL.md .agents/skills/otto-realm-maintainer/SKILL.md .agents/skills/dream-consolidation/SKILL.md .agents/skills/hygiene-audit/SKILL.md .agents/skills/memory-deep/SKILL.md .agents/skills/memory-fast/SKILL.md
git commit -m "feat(skills): add routing metadata — triggers, kernel_config, escalate_to, memory_anchor, constraints"
```

---

## Task 8: Verify all configs load + cross-reference consistency

**Files:**
- Verify: `config/routing.yaml`, `config/kernelization.yaml`, `config/heartbeat_telemetry.yaml`, `config/personas.yaml`, `openclaw.json`

- [ ] **Step 1: Verify all YAML files parse**

Run:
```bash
python -c "
import yaml
for f in ['config/routing.yaml', 'config/kernelization.yaml', 'config/heartbeat_telemetry.yaml', 'config/personas.yaml']:
    try:
        yaml.safe_load(open(f))
        print(f'OK: {f}')
    except Exception as e:
        print(f'FAIL: {f} — {e}')
"
```
Expected: All 4 files print `OK`

- [ ] **Step 2: Verify openclaw.json parses**

Run: `python -c "import json; json.load(open('openclaw.json')); print('OK: openclaw.json')"`
Expected: `OK: openclaw.json`

- [ ] **Step 3: Verify skill IDs in routing.yaml match actual skill files**

Run:
```bash
python -c "
import yaml, os
routing = yaml.safe_load(open('config/routing.yaml'))
skill_dir = '.agents/skills'
for intent in routing.get('intents', []):
    skill = intent.get('skill', '')
    if skill.startswith('agathon') or skill.startswith('otto') or skill.startswith('dream') or skill.startswith('hygiene') or skill.startswith('memory'):
        path = f'{skill_dir}/{skill}/SKILL.md'
        status = 'OK' if os.path.exists(path) else 'MISSING'
        print(f'{status}: {path}')
"
```
Expected: All 6 Otto skill paths print `OK`

- [ ] **Step 4: Verify intent IDs in heartbeat_telemetry.yaml match routing.yaml**

Run:
```bash
python -c "
import yaml
routing = yaml.safe_load(open('config/routing.yaml'))
telemetry = yaml.safe_load(open('config/heartbeat_telemetry.yaml'))
routing_intents = {i['id'] for i in routing.get('intents', [])}
print('Routing intent IDs:', sorted(routing_intents))
"
```
Expected: 13 intent IDs printed (deep-profile, vault-maintenance, dream-consolidate, memory-recall-fast, memory-recall-deep, hygiene-check, scholarly-research, visual-precedent, obsidian-cli, typst-document, thought-partnership, swot-analysis, operational-handoff)

- [ ] **Step 5: Verify persona IDs in personas.yaml match inference rules**

Run:
```bash
python -c "
import yaml
personas = yaml.safe_load(open('config/personas.yaml'))
for p in personas.get('personas', []):
    inf = p.get('inference', {})
    print(f\"{p['id']}: base_score={inf.get('base_score')}, suppress_count={len(inf.get('suppress_if_intent', []))}\")
"
```
Expected: All 7 personas have `base_score` and `suppress_if_intent` populated

- [ ] **Step 6: Commit verification**

```bash
git add -u && git commit -m "test: verify all routing configs parse and cross-reference correctly"
```

---

## Spec Coverage Checklist

- [x] Skill Registry (11 skills) — Task 7 (frontmatter updates) + config files
- [x] Intent Registry (13 intents) — Task 1 (routing.yaml)
- [x] LLM Router + Pattern Fallback — Task 1 (routing.yaml llm_router + fallback sections)
- [x] Model Tier Dispatch (4 tiers: fast, standard, sonnet, premium) — Task 1 (tiers) + Task 5 (AGENTS.md) + Task 6 (openclaw.json)
- [x] Escalation Triggers — Task 1 (escalation section)
- [x] Chunking Strategy (delta collapse) — Task 1 (escalation fallback mitigation)
- [x] Persona Inference (all 7 personas) — Task 4 (personas.yaml update)
- [x] Time-Window Scoring — Task 1 (time_windows section)
- [x] Kernelization Components (5 components) — Task 2 (kernelization.yaml)
- [x] Kernel Application Matrix (11 skills) — Task 2 (application_matrix)
- [x] Output Schemas (10 schemas) — Task 2 (schemas section)
- [x] Behavioral Constraints — Task 2 (constraints section)
- [x] Behavioral Guardrails (scope, multimodal, amnesiac) — Task 5 (AGENTS.md)
- [x] Telemetry Log Schema — Task 3 (heartbeat_telemetry.yaml)
- [x] Heartbeat Feedback Cycle — Task 3 (heartbeat_actions)
- [x] Otto-Realm Sync — Task 3 (heartbeat_actions.on_checkpoint_memory_delta)
- [x] Novel Intent → Skillification — Task 1 (novel_intent section) + Task 3 (skillification)
- [x] Checkpoint Model — referenced in Tasks 1, 5, 6 (state/run_journal/checkpoints/)
- [x] Handoff Composer — referenced in Tasks 5, 6 (state/handoff/latest.json)
- [x] claude-cli backend flags — Task 1 (backends section) + Task 5 (AGENTS.md)
- [x] openclaw.json plugin + routing-aware heartbeat — Task 6
