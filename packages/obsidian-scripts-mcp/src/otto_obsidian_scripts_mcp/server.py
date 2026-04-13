"""
Otto Obsidian Scripts MCP Server.

Wraps Otto's own Python scripts (scripts/manage/*.py) as MCP tools.
These are the actual vault CLI operations — NOT a standalone obsidian binary.

Connects via stdio to OpenClaw.

Env:
    OTTO_REPO_PATH: Absolute path to the Otto repo inside the container (default: /otto)
    OTTO_SCRIPTS_PATH: Path to scripts/manage inside the repo (default: /otto/scripts/manage)
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


APP = Server("otto-obsidian-scripts-mcp")


def _otto_repo() -> Path:
    repo = os.environ.get("OTTO_REPO_PATH")
    if not repo:
        raise RuntimeError("OTTO_REPO_PATH is not set")
    p = Path(repo).expanduser().resolve()
    if not p.exists():
        raise RuntimeError(f"OTTO_REPO_PATH does not exist: {repo}")
    return p


def _scripts_dir() -> Path:
    scripts = os.environ.get("OTTO_SCRIPTS_PATH")
    if scripts:
        return Path(scripts)
    return _otto_repo() / "scripts" / "manage"


def _run_script(script_name: str, args: list[str] | None = None) -> str:
    repo = _otto_repo()
    scripts = _scripts_dir()
    script_path = scripts / script_name

    if not script_path.exists():
        raise RuntimeError(f"Script not found: {script_path}")

    cmd = [sys.executable, str(script_path)] + (args or [])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONPATH": str(repo / "src")},
        cwd=str(repo),
    )
    if result.returncode != 0:
        return f"ERROR (exit {result.returncode}): {result.stderr or result.stdout}"
    return result.stdout or "(no output)"


@APP.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="otto_status_report",
            description="Run Otto status report — returns pipeline state, vault info, OpenClaw health",
            inputSchema={
                "type": "object",
                "properties": {
                    "json": {"type": "boolean", "description": "Output as JSON (default true)"},
                },
            },
        ),
        Tool(
            name="otto_run_pipeline",
            description="Run the Otto Bronze/Silver/Gold pipeline",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "description": "Vault scope (subdirectory, optional)"},
                    "dry_run": {"type": "boolean", "description": "Dry run without writing state"},
                },
            },
        ),
        Tool(
            name="otto_query_memory",
            description="Query Otto memory (Silver SQLite) for notes matching a query",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "number", "description": "Max results (default 8)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="otto_run_kairos",
            description="Run Otto KAIROS telemetry — evaluates signals and updates strategy",
            inputSchema={
                "type": "object",
                "properties": {
                    "dry_run": {"type": "boolean", "description": "Dry run without writing state"},
                },
            },
        ),
    ]


@APP.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "otto_status_report":
            args = ["--json"] if arguments.get("json", True) else []
            output = _run_script("status_report.py", args)
        elif name == "otto_run_pipeline":
            args = []
            if arguments.get("dry_run"):
                args.append("--dry-run")
            scope = arguments.get("scope")
            if scope:
                args.extend(["--scope", scope])
            output = _run_script("run_pipeline.py", args)
        elif name == "otto_query_memory":
            args = [arguments["query"]]
            limit = arguments.get("limit", 8)
            args.extend(["--limit", str(limit)])
            output = _run_script("query_memory.py", args)
        elif name == "otto_run_kairos":
            args = ["--json"] + (["--dry-run"] if arguments.get("dry_run") else [])
            output = _run_script("run_kairos.py", args)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return [TextContent(type="text", text=output)]
    except Exception as exc:
        return [TextContent(type="text", text=f"ERROR: {exc}"), TextContent(type="text", text="", isError=True)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await APP.run(read_stream, write_stream, APP.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
