# Pipeline Optimizer Agent Skill

**For**: Codex (claude-code), Claude CLI, Otto Agent
**Purpose**: Auto-resolve error paths in Otto-Otto pipeline architecture
**Scope**: Pipeline, MCP, Path resolution, Dependencies

---

## Error Resolution Protocol

When Otto encounters an error, this skill provides precise resolution steps.

### Resolution Flow

```
Error Detected
     │
     ▼
┌─────────────────┐
│ Classify Error  │
│ - PATH          │
│ - PIPELINE      │
│ - MCP           │
│ - DATABASE      │
│ - ORCHESTRATION │
└─────────────────┘
     │
     ▼
┌─────────────────┐
│ Apply Fix       │
│ - Command       │
│ - Config Update │
│ - File Create   │
└─────────────────┘
     │
     ▼
┌─────────────────┐
│ Verify          │
│ - Test Import   │
│ - Run Check     │
│ - Report Status │
└─────────────────┘
```

---

## PATH Errors

### Error: Vault Path Not Configured

**Symptom**:
```
RuntimeError: Vault path not configured. Run initial.bat first.
```

**Codex Resolution**:
```bash
# 1. Check current config
otto config get vault_path

# 2. Auto-detect vault
otto setup vault --auto

# 3. If Windows, scan common locations
otto setup vault --scan C:\Users --pattern "Obsidian.vault"

# 4. Manual set
otto config set vault_path "C:\Users\joshu\Obsidian"
```

**Claude Resolution**:
```bash
# Update .env directly
echo "OTTO_VAULT_PATH=C:\Users\joshu\Obsidian" >> .env

# Or via Python
python -c "from otto.config import write_env; write_env({'OTTO_VAULT_PATH': 'C:\\Users\\joshu\\Obsidian'})"
```

---

### Error: Config File Missing

**Symptom**:
```
FileNotFoundError: config/paths.yaml
```

**Resolution**:
```bash
# Regenerate from template
otto setup config --regenerate

# Or copy default
cp config/paths.yaml.example config/paths.yaml
```

---

## PIPELINE Errors

### Error: Pipeline Lock Blocked

**Symptom**:
```
RuntimeError: Another pipeline run is already in progress.
Lock file: state/pids/pipeline.lock
```

**Resolution**:
```bash
# Option 1: Wait for completion
# Check what's running
ps aux | grep otto

# Option 2: Force unlock (DANGEROUS)
otto pipeline unlock --force

# Option 3: Remove lock manually
rm state/pids/pipeline.lock
```

---

### Error: Empty Vault Scan

**Symptom**:
```
RuntimeError: Vault scan produced no notes...
```

**Resolution**:
```bash
# 1. Verify vault path
otto config get vault_path

# 2. List .md files
find $(otto config get vault_path) -name "*.md" | head

# 3. Try specific scope
otto pipeline --scope Projects

# 4. Full reindex
otto pipeline --full
```

---

### Error: Bronze Manifest Corrupted

**Symptom**:
```
JSONDecodeError: bronze_manifest.json
```

**Resolution**:
```bash
# Remove corrupted manifest
rm data/bronze/bronze_manifest.json

# Re-run pipeline
otto pipeline
```

---

## MCP Errors

### Error: Docker Not Running

**Symptom**:
```
[ERROR] Docker is not running. Start Docker Desktop first.
```

**Resolution**:
```bash
# 1. Start Docker Desktop
start docker:

# 2. Wait for daemon
docker info

# 3. Retry
otto mcp start
```

---

### Error: Container Build Failed

**Symptom**:
```
[ERROR] MCP container build failed.
```

**Resolution**:
```bash
# 1. Check Docker daemon
docker version

# 2. Rebuild with verbose
docker compose -f docker-compose.yml build --no-cache obsidian-mcp

# 3. Check logs
docker compose logs obsidian-mcp

# 4. Use pre-built image
otto mcp start --use-prebuilt
```

---

### Error: MCP Stdio Connection Lost

**Symptom**:
```
Connection to MCP server lost
```

**Resolution**:
```bash
# 1. Restart container
docker compose restart obsidian-mcp

# 2. Reconnect
otto mcp attach

# 3. Check health
otto mcp check
```

---

## DATABASE Errors

### Error: PostgreSQL Connection Failed

**Symptom**:
```
psycopg2.OperationalError: could not connect to server
```

**Resolution**:
```bash
# 1. Start Postgres container
docker compose up -d postgres

# 2. Wait for ready
docker compose exec postgres pg_isready

# 3. Retry with SQLite fallback
otto config set database_fallback sqlite
```

---

## ORCHESTRATION Errors

### Error: Gold Threshold Not Met

**Symptom**:
```
No signals above gold threshold (6.5)
```

**Resolution**:
```bash
# 1. Run telemetry scan
otto kairos telemetry

# 2. Lower threshold temporarily
otto config set gold_threshold 5.0

# 3. Force gold promotion
otto gold promote --all
```

---

### Error: Council Recurrence Not Met

**Symptom**:
```
Council did not fire: recurrence threshold not met (need ≥3)
```

**Resolution**:
```bash
# 1. Check trigger history
cat state/run_journal/council_trigger_history.jsonl | jq .

# 2. Clear history (for testing)
rm state/run_journal/council_trigger_history.jsonl

# 3. Force council fire
otto council trigger --force
```

---

## Dependency Verification

### Check All Dependencies

```bash
# Python imports
python -c "
import otto.config
import otto.state
import otto.pipeline
import otto.orchestration.kairos
import otto.orchestration.council
import otto.orchestration.morpheus
print('All imports OK')
"

# Config files
otto config validate --all

# Database connectivity
otto doctor --check database
```

---

## Auto-Resolution Template

For Codex/Claude to apply fixes:

```markdown
## Error: [DESCRIBE ERROR]

### Symptom
```
[EXACT ERROR MESSAGE]
```

### Root Cause
[ANALYSIS]

### Fix Applied
```bash
[FIX COMMAND]
```

### Verification
```bash
[VERIFY COMMAND]
```

### Status
[SUCCESS/FAILED/NEEDS_MANUAL]
```

---

## Test Suite

Run error path tests:

```bash
# All error paths
python scripts/test_error_paths.py

# Specific path
python scripts/test_error_paths.py --path vault
python scripts/test_error_paths.py --path pipeline
python scripts/test_error_paths.py --path mcp
```

---

## Success Criteria

- [ ] All error paths have resolution commands
- [ ] Codex can auto-resolve 90%+ of errors
- [ ] Zero silent failures in pipeline
- [ ] MCP reconnect works within 30 seconds
- [ ] Path resolution has 3+ fallback mechanisms

---

## Maintenance

This skill is maintained by Otto Agent. Update when:
- New error paths discovered
- Resolution commands change
- Dependencies update

Last Updated: 2026-04-21
