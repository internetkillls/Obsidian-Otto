---
name: visual-precedent-execution
description: >-
  Execute visual design or spatial tasks by transferring method, not style, from precedents in the vault. Use when: (1) the user provides or references a visual screenshot, moodboard, diagram, or design reference, (2) a layout, facade, sketch, or spatial concept needs to be realized, (3) a document or presentation needs a visual redesign based on examples, (4) the user asks to "borrow from" or "reference" a visual pattern.
triggers:
  keywords:
    - "visual"
    - "precedent"
    - "moodboard"
    - "design reference"
    - "screenshot"
    - "sketch"
    - "layout"
    - "facade"
    - "diagram"
    - "borrow from"
    - "visual reference"
    - "design precedent"
  suppress_if: [deep-profile, dream-consolidate, memory-recall-fast]
priority: 7
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: true
  output_schema: execution_schema
model_hint: standard
escalate_to: null
memory_anchor:
  - "artifacts/summaries/gold_summary.json"
constraints:
  - method-not-style
  - bias-guardrails
  - measurable-parameters
  - cite-precedent-source
checkpoint_required: true
---

# Visual Precedent Execution

Use this skill to execute visual design tasks by extracting method from precedents — not by imitating style.

## Rules

- Transfer the **method** (how something was achieved), not the **style** (how it looks).
- Bias guardrails: surface copying is prohibited. Require conceptual or procedural rigidity.
- All visual decisions must have measurable or explicitly stated parameters.
- Cite the precedent source for every design decision.
- If no precedent exists in the vault, say so and ask whether to proceed from first principles.

## Workflow

1. **Scope confirm** — "I'm reading this as: [layout X / diagram Y / visual pattern Z]. Is that right?"
2. **Precedent retrieval** — Find relevant visual references in the vault.
3. **Method extraction** — Reverse-engineer the governing method from precedents:
   - Measurable rigidity: what exact parameters (spacing, scale, color values, grid units)?
   - Conceptual rigidity: what ordering idea or schema governs the layout?
   - Procedural rigidity: what sequence of operations produces this?
4. **Bias guardrails check** — "Am I copying surface appearance, or extracting the governing method?"
5. **Execution plan** — Write execution steps that produce the outcome, not the look.
6. **Execute** — Use appropriate tools (draw, render, code, or instruct).
7. **Verify** — Check that the output matches the method, not the surface.

## What "method not style" means in practice

| Surface (do not copy) | Method (extract and apply) |
|---|---|
| "It uses a dark background" | Color contrast ratio ≥ 4.5:1, background luminance ≤ 0.4 |
| "It has a sidebar layout" | 2-column grid, 70/30 split, sidebar fixed-width 240px |
| "The diagram is circular" | Radial arrangement with centroid anchor, proportional spacing |

## Output schema: execution_schema

Must include all five fields:
- `measurable_rigidity`: Quantifiable visual or spatial parameters
- `conceptual_rigidity`: Governing schema or ordering idea
- `procedural_rigidity`: Repeatable sequence of operations
- `bias_guardrails`: Checks preventing surface copying
- `execution_steps`: Ordered execution plan

## Tool commitment

Before executing, declare which tool(s) will be used and why.
