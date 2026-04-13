---
name: memory-fast
description: First-pass retrieval for notes, reminders, SWOT signals, and recent state. Use this before any deep scan or reindex.
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

# Memory Fast

## Trigger

Use when the user asks:
- what they were doing recently
- what reminders are pending
- what notes or research relate to a topic
- what Otto already knows from current state

## Steps

1. Run the fast local retrieval command:

   ```bash
   python -m otto.cli retrieve --mode fast --query "<user query>"
   ```

2. If the result contains `enough_evidence: true`, answer from that package.
3. If the result shows `needs_deepening: true`, switch to the `$memory-deep` skill or ask a deep agent to continue.
4. Cite:
   - folder risk
   - note hits
   - reminder hits
   - state hits
   - missing evidence

## Rules

- Never dump raw note bodies if the summary package is enough.
- Never trigger full vault reindex from this skill.
- Keep answers compact and grounded.
