# Graph Shadow Demotion Apply — Design Specification

Date: 2026-04-25 | Status: Implemented and Bounded | Scope: Vault hygiene / node deflation

## 1. Purpose

This spec defines the current bounded demotion workflow for graph-node inflation in the Obsidian vault, especially for `ALLO-*`, `TO-*`, and `LACK-*` overproduction.

The implementation goal is not bulk graph rewriting. The goal is:

- detect inflated node-driving metadata
- propose safer replacements
- preview exact rewrites note-by-note
- optionally apply a bounded subset with audit artifacts

This keeps semantic retrieval, graph shaping, and human review aligned.

## 2. Current Surfaces

The graph rollup audit now exposes four related operator surfaces:

1. `shadow graph decisions`
   - machine-readable node-deflation audit
2. `shadow family review`
   - grouped family review for `ALLO-*`, `TO-*`, `LACK-*`
3. `demotion plan`
   - exact per-note frontmatter/tag rewrite plan
4. `ALLO hotspots`
   - payoff-ordered markdown report for allocation-family cleanup

Primary script:

- [scripts/c4_graph_rollup_audit.py](/C:/Users/joshu/Obsidian-Otto/scripts/c4_graph_rollup_audit.py)

Primary artifacts:

- [graph_shape_audit.json](/C:/Users/joshu/Obsidian-Otto/state/run_journal/graph_shape_audit.json)
- [graph_shadow_decisions.json](/C:/Users/joshu/Obsidian-Otto/state/run_journal/graph_shadow_decisions.json)
- [graph_shadow_review.md](/C:/Users/joshu/Obsidian-Otto/state/run_journal/graph_shadow_review.md)
- [graph_demotion_plan.json](/C:/Users/joshu/Obsidian-Otto/state/run_journal/graph_demotion_plan.json)
- [graph_demotion_plan.md](/C:/Users/joshu/Obsidian-Otto/state/run_journal/graph_demotion_plan.md)
- [graph_allo_hotspots.md](/C:/Users/joshu/Obsidian-Otto/state/run_journal/graph_allo_hotspots.md)

## 3. Behavioral Contract

### 3.1 Dry-run mode

`--apply-demotion-plan --dry-run`

This mode:

- computes exact note-level rewrites
- prints preview markdown to stdout
- writes demotion-plan artifacts
- does not mutate any vault notes

### 3.2 Apply mode

`--apply-demotion-plan`

This mode:

- reuses the same plan builder as dry-run
- rewrites note frontmatter in-place
- preserves note body content
- is bounded by `--max-demotion-writes`
- records `applied_count` and `skipped_count`

### 3.3 ALLO hotspot report

The `ALLO-*` hotspot report is separate from the broader family review and is ordered by highest cleanup payoff first.

It is meant to answer:

- which family is creating the most graph noise right now
- whether the dominant action is `demote frontmatter`, `convert to tag`, `merge to family`, or `ignore route node`
- which specific notes exemplify the problem

## 4. Rewrite Semantics

The current rewrite rules are intentionally conservative.

### 4.1 Demote frontmatter

Long, sentence-like `allocation` or `orientation` values are moved into:

- `allocation_detail`
- `orientation_detail`

The canonical top-level field is removed from node-driving status.

### 4.2 Convert to tag

Small, local, tactical values can be converted into structured tags such as:

- `allocation/<slug>`
- `orientation/<slug>`
- `scarcity/<slug>`

### 4.3 Merge to family

Low-reuse values may be merged upward toward a family-level target while preserving the original value as a weaker hint via tags or detail fields.

### 4.4 Ignore route node

Route/index-like metadata is treated as non-node-driving and downgraded away from graph pressure.

## 5. Latest Session Delta

### 5.1 Delta from preview-only implementation

Before this session:

- demotion planning could preview exact rewrites
- `ALLO-*` hotspot markdown existed
- apply mode was intentionally blocked

After this session:

- bounded apply mode is live
- `--max-demotion-writes` limits real note mutation
- apply results are now recorded as:
  - `demotion_applied_count`
  - `demotion_skipped_count`
- demotion artifacts now distinguish `mode: dry-run` vs `mode: apply`

### 5.2 Latest real-vault execution

Real bounded apply was executed against the vault with:

```powershell
python scripts/c4_graph_rollup_audit.py --vault "C:\Users\joshu\Josh Obsidian" --scope full --apply-demotion-plan --max-demotion-writes 12
```

Observed result:

- `note_count_batch = 20`
- `note_count_total = 589`
- `shadow_demotion_plan_count = 49`
- `shadow_demotion_applied_count = 12`
- `shadow_demotion_skipped_count = 37`

The first bounded apply therefore mutated the vault, but only within the explicit limit.

## 6. Guardrails

This implementation is still intentionally bounded:

- no bulk full-vault rewrite in one pass
- no destructive graph-anchor deletion
- no automatic entity-anchor cleanup yet
- no graph optimization pass yet
- no speculative schema invention beyond current detail/tag seam

Human review remains the control surface.

## 7. Recommended Operator Flow

1. Run dry-run first for the next batch.
2. Inspect:
   - demotion plan markdown
   - ALLO hotspot markdown
3. Apply bounded writes with a small cap.
4. Reinspect the changed notes and graph readability.
5. Repeat by batch until inflation pressure drops.

## 8. Next Natural Extensions

- add family-scoped apply, e.g. `ALLO`-only apply
- add stronger style-preserving frontmatter serialization
- add rollback packet for bounded apply batches
- add post-apply graph delta metrics to quantify readability improvement
