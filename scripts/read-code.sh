#!/bin/bash

# read-code.sh: Enforce symbol-first, windowed reads for large code files.
#
# MANDATORY: For code files >200 lines, read through this helper.
# This script enforces the Code File Read Efficiency rule from CLAUDE.md:
# "Use codegraph for discovery first, then read only bounded windows."
#
# Usage:
#   read_code_context <file_path> <symbol_or_pattern> [context_lines]
#   read_code_window  <file_path> <start_line> [line_count] [symbol_or_pattern]
#
# Examples:
#   read_code_context src/module.py "def run_pipeline" 80
#   read_code_window src/module.py 120 60 "run_pipeline"

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CODEGRAPH_CONTEXT_DIR="$REPO_ROOT/.codegraphcontext"
CODEGRAPH_DB_DIR="$CODEGRAPH_CONTEXT_DIR/db"

CODE_FILE_LINE_THRESHOLD=200
IGNORE_DIRS_DEFAULT="node_modules,venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,__pycache__,.uv-cache,logs,shadow-runs"

init_codegraph_env() {
    local repo_uv_cache="${CGC_UV_CACHE_DIR:-$CODEGRAPH_CONTEXT_DIR/.uv-cache}"
    mkdir -p "$CODEGRAPH_DB_DIR" "$repo_uv_cache"

    export UV_CACHE_DIR="$repo_uv_cache"
    export DEFAULT_DATABASE="${DEFAULT_DATABASE:-kuzudb}"
    export FALKORDB_PATH="${FALKORDB_PATH:-$CODEGRAPH_DB_DIR/falkordb}"
    export FALKORDB_SOCKET_PATH="${FALKORDB_SOCKET_PATH:-$CODEGRAPH_DB_DIR/falkordb.sock}"
    export KUZUDB_PATH="${KUZUDB_PATH:-$CODEGRAPH_DB_DIR/kuzudb}"
    export IGNORE_DIRS="${IGNORE_DIRS:-$IGNORE_DIRS_DEFAULT}"
}

codegraph_discover_or_fail() {
    local pattern="$1"
    local scope_path="${2:-$REPO_ROOT}"

    if [[ -z "$pattern" ]]; then
        echo "ERROR: codegraph discovery requires a non-empty symbol_or_pattern" >&2
        return 1
    fi

    if ! command -v uv >/dev/null 2>&1; then
        echo "ERROR: uv is required for codegraph discovery (uv run cgc ...)" >&2
        return 1
    fi

    init_codegraph_env

    local output
    if ! output="$(uv run --no-sync cgc find pattern "$pattern" 2>&1)"; then
        # Self-heal common index fragility by rebuilding a scoped index once.
        if [[ "$output" == *"Database Connection Error"* || "$output" == *"No index metadata"* ]]; then
            if [[ -x "$SCRIPT_DIR/cgc_safe_index.sh" ]]; then
                "$SCRIPT_DIR/cgc_safe_index.sh" "$scope_path" >/dev/null 2>&1 || true
                if output="$(uv run --no-sync cgc find pattern "$pattern" 2>&1)"; then
                    :
                else
                    echo "ERROR: codegraph discovery failed for pattern: $pattern" >&2
                    echo "Hint: run scripts/cgc_safe_index.sh <scoped-path> and retry." >&2
                    echo "$output" | tail -20 >&2
                    return 1
                fi
            else
                echo "ERROR: codegraph discovery failed for pattern: $pattern" >&2
                echo "Hint: run scripts/cgc_safe_index.sh <scoped-path> and retry." >&2
                echo "$output" | tail -20 >&2
                return 1
            fi
        else
            echo "ERROR: codegraph discovery failed for pattern: $pattern" >&2
            echo "Hint: run scripts/cgc_safe_index.sh <scoped-path> and retry." >&2
            echo "$output" | tail -20 >&2
            return 1
        fi
    fi

    if [[ "$output" == *"No matches found for pattern"* ]]; then
        echo "WARN: codegraph found no matches for '$pattern'; proceeding with file-local window read." >&2
    fi

    return 0
}

is_large_code_file() {
    local file="$1"
    local lines
    lines="$(wc -l < "$file" | tr -d ' ')"
    [[ "$lines" -gt "$CODE_FILE_LINE_THRESHOLD" ]]
}

read_code_context() {
    local file="$1"
    local pattern="$2"
    local context="${3:-60}"

    if [[ -z "$file" || -z "$pattern" ]]; then
        echo "ERROR: read_code_context requires: <file_path> <symbol_or_pattern> [context_lines]" >&2
        return 1
    fi

    if [[ ! -f "$file" ]]; then
        echo "ERROR: File not found: $file" >&2
        return 1
    fi

    if ! [[ "$context" =~ ^[0-9]+$ ]] || [[ "$context" -le 0 ]]; then
        echo "ERROR: context_lines must be a positive integer: $context" >&2
        return 1
    fi

    codegraph_discover_or_fail "$pattern" "$(dirname "$file")"

    local line_num
    if command -v rg >/dev/null 2>&1; then
        line_num="$(rg -n -m 1 -F -- "$pattern" "$file" | cut -d: -f1)"
    else
        line_num="$(grep -n -m 1 -F -- "$pattern" "$file" | cut -d: -f1)"
    fi

    if [[ -z "$line_num" ]]; then
        echo "ERROR: Pattern not found: $pattern in $file" >&2
        return 1
    fi

    local start=$((line_num - context))
    local end=$((line_num + context))
    if [[ "$start" -lt 1 ]]; then
        start=1
    fi

    nl -ba "$file" | sed -n "${start},${end}p"
    return 0
}

read_code_window() {
    local file="$1"
    local start_line="$2"
    local line_count="${3:-60}"
    local pattern="${4:-}"

    if [[ -z "$file" || -z "$start_line" ]]; then
        echo "ERROR: read_code_window requires: <file_path> <start_line> [line_count]" >&2
        return 1
    fi

    if [[ ! -f "$file" ]]; then
        echo "ERROR: File not found: $file" >&2
        return 1
    fi

    if ! [[ "$start_line" =~ ^[0-9]+$ ]] || [[ "$start_line" -le 0 ]]; then
        echo "ERROR: start_line must be a positive integer: $start_line" >&2
        return 1
    fi

    if ! [[ "$line_count" =~ ^[0-9]+$ ]] || [[ "$line_count" -le 0 ]]; then
        echo "ERROR: line_count must be a positive integer: $line_count" >&2
        return 1
    fi

    if is_large_code_file "$file"; then
        if [[ -z "$pattern" ]]; then
            echo "ERROR: symbol_or_pattern is required for files >${CODE_FILE_LINE_THRESHOLD} lines." >&2
            echo "Usage: read_code_window <file> <start_line> [line_count] <symbol_or_pattern>" >&2
            return 1
        fi
        codegraph_discover_or_fail "$pattern" "$(dirname "$file")"
    fi

    local end_line=$((start_line + line_count - 1))
    nl -ba "$file" | sed -n "${start_line},${end_line}p"
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ "$#" -lt 3 ]]; then
        echo "Usage:"
        echo "  read_code_context <file_path> <symbol_or_pattern> [context_lines]"
        echo "  read_code_window  <file_path> <start_line> [line_count] [symbol_or_pattern]"
        exit 1
    fi

    mode="$1"
    shift
    case "$mode" in
        context)
            read_code_context "$@"
            ;;
        window)
            read_code_window "$@"
            ;;
        *)
            echo "ERROR: Unknown mode '$mode'. Use: context | window" >&2
            exit 1
            ;;
    esac
fi
