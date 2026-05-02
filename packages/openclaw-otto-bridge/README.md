# OpenClaw Otto Bridge

This local plugin exposes an installer-safe Obsidian-Otto bridge to OpenClaw through two tools:

- `otto_repo` for repo-scoped control plane actions
- `obsidian_desktop` for official Obsidian desktop CLI and URI actions

## What it wraps now

The bridge intentionally avoids shell execution inside the plugin so it can pass current OpenClaw install safety policy in WSL live mode.

That means:

- read-only repo state is returned directly from Otto state files
- mutating or long-running Otto actions are returned as exact command previews
- operator launchers remain the execution surface for restart, reindex, sync, and other state-changing tasks

This is the intended boundary for the WSL live migration patch. The plugin remains useful inside OpenClaw, but it no longer hides shell execution inside a linked plugin package.

`otto_repo` returns either:

- cached repo/runtime state for safe read actions
- an exact `python -m otto.cli` or `python -m otto.brain_cli` preview for manual/operator execution

Supported `otto_repo` actions:

- `status`
- `openclaw-health`
- `openclaw-gateway-probe`
- `openclaw-sync`
- `qmd-index-health`
- `qmd-reindex`
- `openclaw-gateway-restart`
- `openclaw-plugin-reload`
- `pipeline`
- `retrieve`
- `kairos`
- `dream`
- `morpheus-bridge`
- `brain`
- `kairos-chat`

`kairos-chat` is the NL bridge for:
- semantic fetch/search across SQLite + Chroma
- QMD-backed OpenClaw memory retrieval for Otto-Realm sources
- one-shot internal auto-deepen on weak `find ...` queries
- widening a weak query through explicit `deepen ...`
- sparse vs dense comparison
- vector status inspection
- per-note chunk inspection

When `find ...` has no trustworthy evidence, the payload now includes:
- `auto_escalate` for one-shot retry policy
- `rewrite_suggestions` from configured title aliases plus SQLite + Gold anchors
- `suggested_queries` with corpus-near rewrites such as `find <known title>` or `dig <known folder>`

Example NL prompts:
- `cari catatan tentang operator rhythm`
- `find notes about operator rhythm`
- `deepen operator rhythm`
- `perdalam operator rhythm`
- `bandingkan sparse vs vector untuk operator rhythm`
- `compare operator rhythm`
- `show vector status`
- `ambil chunk note Projects/Policy Study.md`

Example operator prompts:
- `otto_repo` action=`openclaw-gateway-probe`
- `otto_repo` action=`openclaw-plugin-reload`
- `otto_repo` action=`openclaw-gateway-restart`
- `otto_repo` action=`qmd-index-health`
- `otto_repo` action=`qmd-reindex`
- `otto_repo` action=`morpheus-bridge`

`morpheus-bridge` exposes the current Otto-side contract for MORPHEUS output:
- MORPHEUS output is an `investigative-memory-candidate`
- it is **not** ready for OpenClaw or QMD memory promotion by default
- promotion is blocked until the candidate has been reviewed or verified against markdown-body retrieval evidence
- raw `memory/.dreams/session-corpus` and operational noise are forbidden as primary memory evidence

`openclaw-plugin-reload` and other mutating actions are now operator-lane previews from the plugin surface.
Use `otto.bat`, the launcher menu, or the provided `.bat` wrappers to execute them on the host.

## QMD on Windows

OpenClaw memory is configured for QMD through the repo-owned WSL2 launcher:

```powershell
C:\Users\joshu\Obsidian-Otto\scripts\shell\qmd-wsl.js
```

The OpenClaw target is a Node launcher so Windows direct-spawn policy does not need shell fallback. It calls `/usr/bin/qmd` inside WSL2 to avoid accidentally loading Windows npm modules from `/mnt/c`, forces a Linux PATH, and maps OpenClaw's `XDG_CONFIG_HOME`, `QMD_CONFIG_DIR`, and `XDG_CACHE_HOME` from `C:\...` to `/mnt/c/...`. It defaults to the `Ubuntu` distro and honors `OTTO_QMD_WSL_DISTRO` when a different distro owns the QMD install.

`obsidian_desktop` uses:

- official Obsidian URI actions for `open`, `new`, `daily`, `search`
- official Obsidian CLI actions for `create`, `plugin-reload`, `dev-screenshot`, `eval`, `devtools`

## Assumptions

This package is meant for local self-development on Joshua's machine.

It auto-discovers the installed OpenClaw runtime from the standard Windows npm-global location and defaults the repo root to the parent `Obsidian-Otto` checkout.

If needed, configure plugin overrides under `plugins.entries.obsidian-otto-bridge.config`:

- `repoRoot`
- `pythonCommand`
- `obsidianCommand`
- `defaultTimeoutSeconds`
- `defaultVault`

## Install

From the repo root on Windows:

```powershell
openclaw plugins install -l .\packages\openclaw-otto-bridge
```

Then restart the OpenClaw gateway so the tools and plugin-shipped skill load cleanly.

For WSL live, the migration flow mirrors this package into `/home/joshu/.openclaw/plugins-local/obsidian-otto-bridge` before linking it. Linking directly from `/mnt/c/...` may be flagged as world-writable by OpenClaw.

If the OpenClaw CLI is hanging on `plugins` or `health`, use the repo fallback:

```powershell
.\probe-openclaw-gateway.bat
.\reload-openclaw-plugin.bat
```

Or use the lighter gateway-only restart:

```powershell
.\reload-openclaw-gateway.bat
```
