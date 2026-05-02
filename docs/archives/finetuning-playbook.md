# Fine-tuning Playbook

## Critical truth

This repo does **not** fine-tune Codex / GPT-5 coding models directly.

Architecture:
- **Codex / GPT-5 family** = main controller and inference engine
- **secondary fine-tuned model** = optional persona/style specialist

## Before training

Only export from Gold after these checks pass:
- no major frontmatter corruption
- low duplicate rate
- clear user / assistant role formatting
- no unsupported capability hallucinations
- no sensitive fields accidentally included

## Recommended cadence

- KAIROS daily strategy review
- Gold review by a human before export
- persona fine-tuning at most on a fixed reviewed cadence
- do not fine-tune every day from drifting raw notes

## Persona principle

All personas should share the same operational heuristics:
- retrieval first
- explicit uncertainty
- safety boundaries
- reviewed Gold only

Different personas may vary only in:
- tone
- emphasis
- prioritization bias
- planning style

## Control boundary

Do not let a persona override:
- AGENTS policy
- hygiene rules
- reviewed Gold boundary
- wellbeing / SWOT boundaries
