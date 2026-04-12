---
name: dream-consolidation
description: Nightly memory consolidation that compresses run state, KAIROS insights, and recent retrieval findings.
---

# Dream Consolidation

## Trigger

Use:
- nightly
- after a long sequence of runs
- before a new planning cycle
- when handoff files become noisy

## Steps

1. Run:

   ```bash
   python scripts/manage/run_dream.py --once
   ```

2. Read:
   - `artifacts/reports/dream_summary.md`
   - `state/handoff/latest.json`

3. Extract:
   - stable facts
   - unresolved questions
   - repeated operational failures
   - good candidates for AGENTS updates

## Rules

- Preserve uncertainty.
- Remove contradictions instead of stacking them.
- Keep the dream output shorter than the combined raw logs it summarizes.
