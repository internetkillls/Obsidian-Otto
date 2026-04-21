# OTTO Task: Pipeline & Architecture Optimizer

**Created**: 2026-04-21
**Status**: ACTIVE
**Priority**: HIGH
**Phase**: 2 Enhancement

---

## Objective

Optimize the Otto-Otto transformer/transducer architecture:
1. **Pipeline** (bronze → silver → gold)
2. **MCP** (Model Context Protocol integration)
3. **Path** resolution and error handling
4. Ensure ZERO error paths
5. Provide Codex/Claude resolution mechanisms

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         OTTO CORE                                │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   PIPELINE   │  │     MCP      │  │        PATH          │ │
│  │  bronze.py   │  │  obsidian-mcp│  │   load_paths()      │ │
│  │  silver.py   │  │  docker.yaml │  │   config.py          │ │
│  │  gold.py     │  │  launcher.py │  │   state.py           │ │
│  └──────────────┘  └──────────────┘  └──────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                      ORCHESTRATION                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ kairos   │→│ council  │→│ morpheus │→│  telemetry    │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Known Error Paths & Resolution Map

### Error Path 1: Vault Path Not Configured

```python
# Source: src/otto/tooling/obsidian_scan.py:168-169
if paths.vault_path is None:
    raise RuntimeError("Vault path not configured. Run initial.bat first.")
```

**Resolution**: Run `initial.bat` or set `OTTO_VAULT_PATH` in `.env`

**Codex Command**:
```
otto setup vault --path "C:\Users\joshu\Obsidian"
```

---

### Error Path 2: Empty Vault Scan

```python
# Source: src/otto/tooling/obsidian_scan.py:229-231
if not notes and not attachments:
    raise RuntimeError(f"Vault scan produced no notes...")
```

**Resolution**:
1. Check vault path is correct
2. Ensure `.md` files exist
3. Check scope parameter

**Codex Command**:
```
otto doctor --check vault --scope Projects
```

---

### Error Path 3: Pipeline Lock

```python
# Source: src/otto/pipeline.py:77-81
if not _acquire_pipeline_lock(paths):
    raise RuntimeError("Another pipeline run is already in progress...")
```

**Resolution**: Wait for other pipeline to finish or remove lock file

**Codex Command**:
```
otto pipeline unlock --force
```

---

### Error Path 4: SQLite/Postgres Connection

```python
# Source: src/otto/db/postgres_client.py
# pg_available() checks connection
```

**Resolution**:
1. Start Docker Desktop
2. Check `config/postgres.yaml`
3. Use fallback to SQLite

**Codex Command**:
```
otto doctor --check database --fallback sqlite
```

---

### Error Path 5: MCP Container Not Running

```python
# Source: src/otto/app/launcher.py:509-519
if not docker_daemon_running():
    print("[ERROR] Docker is not running...")
```

**Resolution**:
1. Start Docker Desktop
2. Run `docker compose up -d`

**Codex Command**:
```
otto mcp start --check
```

---

## Error Resolution Skill

### File: `.agents/skills/pipeline-optimizer/SKILL.md`

See attached skill for Codex/Claude auto-resolution.

---

## Dependency Map

| Component | Dependencies | Status |
|---|---|---|
| `pipeline.py` | `obsidian_scan`, `normalize`, `gold_builder` | ✅ |
| `kairos.py` | `kairos_gold`, `council`, `morpheus`, `telemetry` | ✅ |
| `launcher.py` | `docker_utils`, `launcher_state`, `mcp` | ✅ |
| `config.py` | YAML, Path, os | ✅ |
| `state.py` | JSON, Path | ✅ |

---

## Optimization Checklist

- [ ] Pipeline lock timeout (currently blocks forever)
- [ ] Vault path auto-detection
- [ ] MCP health check endpoint
- [ ] Path resolution fallback chain
- [ ] Error logging with recovery hints
- [ ] Zero-error path verification

---

## Verification Commands

```bash
# Test all error paths
python scripts/test_error_paths.py

# Run pipeline stress test
python scripts/test_pipeline_stress.py

# Verify MCP connectivity
otto mcp check --verbose
```
