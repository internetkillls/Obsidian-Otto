---
name: typst-luxury-layout
description: >-
  Design and produce luxury-layout documents using Typst, with cross-format support (markdown to PDF, SVG, LaTeX). Use when: (1) the user wants a document with typographic elegance, precise spacing, or luxury feel, (2) markdown needs to be converted to a polished PDF, (3) a document system with consistent layout across multiple outputs is needed, (4) the user asks about Typst, LaTeX, SVG, or cross-format document production.
triggers:
  keywords:
    - "typst"
    - "PDF layout"
    - "document system"
    - "cross-format"
    - "markdown to PDF"
    - "luxury layout"
    - "typst document"
    - "latex"
    - "mermaid"
    - "SVG"
    - "polished document"
    - "typographic"
  suppress_if: [deep-profile, dream-consolidate, memory-recall-fast]
priority: 6
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: true
  output_schema: typst_output
model_hint: standard
escalate_to: null
memory_anchor:
  - "artifacts/summaries/gold_summary.json"
constraints:
  - source-grounded
  - cite-precedent-source
  - no-fabricated-content
checkpoint_required: true
---

# Typst Luxury Layout

Use this skill to design and produce luxury-layout documents using Typst and cross-format tools.

## Rules

- Source-grounded: content comes from vault notes. Do not fabricate content.
- Cite the precedent source for every design decision.
- All typographic decisions must have explicit parameters (font size, spacing, margins, alignment).
- If multi-step, use coassist-kernel orchestration across steps.
- Verify output before declaring complete.

## Workflow

1. **Scope confirm** — "I read this as: a [single document / multi-page report / cross-format set]. Is that right?"
2. **Content gathering** — Pull relevant content from vault notes.
3. **Layout design** — Determine typographic parameters:
   - Font families and sizes
   - Margins and spacing
   - Grid or column structure
   - Special elements (headers, footers, page numbers)
4. **Schema design** — Determine the output format(s): PDF, SVG, LaTeX, or combination.
5. **Typst code generation** — Write Typst source code implementing the design.
6. **Conversion** — Run the appropriate conversion commands.
7. **Verification** — Open or inspect the output to confirm fidelity.
8. **Deliver** — Report the artifact paths and how to use them.

## Output schema: typst_output

Must include all fields:
- `typst_code`: Complete Typst source code
- `deliverables`: List of output artifacts (PDF, SVG, etc.)
- `conversion_steps`: CLI commands used for conversion
- `verification`: How the output was verified

## Layout principles

- Luxury ≠ complexity. A clean grid with precise spacing is more luxurious than busy decoration.
- Consistent vertical rhythm: use baseline grids.
- Hierarchy through size and weight, not color variety.
- Whitespace is a design element, not wasted space.

## Tool commitment

Before executing, declare which tools will be used (typst CLI, pandoc, inkscape, etc.) and why.
