# Normalization Rules

## Source order

1. WikiDB or other indexed metadata
2. Obsidian CLI or structured vault command output
3. raw markdown body

## Field handling

- `frontmatter`
  - preserve original meaning
  - normalize parsing, not intent
  - keep unresolved keys instead of dropping them
- `tags`
  - deduplicate
  - strip leading `#`
  - preserve namespaces when meaningful
  - do not add tags unless the source supports them
- `wikilinks`
  - deduplicate by normalized target
  - preserve aliases explicitly
  - do not convert plain mentions into links unless the source already does

## Merge rules

- If structured metadata and body evidence conflict, flag the conflict.
- If the body is silent, keep the existing metadata unchanged.
- If enrichment is incomplete, return a partial record instead of guessing.

## Output shape

- `note_path`
- `source`
- `frontmatter`
- `tags`
- `wikilinks`
- `conflicts`
- `unresolved`
- `recommended_patch`
