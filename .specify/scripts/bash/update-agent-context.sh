#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH="" cd "$SCRIPT_DIR/../../.." && pwd)"
ENTRYPOINT="$REPO_ROOT/.specify/scripts/python/update_agent_context.py"

if [[ ! -f "$ENTRYPOINT" ]]; then
    echo "ERROR: Missing Python update-agent-context entrypoint at $ENTRYPOINT" >&2
    exit 1
fi

if command -v uv >/dev/null 2>&1; then
    exec uv run --no-sync python "$ENTRYPOINT" "$@"
else
    exec python3 "$ENTRYPOINT" "$@"
fi
