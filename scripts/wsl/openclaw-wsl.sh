#!/usr/bin/env bash
set -euo pipefail

HOME="/home/joshu"
export HOME
export PATH="/home/joshu/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

OPENCLAW_BIN="/home/joshu/.npm-global/bin/openclaw"
if [[ ! -x "$OPENCLAW_BIN" ]]; then
  echo "openclaw binary is missing or not executable: $OPENCLAW_BIN" >&2
  exit 127
fi

exec "$OPENCLAW_BIN" "$@"
