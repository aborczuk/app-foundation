#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH="" cd "$SCRIPT_DIR/../../.." && pwd)"
ENTRYPOINT="$REPO_ROOT/.specify/scripts/python/check_prerequisites.py"

if [[ ! -f "$ENTRYPOINT" ]]; then
    echo "ERROR: Missing Python check-prerequisites entrypoint at $ENTRYPOINT" >&2
    exit 1
fi

exec python3 "$ENTRYPOINT" "$@"
