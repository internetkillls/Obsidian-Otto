---
name: obsidian_otto_control_plane
description: Use Obsidian-Otto as an OpenClaw tool bridge for repo control-plane actions and Obsidian desktop automation.
---

# Obsidian-Otto Control Plane

Use `otto_repo` whenever the task is about the Obsidian-Otto repository as a system.

Use `obsidian_desktop` whenever the task is about driving the official Obsidian desktop app.

Current bridge mode is installer-safe and preview-first:

- read-only Otto/OpenClaw/QMD state may be returned directly from repo state files
- mutating actions may return exact launcher or CLI previews instead of executing inline
- do not assume the linked plugin can spawn shell commands directly

## When to use `otto_repo`

Prefer `otto_repo` for:

- repo health and state checks
- OpenClaw sync and OpenClaw health checks
- retrieval through the repo's structured Bronze -> Silver -> Gold path
- QMD-backed OpenClaw memory health checks and command previews
- KAIROS heartbeat runs
- Dream consolidation runs
- MORPHEUS -> OpenClaw memory-candidate inspection
- repo pipeline refreshes
- Brain CLI actions
- KAIROS natural-language commands via `kairos-chat`, especially semantic fetch/search, compare, vector status, and chunk inspection

## When to use `obsidian_desktop`

Prefer `obsidian_desktop` for:

- opening notes or searches in the Obsidian app
- creating a new note through official URI or CLI surfaces
- opening the daily note
- reloading an Obsidian community plugin during development
- taking a desktop screenshot from the Obsidian dev surface
- running `eval` or opening devtools in the desktop app

## Operating rules

- Start with `otto_repo` action=`status` or `openclaw-health` before heavy actions when the repo state is unclear.
- When the OpenClaw CLI is hanging, prefer `otto_repo` action=`openclaw-gateway-probe`, `openclaw-plugin-reload`, or `openclaw-gateway-restart` instead of waiting on `openclaw plugins ...`.
- Prefer `otto_repo` action=`retrieve` over dumping raw vault text.
- Prefer `otto_repo` action=`morpheus-bridge` before any OpenClaw dreaming or memory-promotion decision. MORPHEUS output must be treated as `candidate memory`, not ready-to-use durable memory.
- Prefer `otto_repo` action=`kairos-chat` when the user asks in natural language for KAIROS to find, fetch, compare, or inspect vectorized memory.
- `find ...` now auto-deepens once inside `kairos-chat` itself when fast retrieval has no trustworthy evidence.
- When `otto_repo` action=`kairos-chat` still returns `fallback.status=no_evidence` and `auto_escalate.recommended=true`, immediately rerun once with `message=auto_escalate.command` before replying to the user. This should now be a rare compatibility path rather than the default.
- If the deep retry still returns `fallback.status=no_evidence`, surface `suggested_queries` or `rewrite_suggestions` instead of only saying the search failed.
- Prefer `otto_repo` action=`openclaw-sync` before debugging OpenClaw drift.
- Check `otto_repo` action=`qmd-index-health` when retrieval looks stale or an Otto-Realm source was refreshed.
- Use `otto_repo` action=`qmd-reindex` after self-model writes or when the QMD index needs an explicit refresh, then run the returned command from the host/operator lane.
- Use `otto_repo` action=`pipeline` only when a refresh is actually needed.
- Never use raw `memory/.dreams/session-corpus`, heartbeat acknowledgements, or `System (untrusted)` text as primary evidence for OpenClaw memory actions.
- Keep scope as small as possible.
- If the bridge returns `execution_mode=manual_required`, surface the exact next command or URI instead of pretending the action already ran.

## Prompt examples

- `otto_repo` action=`kairos-chat` message=`cari catatan tentang operator rhythm`
- `otto_repo` action=`kairos-chat` message=`find notes about operator rhythm`
- `otto_repo` action=`kairos-chat` message=`deepen operator rhythm`
- `otto_repo` action=`kairos-chat` message=`perdalam operator rhythm`
- `otto_repo` action=`kairos-chat` message=`bandingkan sparse vs vector untuk operator rhythm`
- `otto_repo` action=`kairos-chat` message=`compare operator rhythm`
- `otto_repo` action=`kairos-chat` message=`show vector status`
- `otto_repo` action=`kairos-chat` message=`ambil chunk note Projects/Policy Study.md`
- `otto_repo` action=`openclaw-gateway-probe`
- `otto_repo` action=`openclaw-plugin-reload`
- `otto_repo` action=`openclaw-gateway-restart`
- `otto_repo` action=`qmd-index-health`
- `otto_repo` action=`qmd-reindex`
- `otto_repo` action=`morpheus-bridge`

Use `openclaw-plugin-reload` as the default repair path.
Execute the returned command from the host/operator lane when the bridge is in preview-only mode.
Escalate to `openclaw-gateway-restart` only when the gateway itself is unhealthy.
