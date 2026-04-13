---
name: hygiene-audit
description: Audit folder hygiene, frontmatter quality, duplicate patterns, and Gold readiness for an Obsidian vault.
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

# Hygiene Audit

## Trigger

Use when the user asks to:
- audit a folder
- rank folder risk
- decide what to reorganize
- determine if data is good enough for Gold or training export

## Steps

1. Check current pipeline state:

   ```bash
   python scripts/manage/status_report.py --json
   ```

2. If needed, run a scoped pipeline:

   ```bash
   python scripts/manage/run_pipeline.py --scope "<folder>" --full
   ```

3. Read the Gold summary and audit reports.

4. Return:
   - severity
   - affected folders
   - representative files
   - recommended next action
