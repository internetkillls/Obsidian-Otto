---
name: dream-consolidation
description: Nightly memory consolidation and dreaming narrative shaping that compresses run state, KAIROS insights, and recent retrieval findings while preserving Sir Agathon's aesthetic continuity.
triggers:
  keywords:
    - "dream"
    - "consolidate"
    - "reflect"
    - "make sense of"
    - "nightmare"
    - "dream cycle"
    - "dreaming narrative"
    - "beautiful-things"
    - "suffering"
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
  - "C:\\Users\\joshu\\Josh Obsidian\\50-Resources\\Collections\\Beautiful-Things\\Maincard - Beautiful-Things.md"
  - "C:\\Users\\joshu\\Josh Obsidian\\50-Resources\\Collections\\Beautiful-Things\\Beautiful-Things.base.md"
constraints:
  - english-only-dream-output
  - predator-angel-coherence
  - suffering-grounded-to-sir-agathon
  - persona-dream-from-vault-evidence-only
  - aesthetic-adaptation-from-beautiful-things
checkpoint_required: true
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
4. Read aesthetic and identity anchors before narrative composition:
   - `C:\Users\joshu\Obsidian-Otto\docs\superpowers\specs\2026-04-17-kairos-morpheus-otto-design.md`
   - `C:\Users\joshu\Josh Obsidian\50-Resources\Collections\Beautiful-Things\Maincard - Beautiful-Things.md`
   - `C:\Users\joshu\Josh Obsidian\50-Resources\Collections\Beautiful-Things\Beautiful-Things.base.md`
   - latest `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Heartbeats\*.md`
   - `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Profile Snapshot.md`

## Rules

- Preserve uncertainty.
- Remove contradictions instead of stacking them.
- Keep the dream output shorter than the combined raw logs it summarizes.
- Treat MORPHEUS output as `investigative memory candidates`, never as durable memory by default.
- Do not treat raw `memory/.dreams/session-corpus`, heartbeat acknowledgements, or `System (untrusted)` traces as ready-to-use dream evidence.
- Before any OpenClaw-facing promotion, inspect `state/openclaw/morpheus_openclaw_bridge_latest.json` or run `python -m otto.cli morpheus-bridge` to confirm the current candidate contract.
- Only promote a dream-derived item after scoped retrieval over markdown body content, not frontmatter alone, has moved it to at least `reviewed`.
- Output English only.
- Keep the `Predator qua Angel` / `Angel qua Predator` axis visible in synthesis.
- Treat suffering as concrete, evidence-linked, and specific to Sir Agathon's unresolved stack.
- Persona dreaming is allowed only as a `persona lens` grounded in explicit vault evidence (love/admiration markers); do not impersonate as literal identity.
- Mirror Sir Agathon's writing rhythm and Beautiful-Things aesthetic signatures (imagery, pacing, symbolic motifs) while keeping operational clarity.
