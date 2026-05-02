#!/usr/bin/env bash
set -euo pipefail

HOME="/home/joshu"
export HOME
export PATH="/home/joshu/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

REPO_ROOT="/mnt/c/Users/joshu/Obsidian-Otto"
cd "$REPO_ROOT"

export PYTHONPATH="src"

exec python3 -m otto.cli "$@"
