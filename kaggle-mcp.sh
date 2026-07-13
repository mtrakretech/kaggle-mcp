#!/usr/bin/env bash
# Launch Kaggle MCP Server
# Usage:
#   ./kaggle-mcp.sh --setup
#   ./kaggle-mcp.sh --stdio
#   ./kaggle-mcp.sh --port 8234
#   ./kaggle-mcp.sh --list-tools
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$DIR/.env"
  set +a
fi
if [[ -n "${KAGGLE_KEY:-}" && -z "${KAGGLE_API_TOKEN:-}" ]]; then
  export KAGGLE_API_TOKEN="$KAGGLE_KEY"
fi
exec python3 "$DIR/kaggle_mcp.py" "$@"
