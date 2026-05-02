# Otto Daily Review Ritual

## Morning
- `otto-wsl ops-health --strict`
- `otto-wsl daily-handoff`
- `otto-wsl next-due-jobs`
- `otto-wsl blocker-experiment --dry-run`

## Midday
- `otto-wsl paper-onboarding --dry-run`
- `otto-wsl song-skeleton --dry-run`
- `otto-wsl memento-due`

## Night
- `otto-wsl review-queue`
- `otto-wsl memory-promote-reviewed --review-id <id> --dry-run`
- `otto-wsl qmd-reindex --timeout-seconds 300`
- `otto-wsl reflection-candidate --from-outcome <id>`
