# OpenClaw Injection Map

This document tracks how Otto-managed OpenClaw settings are injected from the repo control plane into the live OpenClaw profile.

## Managed sources

- `.openclaw/openclaw.json`
- `state/openclaw/capabilities.json`
- Otto env contract derived by `src/otto/openclaw_support.py`

## Phase 1 contract

- `agents.defaults.heartbeat.every`
- `agents.defaults.cliBackends`
- `agents.defaults.models`
- `models.providers`
- `env.shellEnv`

## Notes

- Otto treats UI capability toggles as derived readiness state unless a verified writable schema is available.
- Separate multi-cron scheduling is intentionally deferred until the OpenClaw schedule schema is verified.
