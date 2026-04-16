#!/usr/bin/env bash
# Run the CodeGraph doctor against the repository and surface index health.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"
exec uv run python -m src.mcp_codebase.doctor "$@"
