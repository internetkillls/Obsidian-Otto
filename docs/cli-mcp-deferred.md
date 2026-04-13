# obsidian-cli-mcp: Deferred

**Date:** 2026-04-13
**Status:** Deferred — prerequisite not met

## What This Was

An MCP server wrapping a hypothetical `obsidian` CLI binary to provide vault command execution.

## Why It Is Deferred

1. **No real `obsidian` CLI binary exists.** Otto's `scripts/manage/*.py` are Otto-internal Python scripts — wrapping them as MCP would reinforce Otto control-plane coupling, which is the opposite of the migration goal (moving execution out of Otto).
2. **No external CLI-capable backend selected.** The obsidian-cli skill currently uses `scripts/manage/*.py` directly. Until a real external backend (e.g. an official Obsidian CLI tool, a third-party vault automation tool) is identified and selected, the MCP container has nothing meaningful to wrap.
3. **Migration principle: capability, not internal re-wrapping.** MCP should expose *system capabilities* (Obsidian vault operations), not *Otto's own implementation details*.

## Prerequisite to Resume

Select a real external CLI-capable backend. Candidates:
- Official Obsidian CLI tool (when available)
- Third-party vault automation CLI (e.g. obsidian-shellcommands, b枕)
- Custom wrapper around `python scripts/manage/*.py` (but only if that subprocess is considered a stable external API, not internal implementation)

## Current Active Path

- **Read-only vault access:** `obsidian-mcp` (`packages/obsidian-mcp/`) — active, file-based, read-only.
- **Write vault access:** deferred. Mount point must be `:rw` and this doc updated when write path is designed.
- **Vault CLI automation:** deferred. Depends on external CLI backend selection.
