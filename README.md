# Obsidian-Otto

Obsidian-Otto is a clean-room rebuild of your original `Obsidian-Scripts` workspace into a **Codex-native control plane** for:

- Obsidian vault hygiene and restructuring
- Bronze → Silver → Gold data normalization
- SQL + Chroma + LangChain-ready retrieval
- KAIROS telemetry
- Dreaming-mode memory consolidation
- local-first TUI monitoring with rich live logs
- stable Codex tasking through `AGENTS.md`, `.codex/agents`, and repo-scoped skills
- QMD-backed OpenClaw memory retrieval with separate `memory-core` dreaming support

## Context engineering stance

Obsidian-Otto follows a context-engineering discipline:

- prefer the smallest high-signal context that can still solve the task
- retrieve just in time from Gold, then Silver, then optional vector, then raw scope reads only if still needed
- treat memory, summaries, and handoff files as durable external context rather than stuffing long raw traces into active prompt state
- keep bridge drops, notes, and artifacts structured so compaction and resumption stay reliable

This is why the repo externalizes continuity into `state/`, `artifacts/`, and Otto-Realm-linked outputs instead of treating the whole vault as live prompt context.

## Terminology note

- Use `KAIROS telemetry` for Obsidian-Otto control-plane status sampling and strategy output.
- Reserve `heartbeat` for Otto-Realm-facing note artifacts such as `Otto-Realm/Heartbeats/`.

## Mental model

- **Folder** teaches structure
- **Scripts** teach operation
- **Logs** teach reality
- **State** teaches continuity
- **Tasks** teach agent focus

## Important clean-room boundary

This build does **not** copy source code from the uploaded OpenClud archive.
That archive identifies itself as `UNLICENSED` and leaked/proprietary in its own notice.
This repo only adopts clean-room architectural ideas:

- control room / operator surface
- KAIROS telemetry
- Dream consolidation
- task + run journal discipline
- live status and log visibility

See `docs/openclud-injection-map.md`.

## Quick start

1. Run `initial.bat`
2. Point Otto to your Obsidian vault, type `PICK` to browse, or use the bundled sample vault
3. Let the first Bronze → Silver → Gold pipeline finish
4. Run `tui.bat`
5. Run `status.bat` any time for a non-live health report

## Promised contents in this zip

This section is intentionally kept aligned with the actual shipped files.

### Isi utamanya

- `initial.bat` for bootstrap install + pilih vault + first pipeline
- `sync-openclaw.bat` to deploy canonical OpenClaw config into the live OpenClaw profile
- `tui.bat` for live TUI dengan Rich
- `status.bat`, `reindex.bat`, `kairos.bat`, `dream.bat`, `start.bat`, `stop.bat`, `docker-clean.bat`
- `AGENTS.md`, `.codex/`, `.agents/skills/`
- Bronze → Silver → Gold pipeline
- KAIROS + Dream clean-room build
- `docs/openclud-injection-map.md` for what was injected clean-room from OpenClud ideas
- sample vault + basic tests
- `sanity-check.bat`, `MANIFEST.promised.txt`, `CHECKSUMS.sha256`

### Default-nya

- local-first
- SQLite aktif
- Docker opsional
- TUI bisa cek task, state, logs, Gold summary, model routing, dan status Docker

### Langkah pakai

1. Extract zip
2. Run `initial.bat`
3. Run `tui.bat`

## Main operator files

- `initial.bat` bootstrap install + first pipeline
- `tui.bat` live dashboard
- `status.bat` snapshot status
- `reindex.bat` rerun Bronze → Silver → Gold
- `menu.bat` interactive batch launcher with QMD actions
- `start.bat` start background runtime loop
- `stop.bat` stop background runtime loop
- `sync-openclaw.bat` sync canonical `.openclaw/openclaw.json` into `C:\Users\joshu\.openclaw\openclaw.json`
- `qmd-health.bat` check whether the live QMD index is healthy
- `qmd-reindex.bat` refresh the live QMD index on demand
- `scripts/shell/qmd-wsl.js` launches QMD inside WSL2 for OpenClaw memory; `scripts/shell/qmd-wsl.cmd` is the manual operator wrapper. Set `OTTO_QMD_WSL_DISTRO` when the distro is not `Ubuntu`
- `scripts/wsl/otto-wsl.sh` is the WSL-first operator launcher for `status`, `wsl-health`, `docker-probe`, `qmd-index-health`, and `qmd-reindex`
- `scripts/wsl/openclaw-wsl.sh` stable OpenClaw launcher with absolute WSL binary path
- `scripts/wsl/otto-cli-wsl.sh` stable Otto CLI launcher with fixed repo root + `PYTHONPATH=src`
- `scripts/windows/openclaw-wsl.ps1` and `scripts/windows/otto-wsl.ps1` pass args to WSL launchers without `bash -lc` interpolation
- `kairos.bat` one-shot KAIROS telemetry strategy pass
- `dream.bat` one-shot memory consolidation
- `docker-clean.bat` stop optional local Docker services cleanly
- `sanity-check.bat` verify that promised files and core flows exist

