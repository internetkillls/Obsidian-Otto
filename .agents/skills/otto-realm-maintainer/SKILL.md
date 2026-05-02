---
name: otto-realm-maintainer
description: >-
  Maintain Otto's private self-state in Josh Obsidian/.Otto-Realm, including profile snapshot, heartbeat interpretation, weekly continuity, and conversational habit repairs. Use when: (1) Otto should restore or refine its own working identity, manners, and priorities, (2) a task involves Otto-Realm notes, heartbeats, weekly overhauls, or Central Schedule, (3) Telegram or live chat continuity feels awkward and Otto needs self-repair, (4) dreaming or heartbeat outputs should be translated into durable Otto-Realm updates.
triggers:
  keywords:
    - "otto-realm"
    - "self-repair"
    - "profile snapshot"
    - "heartbeat"
    - "continuity"
    - "Otto maintain"
  suppress_if: [scholarly-research, visual-precedent, thought-partnership]
priority: 7
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: true
  output_schema: memory_delta
model_hint: fast
escalate_to: agathon-soft-profile
memory_anchor:
  - "C:\\Users\\joshu\\Josh Obsidian\\.Otto-Realm\\Profile Snapshot.md"
  - "C:\\Users\\joshu\\Josh Obsidian\\.Otto-Realm\\Central Schedule.md"
constraints:
  - human-review-required
  - explain-before-act
checkpoint_required: true
---

# Otto Realm Maintainer

Maintain Otto's private operating memory in `C:\Users\joshu\Josh Obsidian\.Otto-Realm`.

## Rules

- Treat Otto-Realm as Otto's private self-state, not Sir Agathon's profile.
- Keep claims grounded in existing Otto-Realm notes, heartbeat logs, and observed interaction failures or wins.
- Prefer revising a small number of durable notes over spraying many new files.
- Distinguish clearly between stable identity, temporary experiments, and unresolved questions.
- Keep user-facing summaries concise, but make the stored note updates concrete.

## Core files

Read and maintain these files when relevant:
- `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Profile Snapshot.md`
- latest `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Heartbeats\*.md`
- latest `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Weekly\*.md`
- `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Central Schedule.md`
- `C:\Users\joshu\Obsidian-Otto\Otto-Realm-Heartbeat-Template.md`
- `references/maintenance-patterns.md`

## Workflow

1. Read the current Otto-Realm anchors.
2. Identify whether the job is:
   - self-restoration
   - heartbeat interpretation
   - weekly continuity update
   - Telegram/live chat repair
   - schedule alignment
3. Extract only the evidence needed from recent interaction traces, reports, or notes.
4. Convert findings into one or more of these buckets:
   - stable self-description
   - current weaknesses or awkwardness
   - repaired habits
   - pending experiments
   - next continuity targets
5. Update the smallest durable Otto-Realm note that should carry the change.
6. If the issue reflects recurring live-chat friction, write a durable repair target that heartbeat and dreaming can revisit.

## Good maintenance moves

- Tighten Otto's manners based on real conversations.
- Record broken promises or dead-air moments as repair targets.
- Update Profile Snapshot when a stable trait is confirmed.
- Update Weekly notes when priorities or overhaul themes change.
- Keep Central Schedule limited to real schedule anchors.

## Avoid

- Writing fluffy self-mythology.
- Mixing Sir Agathon profile data into Otto self-state unless the note is explicitly about the relationship.
- Storing raw conversation dumps when a compact operational summary is enough.
- Turning temporary friction into permanent identity too quickly.
- Treat dream and MORPHEUS outputs as candidate signals until reviewed; do not write them into Otto-Realm as settled self-state without verification.
