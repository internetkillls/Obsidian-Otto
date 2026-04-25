---
name: memory-deep
description: Deep retrieval and scoped reindex skill for hard questions, weak evidence, or investigative inquiries.
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

# Memory Deep

## Trigger

Use when:
- the fast package has weak evidence
- the user asks for deeper inquiry
- the task needs scoped reindex or deeper folder analysis

## Steps

1. Check status:

   ```bash
   python scripts/manage/status_report.py --json
   ```

2. Run deep retrieval:

   ```bash
   python -m otto.cli retrieve --mode deep --query "<user query>"
   ```

3. If still weak, run a scoped pipeline refresh:

   ```bash
   python scripts/manage/run_pipeline.py --scope "<folder>" --full
   ```

4. Summarize:
   - evidence found
   - evidence still missing
   - whether another scope is needed
5. If the result will feed dreaming, OpenClaw, or Otto-Realm writeback, inspect the current Morpheus bridge:

   ```bash
   python -m otto.cli morpheus-bridge
   ```

## Rules

- Prefer scoped refresh over full-vault rebuild.
- Return uncertainty explicitly.
- Keep the answer smaller than the combined evidence package.
- Treat MORPHEUS outputs as investigation seeds that need markdown-body and semantic verification before promotion.
- Reject raw `memory/.dreams/session-corpus` or operational noise as proof, even if it appears in a generated artifact.
