#!/usr/bin/env node
"use strict";

const { spawnSync } = require("node:child_process");

const distro = (process.env.OTTO_QMD_WSL_DISTRO || "Ubuntu").trim() || "Ubuntu";
const qmdPath = (process.env.OTTO_QMD_WSL_QMD_PATH || "/usr/bin/qmd").trim() || "/usr/bin/qmd";
const args = process.argv.slice(2);

function windowsPathToWsl(value) {
  const pseudoWslMatch = /^[A-Za-z]:[\\/]mnt[\\/]([A-Za-z])[\\/](.*)$/.exec(value);
  if (pseudoWslMatch) {
    const drive = pseudoWslMatch[1].toLowerCase();
    const rest = pseudoWslMatch[2].replace(/\\/g, "/");
    return `/mnt/${drive}/${rest}`;
  }

  const match = /^([A-Za-z]):[\\/](.*)$/.exec(value);
  if (!match) return value;
  const drive = match[1].toLowerCase();
  const rest = match[2].replace(/\\/g, "/");
  return `/mnt/${drive}/${rest}`;
}

const envArgs = [
  "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
];

for (const key of ["XDG_CONFIG_HOME", "QMD_CONFIG_DIR", "XDG_CACHE_HOME"]) {
  const value = process.env[key];
  if (value) envArgs.push(`${key}=${windowsPathToWsl(value)}`);
}

if (process.env.NO_COLOR) envArgs.push("NO_COLOR=1");

const translatedArgs = args.map(windowsPathToWsl);

const result = spawnSync("wsl.exe", ["-d", distro, "--", "env", ...envArgs, qmdPath, ...translatedArgs], {
  encoding: "utf8",
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});

if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);

if (result.error) {
  process.stderr.write(`${result.error.message}\n`);
  process.exit(1);
}

process.exit(result.status ?? (result.signal ? 1 : 0));
