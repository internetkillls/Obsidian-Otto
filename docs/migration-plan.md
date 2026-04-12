# Migration Plan from Obsidian-Scripts

## Old top-level items

From the uploaded zip, the old workspace contains:
- `obsidian-ops/`
- `vault-context/`
- `vault-hygiene/`
- `vault-janitor/`
- `docx-cleanup/`
- `shared/`
- `state/`
- root launch bats and dashboards

## Migration mapping

| Old | New |
|---|---|
| `cleanup.py` | `scripts/manage/run_pipeline.py` + `src/otto/pipeline.py` |
| `dashboard_ctl.py` | `src/otto/app/tui.py` + `scripts/manage/status_report.py` |
| `main.bat` | `tui.bat`, `status.bat`, `start.bat` |
| `launch-mcp.bat` | deferred; stable shell harness first |
