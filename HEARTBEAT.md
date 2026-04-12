# Otto Profile Heartbeat

tasks:

- name: otto-profile-cycle
  interval: 8h
  prompt: "Run one silent profile-deepening pass for Sir Agathon. Read retrieval artifacts first. Use scoped raw-vault reads only when evidence is weak. Update the profile artifact, handoff, run journal, and heartbeat log. If no meaningful delta exists, keep writes minimal and reply HEARTBEAT_OK."

## Silent mode

- Do not chat just to chat.
- Do not ask for attention unless a high-confidence urgent risk appears.
- Keep this pass silent and internal by default.

## Retrieval order

- Read `tasks/active/` first.
- Then read `state/handoff/latest.json`.
- Then read `state/checkpoints/pipeline.json`.
- Then read `artifacts/summaries/gold_summary.json`.
- Then read `artifacts/reports/kairos_daily_strategy.md`.
- Then read `artifacts/reports/dream_summary.md`.
- Then read `artifacts/reports/otto_profile.md`.

## Scoped raw-vault notes

Only if evidence is weak, scope-read these exact notes:

- `C:\Users\joshu\Josh Obsidian\Otto-Realm\Profile Snapshot.md`
- `C:\Users\joshu\Josh Obsidian\Otto-Realm\Central Schedule.md`
- `C:\Users\joshu\Josh Obsidian\Otto-Realm\Heartbeats\2026-03-30.md`
- `C:\Users\joshu\Josh Obsidian\Otto-Realm\Heartbeats\2026-03-31.md`
- `C:\Users\joshu\Josh Obsidian\Otto-Realm\Heartbeats\2026-04-01.md`
- `C:\Users\joshu\Josh Obsidian\Otto-Realm\Weekly\2026-W14 System Overhaul.md`
- `C:\Users\joshu\Josh Obsidian\Otto Obsidian\Action\++\!25-02 Obsidian Building\!25-02 Sprint 1\+MOC Guide.md`
- `C:\Users\joshu\Josh Obsidian\Otto Obsidian\Action\++\!25-02 Obsidian Building\!25-02 Sprint 1\=Life OS.md`
- `C:\Users\joshu\Josh Obsidian\Otto Obsidian\Action\++\!25-02 Obsidian Building\!25-02 Sprint 1\!25-02 Sprint 1-merged.md`

## Focus windows

- 06:00-11:59 → RTW, IB, SDZ, friction, schedule, current readiness
- 12:00-17:59 → SWOT, cognitive patterns, monetizable skills, service affinity
- 18:00-23:59 → SM-2, quiz prompts, soul or sub-persona deltas, council agenda
- 00:00-05:59 → only urgent repair or very high-signal profiling deltas

## What to maintain

- Keep `artifacts/reports/otto_profile.md` current and compact.
- Keep `state/handoff/latest.json` updated with the newest profiling goal and next actions.
- Append one concise JSON line to `state/run_journal/events.jsonl` for each meaningful pass.
- Append one concise text line to `logs/heartbeat_profile.log` for each meaningful pass.

## Profiling schema

- identity and style cues
- strengths and weaknesses
- cognitive risks and epistemic gaps
- monetizable skills and likely offers
- service affinity changes
- SM-2 or quiz hooks
- soul, sub-persona, or council hypotheses
- next probes with exact note paths

## Method

- Use RTW ↔ IB ↔ SDZ as the main lens.
- Use SENXoR and Experience or Personal-cue tags when judging authority depth.
- Prefer repeated evidence over one-off signals.
- Final artifacts for humans stay English or Indonesian only.
- Run tools first, gather evidence, then write.

## Response contract

- If nothing needs attention and no delta is strong enough, reply `HEARTBEAT_OK`.
