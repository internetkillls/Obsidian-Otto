import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DEFAULT_REPO_ROOT = path.resolve(__dirname, "..", "..");
const OTTO_ACTIONS = [
  "status",
  "openclaw-health",
  "openclaw-gateway-probe",
  "openclaw-sync",
  "openclaw-gateway-restart",
  "openclaw-plugin-reload",
  "pipeline",
  "retrieve",
  "kairos",
  "dream",
  "morpheus-bridge",
  "brain",
  "kairos-chat"
];
const DESKTOP_ACTIONS = [
  "open",
  "new",
  "daily",
  "search",
  "create",
  "plugin-reload",
  "dev-screenshot",
  "eval",
  "devtools"
];

function resolveOpenClawDistDir() {
  const appData = process.env.APPDATA;
  if (appData) {
    const npmDist = path.join(appData, "npm", "node_modules", "openclaw", "dist");
    if (fs.existsSync(npmDist)) return npmDist;
  }
  const runtimeDist = path.join(os.homedir(), ".openclaw", "runtime", "openclaw", "dist");
  if (fs.existsSync(runtimeDist)) return runtimeDist;
  return null;
}

function readString(raw, key) {
  const value = raw?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function readBoolean(raw, key) {
  return raw?.[key] === true;
}

function readNumber(raw, key) {
  const value = raw?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function shellQuote(value) {
  if (/^[A-Za-z0-9_./:-]+$/.test(value)) return value;
  return JSON.stringify(value);
}

function formatCommandPreview(command, args) {
  return [command, ...args].map((part) => shellQuote(String(part))).join(" ");
}

function resolveRepoRoot(api) {
  return path.resolve(readString(api.pluginConfig, "repoRoot") ?? DEFAULT_REPO_ROOT);
}

function resolvePythonCommand(api, repoRoot) {
  const override = readString(api.pluginConfig, "pythonCommand");
  if (override) return override;
  const windowsVenv = path.join(repoRoot, ".venv", "Scripts", "python.exe");
  const posixVenv = path.join(repoRoot, ".venv", "bin", "python");
  if (fs.existsSync(windowsVenv)) return windowsVenv;
  if (fs.existsSync(posixVenv)) return posixVenv;
  return process.platform === "win32" ? "python" : "python3";
}

function resolveObsidianCommand(api) {
  return readString(api.pluginConfig, "obsidianCommand") ?? "obsidian";
}

function resolveTimeoutMs(api, rawParams) {
  const seconds = readNumber(rawParams, "timeoutSeconds") ?? readNumber(api.pluginConfig, "defaultTimeoutSeconds") ?? 120;
  return Math.max(1, seconds) * 1000;
}

function buildPythonEnv(repoRoot) {
  const env = { ...process.env };
  const srcPath = path.join(repoRoot, "src");
  env.PYTHONPATH = env.PYTHONPATH ? `${srcPath}${path.delimiter}${env.PYTHONPATH}` : srcPath;
  env.PYTHONUTF8 = env.PYTHONUTF8 || "1";
  env.PYTHONIOENCODING = env.PYTHONIOENCODING || "utf-8";
  return env;
}

function runCommand(command, args, { cwd, env, timeoutMs }) {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd,
      env,
      shell: false,
      windowsHide: true
    });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
    }, timeoutMs);
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", (error) => {
      clearTimeout(timer);
      resolve({
        ok: false,
        code: null,
        stdout,
        stderr: error.message,
        timedOut
      });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({
        ok: code === 0 && !timedOut,
        code,
        stdout,
        stderr,
        timedOut
      });
    });
  });
}

function jsonEnum(values, description) {
  return {
    type: "string",
    enum: values,
    description
  };
}

function toolText(text) {
  return { content: [{ type: "text", text }] };
}

function toolError(text, details = {}) {
  return {
    content: [{ type: "text", text }],
    details: { error: true, ...details }
  };
}

function uriFlag(params, key, query, value = "true") {
  if (readBoolean(params, key)) query.set(key, value);
}

