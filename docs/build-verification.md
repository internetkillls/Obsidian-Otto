# Build Verification

This package was sanity-checked before zipping.

## What was checked

- Python source compiles
- tests pass
- bootstrap script works in non-interactive mode
- TUI imports and renders
- sanity-check script runs
- manifest and checksums were regenerated after cleanup

## Intentional clean state

The shipped zip does **not** include runtime-generated:
- `.env`
- SQLite runtime DB
- Gold reports
- log streams
- heartbeat state

Reason:
- those files would otherwise contain machine-specific absolute paths from the build machine

Generate them locally by running:
1. `initial.bat`
2. `sanity-check.bat`
3. `tui.bat`
