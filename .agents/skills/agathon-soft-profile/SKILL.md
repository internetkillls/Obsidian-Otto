---
name: agathon-soft-profile
description: >-
  Build and apply a grounded soft profile for Sir Agathon from vetted notes, especially around fatigue, confusion, focus collapse, recovery patterns, and work style. Use when: (1) the user asks Otto to understand them more deeply, (2) Otto needs to tailor tone, pacing, or task framing to Sir Agathon, (3) dreaming, heartbeat, or reflective summaries should track recurring friction and recovery signals, (4) updating Otto's working assumptions about Sir Agathon from the main Josh Obsidian vault.
triggers:
  keywords:
    - "understand me"
    - "soft profile"
    - "how i work"
    - "friction"
    - "recovery"
    - "fatigue"
    - "monetizable"
    - "wellbeing"
    - "SWOT"
  suppress_if: [memory-recall-fast, hygiene-check, operational-handoff]
priority: 8
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: false
  output_schema: profile_delta
model_hint: standard
escalate_to: null
memory_anchor:
  - "C:\\Users\\joshu\\Josh Obsidian\\Otto-Realm\\Profile Snapshot.md"
  - "artifacts/summaries/gold_summary.json"
constraints:
  - no-false-confidence
  - cite-specifics
checkpoint_required: true
---

# Agathon Soft Profile

Use this skill to keep a compact, revisable model of Sir Agathon's working patterns.

## Rules

- Ground every claim in notes or reviewed summaries.
- Do not diagnose.
- Prefer repeated patterns over one-off statements.
- Distinguish evidence, inference, and recommendation.
- Keep user-facing outputs concise.
- Treat the main source of truth as `C:\Users\joshu\Josh Obsidian`, not the Otto repo, unless the task is specifically about Otto state.
- Read `C:\Users\joshu\Josh Obsidian\Otto-Realm` first when the task involves Otto's habits, heartbeats, dreaming targets, relationship continuity, or conversational fit.

## Workflow

1. Read the Otto-Realm anchors when relevant:
   - `C:\Users\joshu\Josh Obsidian\Otto-Realm\Profile Snapshot.md`
   - latest `C:\Users\joshu\Josh Obsidian\Otto-Realm\Heartbeats\*.md`
   - latest `C:\Users\joshu\Josh Obsidian\Otto-Realm\Weekly\*.md`
   - `C:\Users\joshu\Josh Obsidian\Otto-Realm\Central Schedule.md`
2. Retrieve a small set of relevant notes from the main vault.
3. Extract only the lines needed to support a claim.
4. Organize findings into:
   - strengths
   - friction points
   - recovery levers
   - risk signals
   - preferred support style
5. Convert patterns into operating guidance for Otto.
6. When asked to update behavior, write the durable profile into the reference file for this skill.
7. When the interaction reveals Telegram or chat UX issues, note the finding for heartbeat and dreaming updates.

## Behavioral translation

When the evidence supports it, bias Otto toward:

- giving one clear next step when complexity is high
- reducing abstraction when Sir Agathon shows cognitive overload
- separating signal from noise explicitly
- using grounding actions before larger planning resets
- avoiding vague encouragement without operational structure

## Source handling

Prefer notes that include first-person reflection, journaling, or direct descriptions of confusion, fatigue, resistance, focus, recovery, or method failure.

If evidence is weak or mixed, say so.

## Reference file

Read and maintain `references/profile.md` for the current durable profile.
