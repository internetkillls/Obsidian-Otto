# Mentor Feedback Loop Rebuild - Phase 2 Checkpoint

Date: 2026-04-25  
Status: implemented and verified  
Scope: probe-driven mentoring loop + launcher surface

## Why this checkpoint exists

Phase 1 closed the obvious missing loop between mentor output and human resolution.
Phase 2 adds the missing middle layer:

- developmental work now goes through a probe before a task is issued
- gap typing is determined from direct probe answers, not from Gold or vault topology
- legacy `SM-2` naming is retired from canonical self-model and handoff surfaces
- the launcher can now show the queue and resolve pending mentor tasks

## What Phase 2 changed

- Canonical self-model field is now `continuity_prompts`
- Legacy `sm2_hooks` remains read-compatible only
- Added probe-first mentoring flow in `src/otto/orchestration/mentor.py`
- Added deterministic probe classification:
  - `theory_gap`
  - `application_gap`
  - `resolved`
- Added weakness registry state in `state/kairos/mentor_latest.json`
- Added launcher home actions for:
  - `Training Queue`
  - `Resolve Training Task`
- Extended KAIROS handoff with:
  - `mentor_active_probes`
  - `mentor_weakness_registry`

## New runtime contract

The developmental loop now works like this:

1. KAIROS reads current profile risk from structured handoff state
2. If a weakness has no active mentor item, Otto writes a probe into `.Otto-Realm/Training/probes/`
3. Josh answers the probe in Obsidian
4. Next KAIROS cycle classifies the probe into `theory_gap`, `application_gap`, or `resolved`
5. Otto creates a bounded task only for non-resolved gaps
6. Josh resolves the task by moving it into `done/` or `skipped/`, or by using the launcher resolve action
7. Otto writes active probes, pending tasks, and weakness registry state into `state/kairos/mentor_latest.json`

This keeps the mentoring loop closed without requiring any new LLM persona runtime.

## Explicit non-goals in Phase 2

- No redesign of operational `CouncilEngine`
- No change to `cognitive_weakness` trigger policy
- No dynamic mentor persona generation
- No new external LLM/runtime dependency for mentoring classification
- No probe-answer editing inside the launcher

## Files touched by the rebuild

- `src/otto/orchestration/mentor.py`
- `src/otto/orchestration/kairos.py`
- `src/otto/orchestration/brain.py`
- `src/otto/brain/self_model.py`
- `src/otto/brain/predictive_scaffold.py`
- `src/otto/app/launcher.py`
- `tests/test_mentor.py`
- `tests/test_brain_self_model.py`
- `tests/test_brain_predictive.py`
- `tests/test_launcher.py`
- `tests/test_kairos_morpheus_extension.py`

## Verification completed

Targeted regression set:

```text
pytest tests/test_brain_self_model.py tests/test_brain_predictive.py tests/test_mentor.py tests/test_launcher.py tests/test_kairos_morpheus_extension.py -q
```

Result:

- `49 passed`

Sanity check run:

```text
python scripts/manage/sanity_check.py --write-report
```

Observed on 2026-04-25:

- `all_promised_present: True`
- `training_ready: True`
- `runtime_status: RUNNING`
- `docker_status: ok`
- `top_folder_count: 1`
- `retrieval_note_hits: 0`
- `openclaw_config_sync: True`
- `anthropic_ready: True`
- `hf_fallback_ready: True`
- `vector_enabled: False`
- active task: `vault-hygiene-pass-01.md`

## Acceptance status

Phase 2 acceptance is met for the intended scope:

- mentor creates a probe before issuing a task
- answered probes are classified into gap types
- tasks are created only for non-resolved gaps
- resolved tasks are not blindly reissued from the same probe
- launcher can read the queue and resolve pending tasks
- canonical naming is now `continuity_prompts`
- legacy `sm2_hooks` still loads as compatibility fallback

## Remaining work after this checkpoint

Likely Phase 3 candidates:

- dynamic mentor persona generation and archive policy
- probe cadence / cooldown policy for re-opening resolved weaknesses
- richer launcher affordances for probe visibility or navigation
