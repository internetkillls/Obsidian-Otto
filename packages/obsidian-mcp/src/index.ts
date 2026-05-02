#!/usr/bin/env node
/**
 * Otto Obsidian MCP Server.
 *
 * Implements read-only Obsidian file operations as MCP tools.
 * Connects via stdio to OpenClaw.
 *
 * Env:
 *   OBSIDIAN_VAULT_PATH: Absolute path to the Obsidian vault on the host.
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import * as fs from "fs";
import * as path from "path";

const VAULT_PATH = process.env.OBSIDIAN_VAULT_PATH;

if (!VAULT_PATH) {
  console.error("OBSIDIAN_VAULT_PATH environment variable is required");
  process.exit(1);
}

if (!fs.existsSync(VAULT_PATH)) {
  console.error(`Vault path does not exist: ${VAULT_PATH}`);
  process.exit(1);
}

const RESOLVED_VAULT_PATH: string = VAULT_PATH;

const SERVER = new Server(
  { name: "otto-obsidian-mcp", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

type ToolArgs = Record<string, unknown>;

function requireString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${field} is required`);
  }
  return value;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function optionalNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

SERVER.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "obsidian_read_note",
      description: "Read the contents of an Obsidian note by its relative path",
      inputSchema: {
        type: "object",
        properties: {
          relativePath: {
            type: "string",
            description: "Relative path to the note from the vault root (e.g. 'Daily/2024-01-15.md')",
          },
        },
        required: ["relativePath"],
      },
    },
    {
      name: "obsidian_search_notes",
      description: "Full-text search across all Obsidian notes in the vault",
      inputSchema: {
        type: "object",
        properties: {
          query: {
            type: "string",
            description: "Search query string",
          },
          limit: {
            type: "number",
            description: "Maximum number of results (default 10)",
          },
        },
        required: ["query"],
      },
    },
    {
      name: "obsidian_list_notes",
      description: "List all markdown notes in a vault subdirectory",
      inputSchema: {
        type: "object",
        properties: {
          subdirectory: {
            type: "string",
            description: "Subdirectory relative to vault root (default: entire vault)",
          },
          limit: {
            type: "number",
            description: "Maximum number of results (default 50)",
          },
        },
      },
    },
  ],
}));

function readNote(relativePath: string): string {
  const fullPath = path.join(RESOLVED_VAULT_PATH, relativePath);
  if (!fullPath.startsWith(RESOLVED_VAULT_PATH)) {
    throw new Error("Path traversal denied");
  }
  if (!fs.existsSync(fullPath)) {
    throw new Error(`Note not found: ${relativePath}`);
  }
  return fs.readFileSync(fullPath, "utf-8");
}

function searchNotes(query: string, limit: number = 10): string {
  const q = query.toLowerCase();
  const results: string[] = [];

  function walk(dir: string): void {
    if (results.length >= limit) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (results.length >= limit) break;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile() && entry.name.endsWith(".md")) {
        const content = fs.readFileSync(full, "utf-8");
        if (content.toLowerCase().includes(q)) {
          const rel = path.relative(RESOLVED_VAULT_PATH, full);
          results.push(`## [[${rel}]]\n${content.slice(0, 500)}...\n`);
        }
      }
    }
  }

  walk(RESOLVED_VAULT_PATH);
  return results.length ? results.join("\n---\n") : "No matches found.";
}

function listNotes(subdirectory?: string, limit: number = 50): string {
  const root = subdirectory ? path.join(RESOLVED_VAULT_PATH, subdirectory) : RESOLVED_VAULT_PATH;
  if (!root.startsWith(RESOLVED_VAULT_PATH)) {
    throw new Error("Path traversal denied");
  }
  if (!fs.existsSync(root)) {
    throw new Error(`Directory not found: ${subdirectory ?? "."}`);
  }

  const notes: string[] = [];
  function walk(dir: string): void {
    if (notes.length >= limit) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (notes.length >= limit) break;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile() && entry.name.endsWith(".md")) {
        notes.push(path.relative(RESOLVED_VAULT_PATH, full));
      }
    }
  }
  walk(root);
  return notes.join("\n");
}

SERVER.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  const toolArgs: ToolArgs = args ?? {};

  try {
    let result: string;

    if (name === "obsidian_read_note") {
      result = readNote(requireString(toolArgs.relativePath, "relativePath"));
    } else if (name === "obsidian_search_notes") {
      result = searchNotes(
        requireString(toolArgs.query, "query"),
        optionalNumber(toolArgs.limit, 10)
      );
    } else if (name === "obsidian_list_notes") {
      result = listNotes(
        optionalString(toolArgs.subdirectory),
        optionalNumber(toolArgs.limit, 50)
      );
    } else {
      throw new Error(`Unknown tool: ${name}`);
    }

    return { content: [{ type: "text", text: result }] };
  } catch (err) {
    return { content: [{ type: "text", text: `ERROR: ${(err as Error).message}` }], isError: true };
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await SERVER.connect(transport);
}

main().catch((err) => {
  console.error("Otto Obsidian MCP server failed:", err);
  process.exit(1);
});
