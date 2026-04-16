#!/usr/bin/env bash

# read-markdown.sh shell wrapper: keeps the function-based interface source-compatible
# while delegating orchestration logic to the Python entrypoint.

set -e

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRYPOINT="$SCRIPT_DIR/read_markdown.py"

_run_read_markdown_entrypoint() {
    if [[ ! -f "$ENTRYPOINT" ]]; then
        echo "ERROR: Missing Python read-markdown entrypoint at $ENTRYPOINT" >&2
        return 1
    fi

    if command -v uv >/dev/null 2>&1; then
        uv run --no-sync python "$ENTRYPOINT" "$@"
    else
        python3 "$ENTRYPOINT" "$@"
    fi
}

read_markdown_section() {
    _run_read_markdown_entrypoint "$@"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    read_markdown_section "$@"
fi
