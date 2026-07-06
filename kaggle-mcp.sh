#!/bin/bash
# kaggle-mcp — Launch the Kaggle MCP Server
#
# Usage:
#   ./kaggle-mcp --stdio           # For Claude Code / Codex CLI / Cursor
#   ./kaggle-mcp --port 8234       # For HTTP SSE clients
#   ./kaggle-mcp --help            # Show tools & help
#
# Environment:
#   KAGGLE_USERNAME    Your Kaggle username
#   KAGGLE_KEY         Your API key (or paste from kaggle.json)
#
# Load from .env if present
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$DIR/.env" ]; then
  set -a
  source "$DIR/.env"
  set +a
fi

exec python "$DIR/kaggle_mcp.py" "$@"
