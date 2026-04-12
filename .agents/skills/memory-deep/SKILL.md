---
name: memory-deep
description: Deep retrieval and scoped reindex skill for hard questions, weak evidence, or investigative inquiries.
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

## Rules

- Prefer scoped refresh over full-vault rebuild.
- Return uncertainty explicitly.
- Keep the answer smaller than the combined evidence package.
