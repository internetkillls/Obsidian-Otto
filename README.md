# Obsidian-Otto

Obsidian-Otto is a clean-room rebuild of your original `Obsidian-Scripts` workspace into a **Codex-native control plane** for:

- Obsidian vault hygiene and restructuring
- Bronze → Silver → Gold data normalization
- SQL + Chroma + LangChain-ready retrieval
- KAIROS heartbeat telemetry
- Dreaming-mode memory consolidation
- local-first TUI monitoring with rich live logs
- stable Codex tasking through `AGENTS.md`, `.codex/agents`, and repo-scoped skills

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
- KAIROS-style heartbeat
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
- `start.bat` start background runtime loop
- `stop.bat` stop background runtime loop
- `kairos.bat` one-shot heartbeat strategy pass
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
