#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CODEGRAPH_DIR="$REPO_ROOT/.codegraph"

mkdir -p "$CODEGRAPH_DIR"

IGNORE_DIRS_DEFAULT="node_modules,venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,__pycache__,.uv-cache,logs,shadow-runs"

export DEFAULT_DATABASE="${DEFAULT_DATABASE:-falkordb}"
export FALKORDB_PATH="${FALKORDB_PATH:-$CODEGRAPH_DIR/falkordb.db}"
export FALKORDB_SOCKET_PATH="${FALKORDB_SOCKET_PATH:-$CODEGRAPH_DIR/falkordb.sock}"
export KUZUDB_PATH="${KUZUDB_PATH:-$CODEGRAPH_DIR/kuzudb}"
export IGNORE_DIRS="${IGNORE_DIRS:-$IGNORE_DIRS_DEFAULT}"

echo "Indexing CodeGraphContext for: $REPO_ROOT"
echo "DEFAULT_DATABASE=$DEFAULT_DATABASE"
echo "KUZUDB_PATH=$KUZUDB_PATH"
echo "IGNORE_DIRS=$IGNORE_DIRS"

if [ "${CGC_ALLOW_REPO_INDEX:-0}" != "1" ]; then
  echo "Refusing full-repo index without explicit opt-in." >&2
  echo "Set CGC_ALLOW_REPO_INDEX=1 when you intentionally want a full-repo rebuild." >&2
  exit 1
fi

cd "$REPO_ROOT"
CGC_ALLOW_REPO_INDEX=1 "$SCRIPT_DIR/cgc_safe_index.sh" "$REPO_ROOT"
