#!/usr/bin/env bash

# read-code.sh shell wrapper: keeps function-based usage source-compatible
# while delegating orchestration logic to the Python entrypoint.

set -e

SOURCE_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
# When sourced from zsh, BASH_SOURCE can be empty and $0 is the shell name.
# In that case, SCRIPT_DIR becomes CWD; normalize to ./scripts if present.
if [[ ! -f "$SCRIPT_DIR/read-code.sh" && -f "$SCRIPT_DIR/scripts/read-code.sh" ]]; then
    SCRIPT_DIR="$SCRIPT_DIR/scripts"
fi

ENTRYPOINT="$SCRIPT_DIR/read_code.py"

_run_read_code_entrypoint() {
    if [[ ! -f "$ENTRYPOINT" ]]; then
        echo "ERROR: Missing Python read-code entrypoint at $ENTRYPOINT" >&2
        return 1
    fi

    if command -v uv >/dev/null 2>&1; then
        uv run --no-sync python "$ENTRYPOINT" "$@"
    else
        python3 "$ENTRYPOINT" "$@"
    fi
}

read_code_context() {
    _run_read_code_entrypoint context "$@"
}

read_code_window() {
    _run_read_code_entrypoint window "$@"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    _run_read_code_entrypoint "$@"
fi
