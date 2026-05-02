---
name: obsidian-metadata-enrichment
description: Fetch and normalize frontmatter, tags, and wikilinks for Obsidian notes using WikiDB or Obsidian CLI, especially before review, repair, or Gold-related work.
---

# Obsidian Metadata Enrichment

Use this skill when note metadata needs to be fetched, normalized, or repaired before retrieval, review, or Gold scoring. The goal is to turn scattered frontmatter, tags, wikilinks, and source-specific entity metadata into a clean, lossless record that downstream systems can trust.

## When To Use

- A note is missing frontmatter, tags, or wikilinks.
- Metadata exists but is inconsistent across sources.
- You need to enrich notes from WikiDB or Obsidian CLI before a scoped review.
- You want to prepare notes for hygiene, retrieval, or Gold calibration without inflating meaning.
- You need a predictable command path for metadata work via `metadata-enrich.bat` or `otto.bat metadata-enrich`.

## Modes

- `review`:
  - read-only fetch + normalize
  - preferred default for operator checks
- `apply`:
  - write-capable normalization of safe frontmatter fields
  - must stay confirmation-gated
- `entity`:
  - source-specific enrichment from Wikidata
  - only when a real external entity target exists
- `verify`:
  - re-scan after apply and compare before/after state

## Workflow

1. Identify the source priority:
   - prefer WikiDB or indexed metadata when available
   - fall back to Obsidian CLI or other structured vault access
   - use raw markdown only when the structured sources are insufficient
   - use the configured backend map so `Metadata Menu` stays the core write path, `MetaEdit` is fallback, and `Wikidata Importer` is source-specific only
2. Fetch the current note record:
   - path
   - title
   - frontmatter text or parsed frontmatter
   - tags
   - wikilinks
   - body evidence if needed to disambiguate metadata
3. Normalize the fields:
   - keep frontmatter lossless; do not invent values
   - deduplicate tags
   - canonicalize wikilinks to consistent target text
   - preserve aliases when they are explicit in the source
4. Reconcile conflicts:
   - prefer body-backed evidence over frontmatter-only hints when they disagree
   - mark unresolved metadata instead of guessing
   - separate confirmed enrichment from speculative suggestions
5. Output a compact enrichment record or patch plan:
   - what changed
   - what was already correct
   - what remains unresolved

## Command Flow

- `main.bat` or `otto.bat metadata-enrich` routes into `scripts/manage/run_launcher.py --once metadata-enrich`
- launcher action `metadata-enrich` runs `scripts/manage/run_metadata_enrichment.py`
- thin shim: `scripts/shell/metadata-enrich.bat`
- backend labels and command names live in `config/metadata_enrichment.yaml`, not hardcoded in the runner
- optional `--dispatch-command` opens the matching Advanced URI command for a single note when you want Obsidian to execute the plugin command directly

## Guardrails

- Do not treat metadata prettification as Gold by itself.
- Do not fabricate tags or wikilinks from weak context.
- Do not overwrite human-authored frontmatter without a clear source of truth.
- Prefer small, reversible edits over broad rewrites.
- Apply-capable writes should stay confirmation-gated.

## Reference

See [normalization rules](references/normalization.md) for canonical field handling and merge order.
