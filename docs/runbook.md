# Runbook

## First install

1. `unzip` repo
2. Run `initial.bat`
3. Choose vault path (or bundled sample vault)
4. Choose whether to enable Docker helpers
5. Wait for Bronze → Silver → Gold pipeline
6. Open `main.bat` → start runtime

## Operator launcher

Run `main.bat` for the interactive home/advanced menu. All actions also work as standalone BAT files.

### Status

```
status.bat
```

### TUI (live monitoring)

```
tui.bat
```

### Runtime

```
start.bat     # start background runtime loop
stop.bat     # stop runtime
```

### Pipeline

```
reindex.bat              # full vault reindex
reindex.bat --scope Foo # scoped reindex (preferred)
```

### One-shot operations

```
kairos.bat          # KAIROS telemetry (one-shot)
dream.bat           # Dream consolidation (one-shot)
sync-openclaw.bat   # sync OpenClaw live config
brain.bat           # Otto Brain CLI
```

### Docker

```
docker-up.bat        # bring up Docker stack (all services)
docker-clean.bat     # clean Docker stack (down + volumes)
launch-mcp.bat       # launch obsidian-mcp in foreground stdio
launch-mcp.bat --build-only  # build only, no run
```

### Memory query

```
query.bat "your search query"
```
