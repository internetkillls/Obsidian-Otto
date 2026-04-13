---
name: scholarly-explore-remap
description: >-
  Explore, map, and synthesize scholarly or source-grounded knowledge from the vault. Use when: (1) the user asks for a literature review, evidence map, or academic synthesis, (2) a concept needs remapping or comparative analysis across sources, (3) research or exploration of a topic requires grounding in existing notes rather than web search, (4) a scholarly writing project needs source organization or argument structure.
triggers:
  keywords:
    - "literature review"
    - "evidence map"
    - "academic"
    - "source"
    - "remap"
    - "exploration"
    - "research"
    - "scholarly"
    - "comparative synthesis"
    - "what sources do i have"
    - "map the literature"
  suppress_if: [memory-recall-fast, hygiene-check, operational-handoff]
priority: 8
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: true
  output_schema: scholarly
model_hint: standard
escalate_to: null
memory_anchor:
  - "artifacts/summaries/gold_summary.json"
constraints:
  - source-grounded
  - no-speculation-without-flag
  - cite-exact-paths
checkpoint_required: true
---

# Scholarly Explore Remap

Use this skill to explore, synthesize, and remap source-grounded knowledge from the Obsidian vault.

## Rules

- Only use information from vault notes. Do not fabricate sources.
- Distinguish between direct quotation, paraphrase, and inference.
- When evidence is absent or thin, say so explicitly rather than speculating.
- Cite exact file paths for every source claim.
- If the topic spans multiple vaults (main Josh Obsidian + Otto-Realm), note both sources.
- Output by default is prose synthesis. Output schema only on explicit request.

## Workflow

1. **Scope confirm** — "I'm reading this as a [literature review / evidence map / comparative synthesis / exploration]. Is that right?"
2. **Source gathering** — Query the vault for relevant notes using memory skills or direct glob/grep.
3. **Evidence mapping** — Build a map of: what claims exist, where they come from, how they relate.
4. **Gap identification** — Note where evidence is thin, contradictory, or absent.
5. **Synthesis** — Write a coherent narrative or structured argument from the mapped evidence.
6. **Deliver** — Return prose by default. Return schema (assumptions, gaps, confidence, sources) only if requested.

## Source types and how to handle them

- **Direct quotes** — Use when the note itself is a primary source or reflection.
- **Paraphrase** — Use when summarizing an argument or claim from a note.
- **Inference** — Only when the claim is strongly implied. Flag as `[inference]`.
- **Absence** — Explicitly state when no relevant notes were found.

## Scope boundaries

- Do not expand beyond the user's stated topic unless a relevant connection is surfaced organically.
- Do not generate bibliography entries for sources you did not actually read.
- Do not apply frameworks or interpretations not grounded in the source notes.

## Output

Prose by default. Structured output (schema: scholarly) only when Otto or the user explicitly requests it.

If no relevant notes exist: "I found no notes in the vault that directly address [topic]. Would you like me to search more broadly or start fresh notes?"
