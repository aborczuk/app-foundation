#!/usr/bin/env bash

# read-markdown.sh shell wrapper: keeps the function-based interface source-compatible
# while delegating orchestration logic to the Python entrypoint.
#
# How to use:
#   source scripts/read-markdown.sh
#   read_markdown_headings <file>
#   read_markdown_section <file> <section_heading>
#
# The Python entrypoint carries the detailed progressive-load contract.

set -e

SOURCE_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(CDPATH="" cd "$(dirname "$SOURCE_PATH")" && pwd)"
# When sourced from zsh, BASH_SOURCE can be empty and $0 is the shell name.
# In that case, SCRIPT_DIR becomes CWD; normalize to ./scripts if present.
if [[ ! -f "$SCRIPT_DIR/read-markdown.sh" && -f "$SCRIPT_DIR/scripts/read-markdown.sh" ]]; then
    SCRIPT_DIR="$SCRIPT_DIR/scripts"
fi
ENTRYPOINT="$SCRIPT_DIR/read_markdown.py"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_UV_CACHE_DIR="$REPO_ROOT/.codegraphcontext/.uv-cache"

_run_read_markdown_entrypoint() {
    if [[ ! -f "$ENTRYPOINT" ]]; then
        echo "ERROR: Missing Python read-markdown entrypoint at $ENTRYPOINT" >&2
        return 1
    fi

    if command -v uv >/dev/null 2>&1; then
        if [[ -z "${UV_CACHE_DIR:-}" ]]; then
            export UV_CACHE_DIR="$DEFAULT_UV_CACHE_DIR"
        fi
        mkdir -p "$UV_CACHE_DIR"
        uv run --no-sync python "$ENTRYPOINT" "$@"
    else
        python3 "$ENTRYPOINT" "$@"
    fi
}

read_markdown_section() {
    _run_read_markdown_entrypoint "$@"
}

read_markdown_headings() {
    _run_read_markdown_entrypoint --headings "$@"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ "${1:-}" == "--headings" ]]; then
        shift
        read_markdown_headings "$@"
    else
        read_markdown_section "$@"
    fi
fi
