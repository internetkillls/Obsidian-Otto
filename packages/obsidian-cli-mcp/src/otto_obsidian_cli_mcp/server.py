"""
Otto Obsidian CLI MCP Server.

Wraps Obsidian vault CLI operations as MCP tools.
Connects via stdio to OpenClaw.

Env:
    OBSIDIAN_VAULT_PATH: Path to the Obsidian vault (inside container or host)
    OBSIDIAN_CLI_PATH:   Path to obsidian CLI binary (optional, searches PATH)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


APP = Server("otto-obsidian-cli-mcp")


def _vault_path() -> Path:
    vault = os.environ.get("OBSIDIAN_VAULT_PATH")
    if not vault:
        raise RuntimeError("OBSIDIAN_VAULT_PATH is not set")
    return Path(vault).expanduser().resolve()


def _find_cli() -> Path:
    cli = os.environ.get("OBSIDIAN_CLI_PATH")
    if cli and Path(cli).exists():
        return Path(cli)
    found = shutil.which("obsidian")
    if found:
        return Path(found)
    raise RuntimeError("obsidian CLI not found in PATH and OBSIDIAN_CLI_PATH not set")


@APP.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="vault_search",
            description="Search Obsidian vault notes using obsidian CLI",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "vault": {"type": "string", "description": "Vault name (optional)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="vault_run_command",
            description="Run an Obsidian CLI command against the vault",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "CLI command to run"},
                    "vault": {"type": "string", "description": "Vault name (optional)"},
                },
                "required": ["command"],
            },
        ),
    ]


@APP.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    vault = _vault_path()
    cli = _find_cli()

    if name == "vault_search":
        query = arguments["query"]
        cmd = [str(cli), "search", "--vault", str(vault), query]
    elif name == "vault_run_command":
        cmd_str = arguments["command"]
        cmd = [str(cli), "--vault", str(vault)] + cmd_str.split()
    else:
        raise ValueError(f"Unknown tool: {name}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    output = result.stdout if result.returncode == 0 else f"ERROR: {result.stderr}"
    return [TextContent(type="text", text=output)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await APP.run(read_stream, write_stream, APP.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