## Structure

```text
docs/        operator docs and architecture
tasks/       active and completed agent tasks
src/         code and wrappers
scripts/     install + manage entry points
config/      app, retrieval, path, model, persona config
state/       handoff, checkpoints, journals, heartbeat state
artifacts/   reports, summaries, retrieval bundles
logs/        live operational truth
data/        sample + temp
external/    SQLite and optional Chroma store
```

## WSL-first QMD and Docker route

The supported QMD path on this machine is WSL2-first. Windows OpenClaw stays live during migration, while Ubuntu provides a canary runtime where QMD, Python, and Docker can share one Linux boundary.

Canonical WSL paths:

- OO repo: `/mnt/c/Users/joshu/Obsidian-Otto`
- Obsidian vault: `/mnt/c/Users/joshu/Josh Obsidian`
- Ubuntu runtime user: `joshu`
- Ubuntu runtime home: `/home/joshu`
- QMD binary: `/usr/bin/qmd`
- OpenClaw shadow config: `/home/joshu/.openclaw/openclaw.json`

Primary probes:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-wsl.sh wsl-health
wsl -d Ubuntu -- bash /mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-wsl.sh docker-probe
wsl -d Ubuntu -- bash /mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-wsl.sh qmd-index-health
wsl -d Ubuntu -- bash /mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-wsl.sh openclaw-doctor
wsl -d Ubuntu -- bash /mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-wsl.sh openclaw-memory
```

Stable launcher wrappers (recommended for automation/cron/heartbeat):

```powershell
.\scripts\windows\openclaw-wsl.ps1 --version
.\scripts\windows\openclaw-wsl.ps1 memory status --deep
.\scripts\windows\openclaw-wsl.ps1 gateway run --port 18790

.\scripts\windows\otto-wsl.ps1 runtime-smoke --gateway-port 18790
.\scripts\windows\otto-wsl.ps1 heartbeat-readiness --strict
.\scripts\windows\otto-wsl.ps1 creative-heartbeat --dry-run --explain
```

Do not use fragile interpolation patterns such as raw `wsl -d Ubuntu -- bash -lc "..."` from PowerShell for cron/heartbeat jobs. PowerShell interpolation can corrupt `$HOME`, `$PATH`, and `$(...)` expansion before Bash receives the command string.

Cron/planned jobs must use launcher commands such as:

```text
/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/otto-cli-wsl.sh creative-heartbeat --dry-run --explain
/mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/openclaw-wsl.sh gateway run --port 18790
```

Do not schedule raw `python3 -m otto.cli ...` jobs without explicit repo `cd`, `PYTHONPATH`, and PATH control.

Shadow gateway start/probe:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/joshu/Obsidian-Otto/scripts/wsl/openclaw-shadow-gateway.sh 18790
python -m otto.cli openclaw-gateway-probe --port 18790 --runtime wsl-shadow
```

The shadow gateway is accepted when port `18790` is reachable, `/health` reports live or the WebSocket port is open, Telegram remains disabled in the Ubuntu shadow config, and QMD memory remains visible. Auth/service/autostart warnings are non-blocking for shadow unless the gateway cannot start or memory becomes unavailable.

Docker uses Docker Desktop WSL integration for the `Ubuntu` distro. If `wsl-health` reports Docker unavailable, enable it in Docker Desktop settings, then rerun the probes.

Ubuntu shadow must never use OpenClaw from the Windows PATH. `scripts/wsl/otto-wsl.sh` quarantines `PATH` to Linux-native locations and refuses OpenClaw paths under `/mnt/c`, `WindowsApps`, or `*.exe`. `wsl-health` treats that as a hard failure, not a warning.

