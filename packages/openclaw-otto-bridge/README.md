# OpenClaw Otto Bridge

This local plugin exposes the full Obsidian-Otto control plane to OpenClaw through two tools:

- `otto_repo` for repo-scoped control plane actions
- `obsidian_desktop` for official Obsidian desktop CLI and URI actions

## What it wraps

`otto_repo` calls the Python control plane in this repository through `python -m otto.cli` or `python -m otto.brain_cli`.

Supported `otto_repo` actions:

- `status`
- `openclaw-health`
- `openclaw-gateway-probe`
- `openclaw-sync`
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
- `otto_repo` action=`morpheus-bridge`

`morpheus-bridge` exposes the current Otto-side contract for MORPHEUS output:
- MORPHEUS output is an `investigative-memory-candidate`
- it is **not** ready for OpenClaw dreaming by default
- promotion is blocked until the candidate has been reviewed or verified against markdown-body retrieval evidence
- raw `memory/.dreams/session-corpus` and operational noise are forbidden as primary memory evidence

`openclaw-plugin-reload` is the fast/default path.
Use `openclaw-gateway-restart` only when you need a full process restart.

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
openclaw plugins install -l .\packages\openclaw-otto-bridge --force
```

Then restart the OpenClaw gateway so the tools and plugin-shipped skill load cleanly.

If the OpenClaw CLI is hanging on `plugins` or `health`, use the repo fallback:

```powershell
.\probe-openclaw-gateway.bat
.\reload-openclaw-plugin.bat
```

Or use the lighter gateway-only restart:

```powershell
.\reload-openclaw-gateway.bat
```
