# B Execution Brief

## FOLLOWUP_AUTO
1. id: folder-1
- action: Repair metadata in Academics Agenda Database [Odd 23-24]
- why_now: risk=722.0; 361 notes missing frontmatter
- expected_artifact: normalized metadata / cleaner folder hygiene
- acceptance_check: frontmatter added consistently across the folder
2. id: folder-2
- action: Repair metadata in Thought Tracker 2024 - 2025→ @Daily Scratchpad Fle
- why_now: risk=352.0; 176 notes missing frontmatter
- expected_artifact: reduced hygiene debt in legacy tracker
- acceptance_check: missing frontmatter count materially reduced
3. id: probe-2
- action: Answer training probe: commitment continuity probe
- why_now: persistent unresolved weakness; training queue explicitly marks it pending
- expected_artifact: shortest truthful answer + one concrete next move
- acceptance_check: probe answered with no evasion

## FOLLOWUP_HUMAN
1. id: gold-1
- decision_needed: Review Gold candidate: Presentasi 553b097c0ca24dc2aec3c34fd5f43f6b
- why_now: promoted theory note with score above threshold
- minimal_input_needed: keep / revise / downgrade
- deadline_or_trigger: next review pass
2. id: gold-2
- decision_needed: Review Gold candidate: Teori Kejahatan dan Penderitaan 3 f6fbfad72ee24e51b6a7f5d50b187e3f
- why_now: bridge candidate already promoted; needs human judgment
- minimal_input_needed: keep / revise / downgrade
- deadline_or_trigger: next review pass
3. id: gold-3
- decision_needed: Review Gold candidate: TPNI 7 50 fa1efc2e2e6c42ee95c3ebe9b53becb5
- why_now: operational candidate already promoted; needs human judgment
- minimal_input_needed: keep / revise / downgrade
- deadline_or_trigger: next review pass

## STOP_TRIGGER
- Stop if the next repair pass still finds the same folder-level missing-frontmatter hotspot after one scoped batch.

## NEXT_ANCHOR
- Use the top-risk folder as the next scoped repair target, then re-check the second folder only if the first batch lands cleanly.

## VERDICT
- machine