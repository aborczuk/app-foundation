#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH="" cd "$SCRIPT_DIR/../../.." && pwd)"
ENTRYPOINT="$REPO_ROOT/.specify/scripts/python/create_new_feature.py"

if [[ ! -f "$ENTRYPOINT" ]]; then
    echo "ERROR: Missing Python create-new-feature entrypoint at $ENTRYPOINT" >&2
    exit 1
fi

exec python3 "$ENTRYPOINT" "$@"
