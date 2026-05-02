PLAN
- Verify the current handoff state and obey the newer operator boundary.
- Inspect representative notes from the two highest-risk folders.
- Draft metadata-only repair plans with concrete field scaffolds and edge-case handling.
- Surface the two human decisions in the required template.

RUN
1. Re-read the current execution brief, latest handoff state, pipeline checkpoint, needs-you template, and SOUL voice file.
2. Confirmed the newer brief no longer exposes executable FOLLOWUP_AUTO items directly and marks mutating Otto actions as blocked on the launcher/operator lane.
3. Pulled evidence from the manual review queue and inspected representative notes in:
   - Academics Agenda Database [Odd 23-24]
   - Thought Tracker 2024 - 2025 → @Daily Scratchpad Fle
4. Drafted a safe metadata-only repair plan for each folder instead of mutating notes.
5. Wrote `needs_you.md` using the exact template headings.

EVIDENCE
- Current brief changed materially from the earlier reminder payload: it now says `status: blocked on launcher/operator lane for mutating Otto actions` and `No mutating auto-action executed`.
- Pipeline state is still `ready`; checkpoint training_ready is `false`.
- Manual review queue evidence:
  - Academics Agenda Database [Odd 23-24]: 361 notes, risk=722.0, missing_frontmatter=361.
  - Thought Tracker 2024 - 2025 → @Daily Scratchpad Fle: 176 notes, risk=352.0, missing_frontmatter=176.
- Representative note evidence:
  - `Untitled 9639a95415e9451495bb08df67c9a3cb.md` contains only `# Untitled`.
  - `Presentasi 553b097c0ca24dc2aec3c34fd5f43f6b.md` has no frontmatter and begins with `# Presentasi` followed by substantive Thomist philosophy notes.
  - `PPT Sempro Fix 297bf49767a546a0b3ee2599beaab81a.md` has no frontmatter and begins with `# PPT Sempro Fix` followed by structured thesis material.
  - `Desain Pasca-Cybernetics dan Kritisisme ...md` has no frontmatter and begins with a usable H1 title.
  - `Design, Meta-Design ...md` has no frontmatter and begins with a usable H1 title.
- Metadata repair plan — Academics Agenda Database [Odd 23-24]:
  - Scope: all 361 markdown notes in the folder; metadata-only; no body edits.
  - Base frontmatter scaffold:
    ```yaml
    ---
    title: <derived from first H1 or folder name>
    source: notion-export
    area: academics
    collection: academics-agenda-database-odd-23-24
    note_type: agenda
    status: imported
    tags:
      - academics
      - notion-import
      - needs-review
    ---
    ```
  - Derivation rules:
    1. If first H1 is non-empty and not `Untitled`, use it as `title`.
    2. If first H1 is `Untitled`, derive `title` from the immediate parent folder name when that folder is human-readable.
    3. If both H1 and parent are weak/hashed, keep `title: Untitled` and add `tags: [needs-title-review]`.
    4. Preserve the existing body exactly; no H1 rewrites in this pass.
  - Edge cases to sample before batching:
    - single-line notes (`# Untitled` only)
    - bracketed context folders like `[Presentasi]`
    - files whose visible title duplicates a parent folder title
  - Batch strategy: operate in chunks of 50 notes, stop if any non-metadata mutation is required.
- Metadata repair plan — Thought Tracker 2024 - 2025 → @Daily Scratchpad Fle:
  - Scope: all 176 markdown notes in the folder; metadata-only; no body edits.
  - Base frontmatter scaffold:
    ```yaml
    ---
    title: <derived from first H1 or filename stem>
    source: notion-export
    area: legacy-database
    collection: thought-tracker-2024-2025
    note_type: scratchpad
    status: imported
    tags:
      - legacy
      - thought-tracker
      - notion-import
      - needs-review
    ---
    ```
  - Derivation rules:
    1. Prefer first H1 when it is specific (`PPT Sempro Fix`, `Desain Pasca-Cybernetics dan Kritisisme`, `Design, Meta-Design`).
    2. If H1 is blank, placeholder, or malformed, fall back to filename stem with hash suffix removed only in metadata, not file path.
    3. Add `tags: [needs-structure-review]` for notes that mix charter/outline/draft fragments in one body.
    4. Preserve all inline links and markdown body text exactly.
  - Edge cases to sample before batching:
    - bilingual notes
    - heavily outline-based research notes
    - near-duplicate titles across sibling folders
  - Batch strategy: operate in chunks of 50 notes, stop if frontmatter insertion reveals body-structure ambiguity that needs human taxonomy.
- Blocking evidence:
  - Attempted filesystem census via Python was denied by approval timeout, so the plan relies on queue statistics plus direct representative-note inspection instead of a fresh full-folder scan.

VERDICT
- Completed the bounded executor pass that the current brief allows: evidence gathered, two metadata-only repair plans drafted, and human decisions surfaced in `needs_you.md`.
- Did not mutate vault notes because the live brief now explicitly routes mutating Otto actions through the launcher/operator lane.