# Obsidian CLI Expert System — Reference

## Status

Initial reference. To be populated with Obsidian CLI patterns as this skill is used.

## Obsidian CLI patterns

### Available tools

(To be populated based on installed Obsidian CLI tools and MCP server availability.)

### Common operations

#### Safe (announce, no confirmation needed)

```bash
# Vault search
python scripts/manage/status_report.py --json

# Pipeline status
python scripts/manage/status_report.py --scope bronze

# File listing
ls vault/**/*.md | head -50
```

#### Moderate (announce + confirm)

```bash
# Create file in safe location
echo "# Draft" > drafts/YYYY-MM-DD-draft.md

# Move file within vault
mv vault/old-path.md vault/new-path.md

# Bulk rename
for f in vault/**/*.md; do
  # process each file
done
```

#### Destructive (confirm required)

```bash
# Delete file
rm vault/path/to/file.md

# Bulk delete
rm vault/**/*.tmp

# Overwrite frontmatter
# Requires confirmation per file
```

### Obsidian MCP tools

(To be populated when MCP server configuration is available. Check `config/paths.yaml` and vault MCP config.)

### Rollback procedures

- For moves: `mv new-path.md old-path.md`
- For deletions: restore from git if committed, or from backup
- For overwrites: git restore (if previously committed)

## Command queue patterns

(To be populated when recurring command queues are established.)

## Safety checklist

Before any command:
- [ ] Is this destructive? (rm, mv on vault files, batch modification)
- [ ] What is the rollback plan?
- [ ] Has the user confirmed?
- [ ] Is this dry-run possible first?
