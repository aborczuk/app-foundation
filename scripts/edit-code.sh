#!/usr/bin/env bash

# edit-code.sh wrapper: source-compatible helper functions that delegate
# deterministic workflow logic to the Python entrypoint.

set -e

SOURCE_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/edit-code.sh" && -f "$SCRIPT_DIR/scripts/edit-code.sh" ]]; then
    SCRIPT_DIR="$SCRIPT_DIR/scripts"
fi

ENTRYPOINT="$SCRIPT_DIR/edit_code.py"

_run_edit_code_entrypoint() {
    if [[ ! -f "$ENTRYPOINT" ]]; then
        echo "ERROR: Missing Python edit-code entrypoint at $ENTRYPOINT" >&2
        return 1
    fi

    if command -v uv >/dev/null 2>&1; then
        uv run --no-sync python "$ENTRYPOINT" "$@"
    else
        python3 "$ENTRYPOINT" "$@"
    fi
}

edit_validate() {
    _run_edit_code_entrypoint validate "$@"
}

edit_refresh() {
    _run_edit_code_entrypoint refresh "$@"
}

edit_sync() {
    _run_edit_code_entrypoint sync "$@"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    _run_edit_code_entrypoint "$@"
fi
