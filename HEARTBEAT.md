# Otto Profile Heartbeat

tasks:

- name: otto-profile-cycle
  interval: 8h
  prompt: "Run one silent profile-deepening pass for Sir Agathon. Read retrieval artifacts first. Use scoped raw-vault reads only when evidence is weak. Update the profile artifact, handoff, run journal, and heartbeat log. If no meaningful delta exists, keep writes minimal and reply HEARTBEAT_OK."

- name: a-clarity-ngram-miner
  interval: 2m
  prompt: "Run Python first: python C:\\Users\\joshu\\Obsidian-Otto\\scripts\\a1_clarity_ngram_miner.py --vault \"C:\\Users\\joshu\\Josh Obsidian\" --scope active --config \"config/clarity_ngram_miner.json\" --noise-config \"config/graph_shaper_noise_words.json\". Rule: only folders 10-90. If no delta files, skip scan. Reply concise summary."

- name: otto-graph-rollup-audit
  interval: 2m
  prompt: "Run Python first: python C:\\Users\\joshu\\Obsidian-Otto\\scripts\\c4_graph_rollup_audit.py --vault \"C:\\Users\\joshu\\Josh Obsidian\" --scope active --batch-size 10 --writeback --max-note-writes 3 --max-entity-writes 5 --max-moc-writes 3 --noise-config \"config/graph_shaper_noise_words.json\". Respect lock file and skip when lock active. Reply concise audit summary only: status, linked, already_present, deferred, graph_growth."

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
- If the live QMD index was refreshed, inspect `state/openclaw/sync_status.json` and the `qmd_index` field before falling back to raw vault reads.

## Scoped raw-vault notes

Only if evidence is weak, scope-read these exact notes:

- `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Profile Snapshot.md`
- `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Central Schedule.md`
- `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Heartbeats\2026-03-30.md`
- `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Heartbeats\2026-03-31.md`
- `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Heartbeats\2026-04-01.md`
- `C:\Users\joshu\Josh Obsidian\.Otto-Realm\Weekly\2026-W14 System Overhaul.md`
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
- Append one concise text line to `logs/kairos_profile.log` for each meaningful pass.

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

## Cadence note

- Previous interval `8h` is kept as the historical baseline.
- New cadence guidance can be appended below this note without removing the prior line, so heartbeat evolution stays auditable.
- Canonical Otto-Realm-facing cadence is `3h` staggered unless an operator-approved override is documented.
- QMD reindexing should happen after self-model refreshes or explicit memory writes, not on every heartbeat tick.

## Terminology note

- In Obsidian-Otto docs, prefer `KAIROS telemetry` for control-plane status sampling and strategy output.
- Reserve `heartbeat` for Otto-Realm-facing artifacts such as `Otto-Realm/Heartbeats/`.
