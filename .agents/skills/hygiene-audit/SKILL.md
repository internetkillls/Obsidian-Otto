---
name: hygiene-audit
description: Audit folder hygiene, frontmatter quality, duplicate patterns, and Gold readiness for an Obsidian vault.
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
