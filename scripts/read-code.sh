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
# Optional HUD fast-path:
#   add --hud-symbol (or set SPECKIT_HUD_DIRECT_READ=1) to skip codegraph
#   discovery when the symbol came directly from a trusted HUD file:symbol entry.
#
# Examples:
#   read_code_context src/module.py "def run_pipeline" 80
#   read_code_window src/module.py 120 60 "run_pipeline"

set -e

SOURCE_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SOURCE_PATH")" && pwd)"
# When sourced from zsh, BASH_SOURCE can be empty and $0 is the shell name.
# In that case, SCRIPT_DIR becomes CWD; normalize to ./scripts if present.
if [[ ! -f "$SCRIPT_DIR/read-code.sh" && -f "$SCRIPT_DIR/scripts/read-code.sh" ]]; then
    SCRIPT_DIR="$SCRIPT_DIR/scripts"
fi
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CODEGRAPH_CONTEXT_DIR="$REPO_ROOT/.codegraphcontext"
CODEGRAPH_DB_DIR="$CODEGRAPH_CONTEXT_DIR/db"

CODE_FILE_LINE_THRESHOLD=200
READ_CODE_DEFAULT_CONTEXT_LINES=60
READ_CODE_DEFAULT_WINDOW_LINES=60
READ_CODE_MAX_LINES="${SPECKIT_READ_CODE_MAX_LINES:-80}"
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
    if ! output="$(uv run --no-sync cgc find pattern -- "$pattern" 2>&1)"; then
        # Self-heal common index fragility by rebuilding a scoped index once.
        if [[ "$output" == *"Database Connection Error"* || "$output" == *"No index metadata"* ]]; then
            if [[ -x "$SCRIPT_DIR/cgc_safe_index.sh" ]]; then
                "$SCRIPT_DIR/cgc_safe_index.sh" "$scope_path" >/dev/null 2>&1 || true
                if output="$(uv run --no-sync cgc find pattern -- "$pattern" 2>&1)"; then
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