Ubuntu shadow commands must run as the canonical non-root user `joshu` with `HOME=/home/joshu`. `wsl-health` fails if WSL runs as root, if `joshu` is missing, or if HOME does not match the Linux passwd entry.

The shadow config generator must not invent OpenClaw config keys. It strips invalid historical guesses such as `plugins.local` and writes generator metadata to `openclaw.shadow.meta.json`, not into `openclaw.json`.

OpenClaw migration is intentionally shadow-first. Generate the Ubuntu canary config without cutting over Windows:

```powershell
python -m otto.cli openclaw-shadow-config --port 18790
wsl -d Ubuntu -- mkdir -p /home/joshu/.openclaw
wsl -d Ubuntu -- cp /mnt/c/Users/joshu/Obsidian-Otto/state/openclaw/ubuntu-shadow/openclaw.json /home/joshu/.openclaw/openclaw.json
```

When running from Ubuntu WSL, this can be installed into the shadow OpenClaw home in one step:

```powershell
wsl -d Ubuntu -- bash -lc "cd /mnt/c/Users/joshu/Obsidian-Otto && PYTHONPATH=src python3 -m otto.cli openclaw-shadow-config --write --install-path /home/joshu/.openclaw/openclaw.json"
```

If the local Otto bridge needs to be linked, use the OpenClaw plugin CLI after config validation instead of hand-writing plugin paths into config:

```powershell
wsl -d Ubuntu -- openclaw plugins install -l /mnt/c/Users/joshu/Obsidian-Otto/packages/openclaw-otto-bridge
wsl -d Ubuntu -- openclaw plugins list --verbose
wsl -d Ubuntu -- openclaw plugins doctor
```

Telegram is disabled in the Ubuntu shadow config by default. Only one OpenClaw instance may have Telegram enabled at a time.

Do not run WSL `qmd-reindex` as a readiness signal until both external gates are green: Docker Desktop WSL Integration for `Ubuntu`, and native Ubuntu OpenClaw. Until then, a WSL reindex timeout is classified as an OpenClaw boundary blocker, not a QMD source-health failure.

## Source registry and QMD manifest

Otto now treats QMD indexing as a governed export, not an open-ended filesystem crawl. The canonical registry is `state/memory/source_registry.json`; it records every source id, Windows path, WSL path, privacy class, owner, whether the source is required, and whether QMD may index it.

Operator commands:

```powershell
python -m otto.cli source-registry
python -m otto.cli qmd-manifest --write
```

Policy:

- `qmd_index=true` is for reviewed/canonical corpus such as `.Otto-Realm` memory tiers, Brain, briefing, Crack-Research, and reviewed/gold profile outputs.
- Raw or sensitive sources, including `instagram_graph_raw`, must remain `qmd_index=false`.
- `state/qmd/qmd_manifest.json` is generated from the registry and is the Otto-managed contract for what QMD is allowed to see.
- `qmd-index-health` includes generated manifest health when running against the live/default OpenClaw config.

## OpenClaw bridge surface

The WSL shadow bridge starts read-only. Otto exposes context and tool payloads to OpenClaw without creating a second gateway:

```powershell
python -m otto.cli openclaw-tool-manifest
python -m otto.cli openclaw-context-pack --task "current task"
python -m otto.cli qmd-search "OpenClaw bridge architecture"
python -m otto.cli single-owner-lock
python -m otto.cli runtime-smoke --gateway-port 18790
```

Generated state:

- `state/openclaw/tool_manifest.json`
- `state/openclaw/context_pack_v1.json`
- `state/openclaw/gateway_probe.json`
- `state/runtime/owner.json`
- `state/runtime/single_owner_lock.json`
- `state/runtime/smoke_last.json`

Initial OpenClaw tool manifest entries are read-only: `otto.qmd_health`, `otto.qmd_manifest`, `otto.context_pack`, `otto.source_registry`, and `otto.runtime_status`.

## Verification

Use:

```bat
sanity-check.bat
```

This writes:
- `artifacts/reports/sanity_check.json`
- `artifacts/reports/sanity_check.md`

Also inspect:
- `MANIFEST.promised.txt`
- `CHECKSUMS.sha256`

## Hidden dot-folders note

Some important Codex files live in dot-folders:

- `.codex/`
- `.agents/`

Do not delete them. They are intentionally part of the control plane.
