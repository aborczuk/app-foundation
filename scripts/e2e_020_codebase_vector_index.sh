#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FEATURE_ID="020"
FEATURE_SLUG="020-codebase-vector-index"
FEATURE_NAME="Codebase Vector Index"
FEATURE_DIR="$REPO_ROOT/specs/$FEATURE_SLUG"
CONFIG_FILE="${1:-$REPO_ROOT/.codegraphcontext/config.yaml}"
MODE="${2:-full}"

UV_PREFIX=(uv run)
if ! command -v uv >/dev/null 2>&1; then
  UV_PREFIX=()
fi

usage() {
  cat <<EOF
Usage: $(basename "$0") <config-file> [preflight|run|verify|ci|full]
EOF
}

log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

run_python() {
  if ((${#UV_PREFIX[@]})); then
    "${UV_PREFIX[@]}" python "$@"
  else
    python3 "$@"
  fi
}

cleanup() {
  :
}
trap cleanup EXIT

require_config() {
  [[ -f "$CONFIG_FILE" ]] || fail "Config file not found: $CONFIG_FILE"
}

run_preflight() {
  log "Preflight for ${FEATURE_NAME}"
  run_python "$REPO_ROOT/scripts/pipeline_driver.py" --feature-id "$FEATURE_ID" --dry-run --json >/tmp/e2e_020_preflight.json
  log "Preflight passed"
}

run_story_1() {
  log "Story 1: semantic symbol lookup"
  run_python -m pytest "$REPO_ROOT/tests/integration/test_codebase_vector_index.py" -k "code_symbol_lookup_returns_metadata" -q
}

run_story_2() {
  log "Story 2: markdown section discovery"
  run_python -m pytest "$REPO_ROOT/tests/integration/test_codebase_vector_index.py" -k "markdown_section_lookup_returns_breadcrumb" -q
}

run_story_3() {
  log "Story 3: incremental refresh and recovery"
  run_python -m pytest "$REPO_ROOT/tests/integration/test_codebase_vector_index.py" -k "incremental_refresh_preserves_last_good_snapshot or refresh_excludes_generated_artifacts" -q
}

run_story_4() {
  log "Story 4: staleness reporting"
  run_python -m pytest "$REPO_ROOT/tests/integration/test_codebase_vector_index.py" -k "staleness_reports_commit_delta" -q
}

run_final() {
  run_preflight
  run_story_1
  run_story_2
  run_story_3
  run_story_4
  run_python "$REPO_ROOT/scripts/pipeline_ledger.py" validate >/tmp/e2e_020_ledger_validate.txt
  log "Final E2E passed"
}

show_verify() {
  log "Verification commands:"
  echo "  ${UV_PREFIX[*]:-python3} python scripts/pipeline_driver.py --feature-id ${FEATURE_ID} --dry-run --json"
  echo "  ${UV_PREFIX[*]:-python3} python -m pytest tests/integration/test_codebase_vector_index.py -q"
  echo "  ${UV_PREFIX[*]:-python3} python scripts/pipeline_ledger.py validate"
}

main() {
  [[ $# -ge 0 ]] || usage
  require_config
  case "$MODE" in
    preflight) run_preflight ;;
    run)
      run_story_1
      run_story_2
      run_story_3
      run_story_4
      ;;
    verify) show_verify ;;
    ci) run_preflight ;;
    full) run_final ;;
    *) usage; fail "Unknown mode: $MODE" ;;
  esac
}

main "$@"
