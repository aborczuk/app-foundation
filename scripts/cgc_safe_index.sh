#!/usr/bin/env bash
# Scoped CodeGraph indexing wrapper that avoids unsafe full-repo reindexing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CODEGRAPH_CONTEXT_DIR="$REPO_ROOT/.codegraphcontext"
CODEGRAPH_DB_DIR="$CODEGRAPH_CONTEXT_DIR/db"
source "$SCRIPT_DIR/cgc_owner.sh"

IGNORE_DIRS_DEFAULT="node_modules,venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,__pycache__,.uv-cache,logs,shadow-runs"

REPO_UV_CACHE_DIR="${CGC_UV_CACHE_DIR:-$CODEGRAPH_CONTEXT_DIR/.uv-cache}"
mkdir -p "$CODEGRAPH_DB_DIR" "$REPO_UV_CACHE_DIR"

export UV_CACHE_DIR="$REPO_UV_CACHE_DIR"
export DEFAULT_DATABASE="${DEFAULT_DATABASE:-kuzudb}"
export FALKORDB_PATH="${FALKORDB_PATH:-$CODEGRAPH_DB_DIR/falkordb}"
export FALKORDB_SOCKET_PATH="${FALKORDB_SOCKET_PATH:-$CODEGRAPH_DB_DIR/falkordb.sock}"
export KUZUDB_PATH="${KUZUDB_PATH:-$CODEGRAPH_DB_DIR/kuzudb}"
export IGNORE_DIRS="${IGNORE_DIRS:-$IGNORE_DIRS_DEFAULT}"

usage() {
  cat <<'EOF'
Usage:
  scripts/cgc_safe_index.sh [--force] <path>

Examples:
  scripts/cgc_safe_index.sh src/clickup_control_plane
  CGC_ALLOW_FORCE=1 scripts/cgc_safe_index.sh --force src/clickup_control_plane
  CGC_ALLOW_REPO_INDEX=1 scripts/cgc_safe_index.sh .

Safety:
  - Full-repo indexing (target '.', '/', or repo root) is blocked by default.
  - To allow non-force full-repo indexing intentionally, set CGC_ALLOW_REPO_INDEX=1.
  - Forced indexing requires explicit opt-in: CGC_ALLOW_FORCE=1.
  - Forced full-repo indexing is always blocked.
EOF
}

FORCE=0
if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

if [ "${1:-}" = "--force" ]; then
  FORCE=1
  shift
fi

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  usage
  exit 0
fi

if [ "$#" -ne 1 ]; then
  usage
  exit 2
fi

TARGET="$1"
TARGET_TRIMMED="${TARGET%/}"

is_repo_root_target() {
  local candidate="$1"

  if [ "$candidate" = "." ] || [ "$candidate" = "/" ] || [ "$candidate" = "$REPO_ROOT" ]; then
    return 0
  fi

  if [ -d "$candidate" ]; then
    local candidate_abs
    candidate_abs="$(cd "$candidate" && pwd -P)"
    if [ "$candidate_abs" = "$REPO_ROOT" ]; then
      return 0
    fi
  fi

  return 1
}

if [ "$FORCE" -eq 1 ] && is_repo_root_target "$TARGET_TRIMMED"; then
  echo "Refusing unsafe full-repo force re-index: cgc index --force $TARGET" >&2
  echo "Use a scoped path (example: scripts/cgc_safe_index.sh --force src/clickup_control_plane)." >&2
  exit 1
fi

if [ "$FORCE" -eq 1 ] && [ "${CGC_ALLOW_FORCE:-0}" != "1" ]; then
  echo "Refusing forced index without explicit opt-in." >&2
  echo "Set CGC_ALLOW_FORCE=1 for a one-off scoped force re-index." >&2
  exit 1
fi

if [ "$FORCE" -eq 0 ] && is_repo_root_target "$TARGET_TRIMMED" && [ "${CGC_ALLOW_REPO_INDEX:-0}" != "1" ]; then
  echo "Refusing default full-repo index target: $TARGET" >&2
  echo "Use a scoped target (recommended) or set CGC_ALLOW_REPO_INDEX=1 intentionally." >&2
  exit 1
fi

cd "$REPO_ROOT"
if cgc_owner_wait_for_release; then
  :
else
  owner_guard_status=$?
  exit "$owner_guard_status"
fi

cgc_owner_claim

stdout_file="$(mktemp "${TMPDIR:-/tmp}/cgc-index-stdout-XXXXXX")"
stderr_file="$(mktemp "${TMPDIR:-/tmp}/cgc-index-stderr-XXXXXX")"
cleanup_temp_files() {
  rm -f "$stdout_file" "$stderr_file"
}
trap 'cleanup_temp_files; cgc_owner_release' EXIT INT TERM

if [ "$FORCE" -eq 1 ]; then
  echo "Running scoped force index for: $TARGET"
  if uv run --no-sync cgc index --force "$TARGET" >"$stdout_file" 2>"$stderr_file"; then
    cat "$stdout_file"
    cat "$stderr_file" >&2
    cgc_owner_clear_last_error
    cleanup_temp_files
  else
    index_status=$?
    stderr_text="$(cat "$stderr_file")"
    if cgc_owner_error_is_memory_pressure "$stderr_text"; then
      cgc_owner_record_last_error "memory-pressure" "$index_status" "$stderr_text"
      echo "CodeGraph indexing failed due to memory pressure: $stderr_text" >&2
    else
      cgc_owner_clear_last_error
      echo "CodeGraph indexing failed: $stderr_text" >&2
    fi
    cleanup_temp_files
    exit "$index_status"
  fi
else
  echo "Running incremental index for: $TARGET"
  if uv run --no-sync cgc index "$TARGET" >"$stdout_file" 2>"$stderr_file"; then
    cat "$stdout_file"
    cat "$stderr_file" >&2
    cgc_owner_clear_last_error
    cleanup_temp_files
  else
    index_status=$?
    stderr_text="$(cat "$stderr_file")"
    if cgc_owner_error_is_memory_pressure "$stderr_text"; then
      cgc_owner_record_last_error "memory-pressure" "$index_status" "$stderr_text"
      echo "CodeGraph indexing failed due to memory pressure: $stderr_text" >&2
    else
      cgc_owner_clear_last_error
      echo "CodeGraph indexing failed: $stderr_text" >&2
    fi
    cleanup_temp_files
    exit "$index_status"
  fi
fi
