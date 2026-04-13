#!/usr/bin/env node
/**
 * Otto Obsidian MCP Server
 *
 * Wraps @modelcontextprotocol/server-obsidian.
 * Reads OBSIDIAN_VAULT_PATH from env, passes to the official server.
 *
 * Usage:
 *   node dist/index.js
 *   (stdio mode — connects to OpenClaw via stdin/stdout)
 */

import { ObsidianMcpServer } from "@modelcontextprotocol/server-obsidian";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const vaultPath = process.env.OBSIDIAN_VAULT_PATH;

if (!vaultPath) {
  console.error("OBSIDIAN_VAULT_PATH environment variable is required");
  process.exit(1);
}

async function main() {
  const transport = new StdioServerTransport();
  const server = new ObsidianMcpServer({ vaultPath });
  await server.connect(transport);
}

main().catch((err) => {
  console.error("Obsidian MCP server failed:", err);
  process.exit(1);
});
