# Operator Launcher

## Overview

The launcher (`main.bat`) is Otto's operator surface. It is a Python-based console with two screens (home/advanced) backed by structured state files.

## Architecture

```
main.bat (thin shim)
  -> calls ensure_python_env
  -> resolves .venv/Scripts/python.exe
  -> runs scripts/manage/run_launcher.py
     -> LauncherApp (src/otto/app/launcher.py)
        -> LauncherStateStore (src/otto/launcher_state.py)
           -> state/launcher/current.json
           -> state/launcher/last_action.json
           -> state/launcher/mcp_last_run.json
```

Every BAT file (`start.bat`, `stop.bat`, `doctor.bat`, etc.) is an identical 6-line shim. All operator logic lives in Python.

## BAT files

All BAT files share this pattern:

```batch
@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "COMMON=%ROOT%scripts\shell\otto_common.bat"
set "LAUNCHER=%ROOT%scripts\manage\run_launcher.py"
call "%COMMON%" :ensure_python_env "%ROOT%" PYTHON_EXE PYTHONPATH_VALUE
if errorlevel 1 (
    echo [Otto] Virtual environment missing. Run initial.bat first.
    exit /b 1
)
set "PYTHONPATH=%PYTHONPATH_VALUE%"
"%PYTHON_EXE%" "%LAUNCHER%" --once ACTION -- %*
exit /b %ERRORLEVEL%
endlocal
```

## State files

### `state/launcher/current.json`

Written every menu render. Fields:

```json
{
  "ts": "2026-04-14T10:00:00+07:00",
  "screen": "home",
  "runtime_status": "STOPPED",
  "runtime_pid": null,
  "venv_ready": true,
  "vault_host_path": "C:\\Users\\joshu\\Josh Obsidian",
  "docker_cli_available": true,
  "mcp_configured": false,
  "recommended_next_actions": ["..."]
}
```

### `state/launcher/last_action.json`

Written after every action. Fields:

```json
{
  "ts": "2026-04-14T10:00:00+07:00",
  "action": "start",
  "screen": "home",
  "status": "ok",
  "exit_code": 0,
  "duration_ms": 120,
  "details": {"runtime_status": "started", "runtime_pid": 95892}
}
```

### `state/launcher/mcp_last_run.json`

Written after every `launch-mcp` action (success or failure):

```json
{
  "ts": "2026-04-14T10:00:00+07:00",
  "mode": "build_only",
  "vault_host": "C:\\Users\\joshu\\Josh Obsidian",
  "vault_path": "/vault",
  "build_exit": null,
  "run_exit": 1,
  "notes": ["disabled in config/docker.yaml", "docker daemon unavailable"]
}
```

## MCP launch flags

```batch
launch-mcp.bat              # normal launch (requires enabled: true in docker.yaml)
launch-mcp.bat --build-only  # build image, verify Dockerfile, no run
launch-mcp.bat --no-build    # skip build, run directly
```

`launch-mcp.bat --help` prints usage without touching state files.

## Native/WSL operator lane

The advanced launcher screen includes a dedicated OpenClaw/QMD operator lane:

```batch
otto.bat operator-status
otto.bat operator-doctor
otto.bat operator-update
otto.bat wsl-live-preflight
otto.bat wsl-live-promote --dry-run
otto.bat wsl-live-promote --write
otto.bat wsl-live-status
otto.bat wsl-live-rollback --write
otto.bat wsl-gateway-start
otto.bat wsl-gateway-stop
otto.bat wsl-gateway-restart
otto.bat native-fallback
```

For a desktop-first workflow, install shortcuts and the login startup task:

```batch
scripts\shell\install-operator-shortcuts.bat
```

This creates shortcuts for the operator menu, WSL gateway start/restart, WSL live status, and native fallback. It also installs a current-user `ONLOGON` task that runs `otto.bat wsl-gateway-start` after restart. The startup task starts the current WSL config already installed, so it is safe for both shadow and promoted live states. See [operator-wsl-native.md](/C:/Users/joshu/Obsidian-Otto/docs/operator-wsl-native.md) for the safety boundary and parity checks.

## Runtime PID lifecycle

1. `start.bat` spawns `runtime_loop.py` via `subprocess.Popen` (detached)
2. PID written to `state/pids/runtime.pid`
3. `stop.bat` reads PID → `Stop-Process -Force`
4. If process dies without stopping, PID file is stale → cleared on next start/stop

## Metadata enrichment entrypoint

`metadata-enrich.bat` is a thin shim for the metadata workflow:

```text
metadata-enrich.bat -> otto.bat metadata-enrich -> scripts/manage/run_launcher.py --once metadata-enrich -> scripts/manage/run_metadata_enrichment.py
```

Default mode is `review`. `apply` or `entity` must be paired with `--confirm` to write.
If you want Obsidian itself to execute the matching plugin command for a single note, pass `--dispatch-command` to the runner. The command name comes from `config/metadata_enrichment.yaml`.

## Notion export hygiene entrypoint

`notion-export-hygiene.bat` is the companion workflow for Notion imports that need hash cleanup:

```text
notion-export-hygiene.bat -> otto.bat notion-export-hygiene -> scripts/manage/run_launcher.py --once notion-export-hygiene -> scripts/manage/run_notion_export_hygiene.py
```

Use it after import to:
- strip hash-like suffixes from filenames
- write or normalize frontmatter titles and aliases
- rewrite scoped wikilinks that still point at the old filename

`apply` writes changes only when paired with `--confirm`. Add `--reindex-after` if you want the scoped pipeline to run immediately after the rename pass.

## MCP configuration check

`mcp_configured` in `current.json` requires **all** of:
- `config/docker.yaml` → `enabled: true`
- `config/docker.yaml` → `"obsidian-mcp"` in `services` list
- `.env` → `OBSIDIAN_VAULT_HOST` set

If any fail, `mcp_configured: false` and menu recommendation says "MCP stays disabled until docker.yaml deployment is enabled."
