# OpenClaw Otto Bridge

This repo ships a local OpenClaw plugin package at `packages/openclaw-otto-bridge`.

Current bridge mode is installer-safe:

- read-only Otto/OpenClaw/QMD state can be surfaced directly inside OpenClaw
- mutating or desktop actions may return exact command previews or URIs instead of executing inline
- host-side launchers remain the execution surface for restart, reindex, sync, and rollback flows

## Native/WSL Operator Boundary

The optimized Obsidian-Otto setup now has two explicit WSL modes:

- native Windows OpenClaw: rollback/fallback operator surface
- WSL shadow gateway: loopback gateway on port `18790`, Telegram disabled
- WSL live gateway: Ubuntu OpenClaw is the live owner of gateway + Telegram on port `18790`
- QMD: same Otto-managed source manifest across both surfaces
- cron/heartbeat: read from `state/openclaw/cron_contract_v1.json` and `state/openclaw/heartbeat/otto_heartbeat_manifest.json`

Use `otto.bat operator-status` to verify parity and write `state/operator/openclaw_runtime.json`.

Use the explicit migration flow for live cutover:

```powershell
otto.bat wsl-live-preflight
otto.bat wsl-live-promote --dry-run
otto.bat wsl-live-promote --write
otto.bat wsl-live-status
```

`otto.bat wsl-gateway-start` now starts the current WSL config that is already installed. It does not silently perform a Telegram cutover anymore. `otto.bat native-fallback` now uses the rollback flow first when the repo is already in `S4_WSL_LIVE`.

## Install or relink

```powershell
openclaw plugins install -l .\packages\openclaw-otto-bridge
```

If your installed OpenClaw build supports `--force` for non-link installs only, do not combine it with `--link`. The WSL live promote flow now retries plain link install automatically when the CLI rejects `--force` with `--link`.

For WSL live, mirror the plugin into a WSL-local path before linking it. Linking directly from `/mnt/c/...` may be treated as world-writable and blocked by OpenClaw.

## Then restart the gateway

```powershell
openclaw gateway restart
```

If the OpenClaw CLI is hanging, use the repo-side fallback:

```powershell
.\probe-openclaw-gateway.bat
.\reload-openclaw-plugin.bat
```

Or use the gateway-only fallback:

```powershell
.\reload-openclaw-gateway.bat
```

## Tools exposed

- `otto_repo`
- `obsidian_desktop`

## Example operator actions

- `otto_repo` action=`openclaw-gateway-probe`
- `otto_repo` action=`openclaw-plugin-reload`
- `otto_repo` action=`openclaw-gateway-restart`
- `otto_repo` action=`morpheus-bridge`

Use `openclaw-plugin-reload` as the default fast path.
Use `openclaw-gateway-restart` only when the gateway process itself is unhealthy.

## Morpheus memory contract

`otto_repo` action=`morpheus-bridge` returns Otto's current bridge payload for MORPHEUS -> OpenClaw handoff.

Contract rules:

- Treat MORPHEUS output as `investigative-memory-candidate`.
- Do not treat MORPHEUS output as ready-to-use durable memory or ready-for-dreaming input.
- Promotion is blocked until the candidate reaches at least `reviewed`.
- Verification must use markdown-body or semantic retrieval evidence, not frontmatter alone.
- Raw `memory/.dreams/session-corpus`, `System (untrusted)`, heartbeat acknowledgements, and stale inline dreaming markers are forbidden as primary memory evidence.

## Current runtime status

As of 2026-04-25:

- OpenClaw gateway health should be read from the direct HTTP probe first.
- The gateway can show a historical failed probe while still being currently healthy.
- MORPHEUS -> OpenClaw is now explicitly bridged in `investigate-first` mode.
- OpenClaw must not consume MORPHEUS output as ready dreaming input.

Current live artifacts:

- `state/openclaw/morpheus_openclaw_bridge_latest.json`
- `artifacts/reports/morpheus_openclaw_bridge.md`
- `state/openclaw/gateway_probe.json`

Read the bridge payload before any dreaming or promotion flow.

## Last known constraints

- The producer side of OpenClaw dreaming is still not trusted as a source of durable memory by itself.
- Otto-side guardrails and the Morpheus bridge contain the issue, but they do not magically upgrade producer semantics.
- The live bridge can still report `vector_cache_live=false`; when that happens, MORPHEUS candidates must stay low-confidence.
- The practical consequence is: retrieval and review come first, dreaming or promotion comes later.

## Example `kairos-chat` prompts

- `cari catatan tentang operator rhythm`
- `find notes about operator rhythm`
- `deepen operator rhythm`
- `perdalam operator rhythm`
- `bandingkan sparse vs vector untuk operator rhythm`
- `compare operator rhythm`
- `show vector status`
- `ambil chunk note Projects/Policy Study.md`

## No-evidence bridge behavior

When `kairos-chat` returns no trustworthy evidence:

- `find ...` already performs one internal fast -> deep retry when enabled
- if `auto_escalate.recommended=true`, rerun once with `auto_escalate.command`
- if deep retrieval is still empty, use `suggested_queries` or `rewrite_suggestions` to guide the next query instead of returning a blank failure

## Notes

- `otto_repo` wraps the repo Python control plane.
- `obsidian_desktop` wraps the official Obsidian CLI and URI surfaces.
- The plugin also ships the skill `obsidian_otto_control_plane`.