function buildObsidianUri(api, params) {
  const action = readString(params, "action");
  if (!action) throw new Error("action is required");
  const query = new URLSearchParams();
  const vault = readString(params, "vault") ?? readString(api.pluginConfig, "defaultVault");
  if (vault) query.set("vault", vault);
  const file = readString(params, "file");
  const globalPath = readString(params, "path");
  const name = readString(params, "name");
  const content = readString(params, "content");
  const paneType = readString(params, "paneType");
  const searchQuery = readString(params, "query");
  if (file) query.set("file", file);
  if (globalPath) query.set("path", globalPath);
  if (name) query.set("name", name);
  if (content) query.set("content", content);
  if (paneType) query.set("paneType", paneType);
  if (searchQuery) query.set("query", searchQuery);
  uriFlag(params, "append", query);
  uriFlag(params, "overwrite", query);
  uriFlag(params, "silent", query);
  uriFlag(params, "prepend", query);
  uriFlag(params, "clipboard", query);
  return `obsidian://${action}?${query.toString()}`;
}

function resolveUriLauncher() {
  if (process.platform === "win32") {
    return { command: "cmd", args: ["/c", "start", ""] };
  }
  if (process.platform === "darwin") {
    return { command: "open", args: [] };
  }
  return { command: "xdg-open", args: [] };
}