normalize_symbol_pattern() {
    local raw="$1"
    local normalized="$raw"
    normalized="${normalized#"${normalized%%[![:space:]]*}"}"
    normalized="${normalized%"${normalized##*[![:space:]]}"}"
    normalized="${normalized#async def }"
    normalized="${normalized#def }"
    normalized="${normalized#class }"
    normalized="${normalized%%(*}"
    normalized="${normalized%%:*}"
    normalized="${normalized%%[[:space:]]*}"
    echo "$normalized"
}

_find_line_num() {
    local file="$1"
    local raw_pattern="$2"
    local normalized_pattern="$3"
    local line_num=""

    if command -v rg >/dev/null 2>&1; then
        if [[ -n "$raw_pattern" ]]; then
            line_num="$(rg -n -m 1 -F -- "$raw_pattern" "$file" | cut -d: -f1)"
        fi
        if [[ -z "$line_num" && -n "$normalized_pattern" && "$normalized_pattern" != "$raw_pattern" ]]; then
            line_num="$(rg -n -m 1 -F -- "$normalized_pattern" "$file" | cut -d: -f1)"
        fi
        if [[ -z "$line_num" && -n "$normalized_pattern" ]]; then
            line_num="$(rg -n -m 1 -F -- "def $normalized_pattern" "$file" | cut -d: -f1)"
        fi
        if [[ -z "$line_num" && -n "$normalized_pattern" ]]; then
            line_num="$(rg -n -m 1 -F -- "async def $normalized_pattern" "$file" | cut -d: -f1)"
        fi
        if [[ -z "$line_num" && -n "$normalized_pattern" ]]; then
            line_num="$(rg -n -m 1 -F -- "class $normalized_pattern" "$file" | cut -d: -f1)"
        fi
    else
        if [[ -n "$raw_pattern" ]]; then
            line_num="$(grep -n -m 1 -F -- "$raw_pattern" "$file" | cut -d: -f1)"
        fi
        if [[ -z "$line_num" && -n "$normalized_pattern" && "$normalized_pattern" != "$raw_pattern" ]]; then
            line_num="$(grep -n -m 1 -F -- "$normalized_pattern" "$file" | cut -d: -f1)"
        fi
        if [[ -z "$line_num" && -n "$normalized_pattern" ]]; then
            line_num="$(grep -n -m 1 -F -- "def $normalized_pattern" "$file" | cut -d: -f1)"
        fi
        if [[ -z "$line_num" && -n "$normalized_pattern" ]]; then
            line_num="$(grep -n -m 1 -F -- "async def $normalized_pattern" "$file" | cut -d: -f1)"
        fi
        if [[ -z "$line_num" && -n "$normalized_pattern" ]]; then
            line_num="$(grep -n -m 1 -F -- "class $normalized_pattern" "$file" | cut -d: -f1)"
        fi
    fi

    echo "$line_num"
}

_collect_literal_hits() {
    local file="$1"
    local literal="$2"
    if [[ -z "$literal" ]]; then
        return 0
    fi

    if command -v rg >/dev/null 2>&1; then
        rg -n -F -- "$literal" "$file" | cut -d: -f1 || true
    else
        grep -n -F -- "$literal" "$file" | cut -d: -f1 || true
    fi
}

_resolve_line_num_strict() {
    local file="$1"
    local raw_pattern="$2"
    local normalized_pattern="$3"
    local matches=""
    local count=""

    if [[ -n "$normalized_pattern" ]]; then
        matches="$(
            {
                _collect_literal_hits "$file" "def $normalized_pattern("
                _collect_literal_hits "$file" "async def $normalized_pattern("
                _collect_literal_hits "$file" "class $normalized_pattern"
                _collect_literal_hits "$file" "function $normalized_pattern"
                _collect_literal_hits "$file" "$normalized_pattern() {"
                _collect_literal_hits "$file" "$normalized_pattern () {"
                _collect_literal_hits "$file" "$normalized_pattern ="
            } | awk 'NF' | sort -n | awk '!seen[$0]++'
        )"
        count="$(printf '%s\n' "$matches" | awk 'NF' | wc -l | tr -d ' ')"
        if [[ "$count" -eq 1 ]]; then
            printf '%s\n' "$matches" | awk 'NF{print; exit}'
            return 0
        fi
        if [[ "$count" -gt 1 ]]; then
            echo "ERROR: Strict symbol match is ambiguous for '$normalized_pattern' in $file." >&2
            return 2
        fi
    fi

    matches="$(_collect_literal_hits "$file" "$raw_pattern" | awk 'NF' | sort -n | awk '!seen[$0]++')"
    count="$(printf '%s\n' "$matches" | awk 'NF' | wc -l | tr -d ' ')"
    if [[ "$count" -eq 1 ]]; then
        printf '%s\n' "$matches" | awk 'NF{print; exit}'
        return 0
    fi
    if [[ "$count" -gt 1 ]]; then
        echo "ERROR: Strict symbol match is ambiguous for '$raw_pattern' in $file." >&2
        return 2
    fi

    return 1
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
    shift 2
    local context="$READ_CODE_DEFAULT_CONTEXT_LINES"
    local context_set=0
    local hud_flag=""
    local allow_fallback=0

    if [[ -z "$file" || -z "$pattern" ]]; then
        echo "ERROR: read_code_context requires: <file_path> <symbol_or_pattern> [context_lines]" >&2
        return 1
    fi

    while [[ "$#" -gt 0 ]]; do
        case "$1" in
            --hud-symbol)
                hud_flag="--hud-symbol"
                ;;
            --allow-fallback)
                allow_fallback=1
                ;;
            *)
                if [[ "$1" =~ ^[0-9]+$ ]] && [[ "$context_set" -eq 0 ]]; then
                    context="$1"
                    context_set=1
                else
                    echo "ERROR: Unexpected argument for context mode: $1" >&2
                    return 1
                fi
                ;;
        esac
        shift
    done

    if [[ ! -f "$file" ]]; then
        echo "ERROR: File not found: $file" >&2
        return 1
    fi

    if ! [[ "$context" =~ ^[0-9]+$ ]] || [[ "$context" -le 0 ]]; then
        echo "ERROR: context_lines must be a positive integer: $context" >&2
        return 1
    fi
    if [[ "$context" -gt "$READ_CODE_MAX_LINES" ]]; then
        echo "ERROR: context_lines exceeds max ($READ_CODE_MAX_LINES): $context" >&2
        return 1
    fi

    local normalized_pattern
    normalized_pattern="$(normalize_symbol_pattern "$pattern")"

    local use_hud_fast_path=0
    if [[ "$hud_flag" == "--hud-symbol" || "${SPECKIT_HUD_DIRECT_READ:-0}" == "1" ]]; then
        use_hud_fast_path=1
    fi

    if [[ "$use_hud_fast_path" -eq 0 ]]; then
        if [[ -n "$normalized_pattern" && "$normalized_pattern" != "$pattern" ]]; then
            codegraph_discover_or_fail "$normalized_pattern" "$(dirname "$file")"
        else
            codegraph_discover_or_fail "$pattern" "$(dirname "$file")"
        fi
    fi

    local line_num
    if line_num="$(_resolve_line_num_strict "$file" "$pattern" "$normalized_pattern")"; then
        :
    else
        local strict_status="$?"
        if [[ "$allow_fallback" -eq 1 ]]; then
            line_num="$(_find_line_num "$file" "$pattern" "$normalized_pattern")"
        else
            if [[ "$strict_status" -eq 2 ]]; then
                echo "ERROR: Symbol resolution ambiguous; re-run with --allow-fallback to allow bounded file-local fallback." >&2
            else
                echo "ERROR: Strict symbol resolution failed for '$pattern'. Re-run with --allow-fallback to allow bounded file-local fallback." >&2
            fi
            return 1
        fi
    fi

    if [[ -z "$line_num" ]]; then
        echo "ERROR: Pattern not found after one bounded fallback: $pattern in $file" >&2
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
    shift 2
    local line_count="$READ_CODE_DEFAULT_WINDOW_LINES"
    local line_count_set=0
    local pattern=""
    local hud_flag=""
    local allow_fallback=0

    if [[ -z "$file" || -z "$start_line" ]]; then
        echo "ERROR: read_code_window requires: <file_path> <start_line> [line_count]" >&2
        return 1
    fi

    while [[ "$#" -gt 0 ]]; do
        case "$1" in
            --hud-symbol)
                hud_flag="--hud-symbol"
                ;;
            --allow-fallback)
                allow_fallback=1
                ;;
            *)
                if [[ "$1" =~ ^[0-9]+$ ]] && [[ "$line_count_set" -eq 0 ]]; then
                    line_count="$1"
                    line_count_set=1
                elif [[ -z "$pattern" ]]; then
                    pattern="$1"
                else
                    echo "ERROR: Unexpected argument for window mode: $1" >&2
                    return 1
                fi
                ;;
        esac
        shift
    done

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
    if [[ "$line_count" -gt "$READ_CODE_MAX_LINES" ]]; then
        echo "ERROR: line_count exceeds max ($READ_CODE_MAX_LINES): $line_count" >&2
        return 1
    fi

    if is_large_code_file "$file"; then
        local use_hud_fast_path=0
        if [[ "$hud_flag" == "--hud-symbol" || "${SPECKIT_HUD_DIRECT_READ:-0}" == "1" ]]; then
            use_hud_fast_path=1
        fi

        # HUD current-line fast-path: allow bounded line-anchored reads without symbol lookup.
        if [[ -z "$pattern" && "$use_hud_fast_path" -eq 1 ]]; then
            :
        else
            if [[ -z "$pattern" ]]; then
                echo "ERROR: symbol_or_pattern is required for files >${CODE_FILE_LINE_THRESHOLD} lines unless using HUD current-line fast-path." >&2
                echo "Usage: read_code_window <file> <start_line> [line_count] <symbol_or_pattern>" >&2
                return 1
            fi
            local normalized_pattern
            normalized_pattern="$(normalize_symbol_pattern "$pattern")"
            if [[ "$use_hud_fast_path" -eq 0 ]]; then
                if [[ -n "$normalized_pattern" && "$normalized_pattern" != "$pattern" ]]; then
                    codegraph_discover_or_fail "$normalized_pattern" "$(dirname "$file")"
                else
                    codegraph_discover_or_fail "$pattern" "$(dirname "$file")"
                fi
            fi

            if ! _resolve_line_num_strict "$file" "$pattern" "$normalized_pattern" >/dev/null; then
                local strict_status="$?"
                if [[ "$allow_fallback" -ne 1 ]]; then
                    if [[ "$strict_status" -eq 2 ]]; then
                        echo "ERROR: Symbol resolution ambiguous; re-run with --allow-fallback to allow bounded file-local fallback." >&2
                    else
                        echo "ERROR: Strict symbol resolution failed for '$pattern'. Re-run with --allow-fallback to allow bounded file-local fallback." >&2
                    fi
                    return 1
                fi
                if [[ -z "$(_find_line_num "$file" "$pattern" "$normalized_pattern")" ]]; then
                    echo "ERROR: Pattern not found after one bounded fallback: $pattern in $file" >&2
                    return 1
                fi
            fi
        fi
    fi

    local end_line=$((start_line + line_count - 1))
    nl -ba "$file" | sed -n "${start_line},${end_line}p"
    return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [[ "$#" -lt 3 ]]; then
        echo "Usage:"
        echo "  read_code_context <file_path> <symbol_or_pattern> [context_lines<=${READ_CODE_MAX_LINES}] [--hud-symbol] [--allow-fallback]"
        echo "  read_code_window  <file_path> <start_line> [line_count<=${READ_CODE_MAX_LINES}] [symbol_or_pattern] [--hud-symbol] [--allow-fallback]"
        echo "                   (for large files, HUD current-line fast-path may omit symbol when --hud-symbol is set)"
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
