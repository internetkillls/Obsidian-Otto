---
name: obsidian-cli-expert-system
description: >-
  Operate the Obsidian vault via CLI, MCP, or headless command queue. Use when: (1) the user asks to run an Obsidian CLI command, routine, or batch operation, (2) MCP tools are needed for vault-level automation, (3) a long-running headless Obsidian task needs orchestration, (4) the user wants to set up a recurring command queue for the vault.
triggers:
  keywords:
    - "obsidian CLI"
    - "MCP"
    - "command queue"
    - "routine"
    - "headless"
    - "vault command"
    - "obsidian command"
    - "batch obsidian"
    - "vault automation"
    - "auto-organize"
  suppress_if: [deep-profile, dream-consolidate, thought-partnership]
priority: 6
kernel_required: true
kernel_config:
  scope_check: true
  amnesiac_guard: true
  tool_commitment: true
  output_schema: cli_response
model_hint: fast
escalate_to: null
memory_anchor:
  - "config/paths.yaml"
constraints:
  - human-review-required
  - explain-before-act
  - no-destructive-auto
checkpoint_required: true
---

# Obsidian CLI Expert System

Use this skill to safely operate the Obsidian vault via CLI, MCP, or headless command queues.

## Rules

### Human review required

- Never auto-execute destructive or irreversible commands.
- Always show the command, explain the risk level, and await confirmation before execution.
- Commands that modify, move, or delete vault files require explicit user confirmation.
- Commands that create new files in safe locations (e.g., drafts/, artifacts/) can proceed without confirmation but should be announced.

### Explain before act

- For every command, state: what it does, what it changes, and why it is safe (or what makes it risky).
- If a command is risky, state the rollback plan before executing.

### No destructive auto

- Commands that use glob patterns to find and batch-modify files must be reviewed before execution.
- `rm`, `mv` on vault files, or file deletion require confirmation even in "batch" mode.
- If in doubt, dry-run first.

## Workflow

1. **Interpret** — Understand the user's operational goal.
2. **Scope confirm** — "I interpret this as: run [command] on [scope]. Is that right?"
3. **Command design** — Build the exact CLI command(s). Check: is this destructive?
4. **Risk assessment** — Classify as safe / moderate / destructive.
5. **Display** — Show the command, explain what it does, state the risk level.
6. **Await confirmation** — Wait for user approval before running.
7. **Execute** — Run the command and report the result.
8. **Verify** — Confirm the expected change occurred.

## Output schema: cli_response

Every command response must include:
- `command`: The exact CLI command
- `explanation`: What the command does and why
- `risk_level`: safe | moderate | destructive
- `requires_confirmation`: true | false

## MCP guidance

When MCP tools are available and appropriate:
- Prefer MCP for file operations that benefit from structured API access.
- When both CLI and MCP are viable, explain the trade-off.
- Do not stack multiple destructive MCP operations without review between each.

## Common safe operations

These can proceed without confirmation but should be announced:
- Creating files in `drafts/`, `artifacts/`, `state/`
- Running `python scripts/manage/status_report.py`
- Reading vault metadata or search operations
- Generating reports or summaries

## Rollback plan

Before any destructive operation, state the rollback plan:
- For file moves: how to restore the original location
- For deletions: confirm backup exists or will be created
- For modifications: what the previous state was