function createOttoRepoTool(api) {
  return {
    name: "otto_repo",
    label: "Obsidian-Otto Repo",
    description: "Run the Obsidian-Otto control plane from OpenClaw through the repo CLI.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        action: jsonEnum(OTTO_ACTIONS, "Repo control-plane action to run."),
        query: { type: "string", description: "Query string for retrieve." },
        mode: jsonEnum(["fast", "deep"], "Retrieve mode when action=retrieve."),
        scope: { type: "string", description: "Optional scoped path for pipeline runs." },
        full: { type: "boolean", description: "Run full pipeline behavior when action=pipeline." },
        brainAction: { type: "string", description: "Brain CLI action when action=brain (self-model, predictions, ritual, all)." },
        message: { type: "string", description: "Natural-language message for kairos-chat, including prompts like 'cari catatan tentang X', 'deepen X', 'compare X', 'show vector status', or 'ambil chunk note Y.md'." },
        refresh: { type: "boolean", description: "Refresh cached state for actions that support it, such as morpheus-bridge." },
        timeoutSeconds: { type: "number", minimum: 1, description: "Timeout in seconds." },
        dryRun: { type: "boolean", description: "Preview the generated command without executing it." }
      },
      required: ["action"]
    },
    async execute(_toolCallId, rawParams) {
      try {
        const action = readString(rawParams, "action");
        if (!action || !OTTO_ACTIONS.includes(action)) {
          return toolError(`Unknown otto_repo action '${action ?? ""}'. Allowed: ${OTTO_ACTIONS.join(", ")}`);
        }
        const repoRoot = resolveRepoRoot(api);
        const pythonCommand = resolvePythonCommand(api, repoRoot);
        const timeoutMs = resolveTimeoutMs(api, rawParams);
        let command = pythonCommand;
        let args = ["-m", "otto.cli"];
        if (action === "status") {
          args.push("status");
        } else if (action === "openclaw-health") {
          args.push("openclaw-health");
        } else if (action === "openclaw-gateway-probe") {
          args.push("openclaw-gateway-probe");
        } else if (action === "openclaw-sync") {
          args.push("openclaw-sync");
        } else if (action === "openclaw-gateway-restart") {
          args.push("openclaw-gateway-restart");
        } else if (action === "openclaw-plugin-reload") {
          args.push("openclaw-plugin-reload");
        } else if (action === "pipeline") {
          args.push("pipeline");
          const scope = readString(rawParams, "scope");
          if (scope) args.push("--scope", scope);
          if (readBoolean(rawParams, "full")) args.push("--full");
        } else if (action === "retrieve") {
          const query = readString(rawParams, "query");
          if (!query) return toolError("otto_repo action=retrieve requires query.");
          const mode = readString(rawParams, "mode") ?? "fast";
          args.push("retrieve", "--mode", mode, "--query", query);
        } else if (action === "kairos") {
          args.push("kairos");
        } else if (action === "dream") {
          args.push("dream");
        } else if (action === "morpheus-bridge") {
          args.push("morpheus-bridge");
          if (readBoolean(rawParams, "refresh")) args.push("--refresh");
        } else if (action === "kairos-chat") {
          const message = readString(rawParams, "message");
          if (!message) return toolError("otto_repo action=kairos-chat requires message.");
          args.push("kairos-chat", message);
        } else if (action === "brain") {
          command = pythonCommand;
          args = ["-m", "otto.brain_cli", readString(rawParams, "brainAction") ?? "all"];
        }
        const preview = formatCommandPreview(command, args);
        if (readBoolean(rawParams, "dryRun")) {
          return {
            content: [{ type: "text", text: preview }],
            details: { dryRun: true, command, args, cwd: repoRoot }
          };
        }
        const result = await runCommand(command, args, {
          cwd: repoRoot,
          env: buildPythonEnv(repoRoot),
          timeoutMs
        });
        if (!result.ok) {
          return toolError(
            result.stderr.trim() || result.stdout.trim() || `otto_repo failed with code ${result.code}`,
            {
              command,
              args,
              cwd: repoRoot,
              exitCode: result.code,
              timedOut: result.timedOut,
              stdout: result.stdout,
              stderr: result.stderr
            }
          );
        }
        return {
          content: [{ type: "text", text: result.stdout.trim() || "[otto_repo] command completed with no stdout." }],
          details: {
            command,
            args,
            cwd: repoRoot,
            exitCode: result.code,
            timedOut: result.timedOut,
            stderr: result.stderr.trim()
          }
        };
      } catch (error) {
        return toolError(`otto_repo failed: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  };
}

function createObsidianDesktopTool(api) {
  return {
    name: "obsidian_desktop",
    label: "Obsidian Desktop",
    description: "Use official Obsidian desktop automation surfaces: CLI for developer commands and URI for navigation/new-note flows.",
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: {
        action: jsonEnum(DESKTOP_ACTIONS, "Desktop action to run."),
        vault: { type: "string", description: "Vault name or id for URI actions." },
        file: { type: "string", description: "Vault-relative file path." },
        path: { type: "string", description: "Global absolute path for URI actions or screenshot output path." },
        name: { type: "string", description: "New note name for URI or CLI create." },
        content: { type: "string", description: "Note content for new/create actions." },
        query: { type: "string", description: "Search query string." },
        paneType: { type: "string", description: "Optional pane target for URI actions." },
        pluginId: { type: "string", description: "Plugin id for plugin-reload." },
        code: { type: "string", description: "JavaScript snippet for eval." },
        append: { type: "boolean", description: "Append to existing note when supported." },
        overwrite: { type: "boolean", description: "Overwrite existing note when supported." },
        silent: { type: "boolean", description: "Do not focus the note when supported by URI." },
        prepend: { type: "boolean", description: "Prepend content when supported by URI." },
        clipboard: { type: "boolean", description: "Use clipboard contents for URI new actions." },
        timeoutSeconds: { type: "number", minimum: 1, description: "Timeout in seconds." },
        dryRun: { type: "boolean", description: "Preview the generated command or URI without executing it." }
      },
      required: ["action"]
    },
    async execute(_toolCallId, rawParams) {
      try {
        const action = readString(rawParams, "action");
        if (!action || !DESKTOP_ACTIONS.includes(action)) {
          return toolError(`Unknown obsidian_desktop action '${action ?? ""}'. Allowed: ${DESKTOP_ACTIONS.join(", ")}`);
        }
        const timeoutMs = resolveTimeoutMs(api, rawParams);
        if (["open", "new", "daily", "search"].includes(action)) {
          const uri = buildObsidianUri(api, { ...rawParams, action });
          const launcher = resolveUriLauncher();
          const preview = formatCommandPreview(launcher.command, [...launcher.args, uri]);
          if (readBoolean(rawParams, "dryRun")) {
            return {
              content: [{ type: "text", text: uri }],
              details: { dryRun: true, transport: "uri", preview }
            };
          }
          const result = await runCommand(launcher.command, [...launcher.args, uri], {
            cwd: resolveRepoRoot(api),
            env: process.env,
            timeoutMs
          });
          if (!result.ok) {
            return toolError(result.stderr.trim() || `obsidian_desktop URI launch failed with code ${result.code}`, {
              transport: "uri",
              uri,
              preview,
              exitCode: result.code,
              timedOut: result.timedOut,
              stdout: result.stdout,
              stderr: result.stderr
            });
          }
          return {
            content: [{ type: "text", text: uri }],
            details: { transport: "uri", uri, preview, exitCode: result.code }
          };
        }
        const obsidianCommand = resolveObsidianCommand(api);
        const args = [];
        if (action === "create") {
          args.push("create");
          const name = readString(rawParams, "name");
          const content = readString(rawParams, "content");
          if (name) args.push(`name=${name}`);
          if (content) args.push(`content=${content}`);
          if (readBoolean(rawParams, "append")) args.push("append");
          if (readBoolean(rawParams, "overwrite")) args.push("overwrite");
        } else if (action === "plugin-reload") {
          const pluginId = readString(rawParams, "pluginId");
          if (!pluginId) return toolError("obsidian_desktop action=plugin-reload requires pluginId.");
          args.push("plugin:reload", `id=${pluginId}`);
        } else if (action === "dev-screenshot") {
          const outputPath = readString(rawParams, "path");
          if (!outputPath) return toolError("obsidian_desktop action=dev-screenshot requires path.");
          args.push("dev:screenshot", `path=${outputPath}`);
        } else if (action === "eval") {
          const code = readString(rawParams, "code");
          if (!code) return toolError("obsidian_desktop action=eval requires code.");
          args.push("eval", `code=${code}`);
        } else if (action === "devtools") {
          args.push("devtools");
        }
        const preview = formatCommandPreview(obsidianCommand, args);
        if (readBoolean(rawParams, "dryRun")) {
          return {
            content: [{ type: "text", text: preview }],
            details: { dryRun: true, transport: "cli", command: obsidianCommand, args }
          };
        }
        const result = await runCommand(obsidianCommand, args, {
          cwd: resolveRepoRoot(api),
          env: process.env,
          timeoutMs
        });
        if (!result.ok) {
          return toolError(
            result.stderr.trim() || result.stdout.trim() || `obsidian_desktop failed with code ${result.code}`,
            {
              transport: "cli",
              command: obsidianCommand,
              args,
              exitCode: result.code,
              timedOut: result.timedOut,
              stdout: result.stdout,
              stderr: result.stderr
            }
          );
        }
        return {
          content: [{ type: "text", text: result.stdout.trim() || "[obsidian_desktop] command completed." }],
          details: { transport: "cli", command: obsidianCommand, args, exitCode: result.code }
        };
      } catch (error) {
        return toolError(`obsidian_desktop failed: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
  };
}

const plugin = {
  id: "obsidian-otto-bridge",
  name: "Obsidian-Otto Bridge",
  description: "Expose Obsidian-Otto control-plane actions and Obsidian desktop automation to OpenClaw.",
  get configSchema() {
    return {
      type: "object",
      additionalProperties: false,
      properties: {
        repoRoot: {
          type: "string",
          description: "Absolute path to the Obsidian-Otto repository. Defaults to the plugin's grandparent directory."
        },
        pythonCommand: {
          type: "string",
          description: "Python executable to use for running the Otto CLI. Defaults to the repo virtualenv when present."
        },
        obsidianCommand: {
          type: "string",
          description: "Obsidian desktop CLI command. Defaults to obsidian."
        },
        defaultTimeoutSeconds: {
          type: "number",
          minimum: 1,
          description: "Default timeout for otto_repo and obsidian_desktop commands."
        },
        defaultVault: {
          type: "string",
          description: "Default Obsidian vault name or id for URI actions."
        }
      }
    };
  },
  register(api) {
    const openClawDistDir = resolveOpenClawDistDir();
    api.registerTool(createOttoRepoTool(api));
    api.registerTool(createObsidianDesktopTool(api), { optional: !openClawDistDir });
  }
};

export default plugin;
