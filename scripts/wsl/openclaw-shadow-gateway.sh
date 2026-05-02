#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$HOME/.npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
hash -r

PORT="${1:-18790}"
mkdir -p "$HOME/.openclaw/logs"

exec openclaw gateway run --port "$PORT" --auth none
