#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
hash -r

REPO_ROOT="${OTTO_REPO_ROOT:-/mnt/c/Users/joshu/Obsidian-Otto}"
VAULT_PATH="${OTTO_VAULT_PATH:-/mnt/c/Users/joshu/Josh Obsidian}"

export OTTO_REPO_ROOT="$REPO_ROOT"
export OTTO_VAULT_PATH="$VAULT_PATH"
export OBSIDIAN_VAULT_HOST="${OBSIDIAN_VAULT_HOST:-$VAULT_PATH}"
export OBSIDIAN_VAULT_PATH="${OBSIDIAN_VAULT_PATH:-/vault}"
export OTTO_SQLITE_PATH="${OTTO_SQLITE_PATH:-external/sqlite/otto_silver.db}"
export OTTO_CHROMA_PATH="${OTTO_CHROMA_PATH:-external/chroma_store}"
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

require_native_openclaw() {
  local bin
  bin="$(command -v openclaw || true)"

  if [[ -z "$bin" ]]; then
    echo "OpenClaw is not installed natively inside Ubuntu WSL." >&2
    return 127
  fi

  case "$bin" in
    /mnt/c/*|*WindowsApps*|*.exe|*.EXE)
      echo "Refusing Windows OpenClaw from WSL PATH: $bin" >&2
      echo "Install native OpenClaw inside Ubuntu or fix PATH quarantine." >&2
      return 127
      ;;
  esac

  echo "$bin"
}

if [[ $# -eq 0 ]]; then
  set -- wsl-health
fi

case "${1:-}" in
  openclaw-doctor)
    shift
    OPENCLAW_BIN="$(require_native_openclaw)" || exit $?
    exec "$OPENCLAW_BIN" doctor --non-interactive "$@"
    ;;
  openclaw-memory)
    shift
    OPENCLAW_BIN="$(require_native_openclaw)" || exit $?
    exec "$OPENCLAW_BIN" memory status --deep "$@"
    ;;
  *)
    cd "$REPO_ROOT"
    exec python3 -m otto.cli "$@"
    ;;
esac
