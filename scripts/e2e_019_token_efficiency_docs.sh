#!/usr/bin/env bash
# E2E Testing Pipeline: Deterministic Pipeline Driver with LLM Handoff (Feature 019)
# Automates the checks documented in specs/019-token-efficiency-docs/e2e.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

FEATURE_ID="019"
FEATURE_SLUG="019-token-efficiency-docs"
FEATURE_DIR="$REPO_ROOT/specs/$FEATURE_SLUG"
PIPELINE_LEDGER="$REPO_ROOT/.speckit/pipeline-ledger.jsonl"
TASK_LEDGER="$REPO_ROOT/.speckit/task-ledger.jsonl"
E2E_LOG_DIR="$REPO_ROOT/.speckit/e2e-019"

UV_CACHE_DIR_VALUE="${E2E_UV_CACHE_DIR:-/tmp/uv-cache}"
E2E_NON_INTERACTIVE="${E2E_NON_INTERACTIVE:-0}"
E2E_REQUIRE_MANUAL_REVIEW="${E2E_REQUIRE_MANUAL_REVIEW:-0}"

COMMAND="${1:-full}"
CONFIG_FILE="${2:-}"
TMP_DIR=""
TEMP_CONFIG=""
SECTION_START_EPOCH=0

usage() {
  cat <<'EOF'
Usage:
  scripts/e2e_019_token_efficiency_docs.sh [preflight|run|verify|ci|full] [config-file]

Modes:
  preflight  Run deterministic prerequisite checks only
  run        Run per-story sections (US1 -> US2 -> US3)
  verify     Print useful verification commands and run lightweight validators
  ci         Non-interactive mode (no manual gates)
  full       preflight -> run -> final integrated assertions (default)

Environment:
  E2E_UV_CACHE_DIR=/tmp/uv-cache  Writable uv cache path override
  E2E_NON_INTERACTIVE=1           Disable prompts and fail with blocked_manual when required
  E2E_REQUIRE_MANUAL_REVIEW=1     Enable manual governance review prompt
EOF
}

log() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing required command: $cmd"
}

run_python() {
  if command -v uv >/dev/null 2>&1; then
    UV_CACHE_DIR="$UV_CACHE_DIR_VALUE" uv run python "$@"
  else
    python3 "$@"
  fi
}

run_pytest() {
  if command -v uv >/dev/null 2>&1; then
    UV_CACHE_DIR="$UV_CACHE_DIR_VALUE" uv run pytest "$@"
  else
    python3 -m pytest "$@"
  fi
}

run_and_log() {
  local log_file="$1"
  shift
  log "Running: $*"
  "$@" 2>&1 | tee -a "$log_file"
}

file_mtime_epoch() {
  local path="$1"
  if stat -f "%m" "$path" >/dev/null 2>&1; then
    stat -f "%m" "$path"
  else
    stat -c "%Y" "$path"
  fi
}

start_section() {
  local title="$1"
  SECTION_START_EPOCH="$(date +%s)"
  log "=== $title ==="
}

assert_timestamp_gate() {
  local artifact="$1"
  [ -f "$artifact" ] || fail "Timestamp gate failed: artifact missing: $artifact"
  local artifact_epoch
  artifact_epoch="$(file_mtime_epoch "$artifact")"
  [ "$artifact_epoch" -ge "$SECTION_START_EPOCH" ] || fail "Timestamp gate failed: stale artifact from previous run: $artifact"
}

assert_no_event_loop_signals() {
  local log_file="$1"
  if grep -Eiq "event loop is already running|Task was destroyed but it is pending|coroutine .* was never awaited|pending-task destruction" "$log_file"; then
    fail "Lifecycle assertion failed: event loop/pending-task warning detected in $log_file"
  fi
}

assert_no_persistence_ambiguity() {
  local log_file="$1"
  if grep -Eiq "partial commit|rollback failed|transaction.*(failed|error)|database is locked|swallowed persistence error" "$log_file"; then
    fail "Persistence assertion failed: ambiguous transaction/persistence signals found in $log_file"
  fi
}

assert_no_partial_db_residue() {
  local scan_output
  if ! scan_output="$(run_python - "$REPO_ROOT" "$SECTION_START_EPOCH" <<'PY'
import os
import sys
from pathlib import Path

repo = Path(sys.argv[1])
start_epoch = int(sys.argv[2])
patterns = (".db-wal", ".db-journal", ".sqlite-wal", ".sqlite-journal")
hits = []
for path in repo.rglob("*"):
    if not path.is_file():
        continue
    name = path.name
    if not name.endswith(patterns):
        continue
    try:
        if int(path.stat().st_mtime) >= start_epoch:
            hits.append(str(path))
    except OSError:
        continue
if hits:
    print("\n".join(hits))
    sys.exit(1)
print("ok")
PY
)"; then
    fail "Transaction-integrity assertion failed: local DB residue detected: $scan_output"
  fi
}

assert_no_feature_lock_residue() {
  local lock_matches
  lock_matches="$(find "$REPO_ROOT/.speckit/locks" -maxdepth 1 -type f -name "${FEATURE_ID}*.lock" 2>/dev/null || true)"
  if [ -n "$lock_matches" ]; then
    fail "State-safety assertion failed: stale feature lock(s) detected: $lock_matches"
  fi
}

assert_no_orphan_processes() {
  if pgrep -f "[p]ipeline_driver.py" >/dev/null 2>&1; then
    fail "Lifecycle assertion failed: orphan pipeline_driver process detected"
  fi
}

assert_manifest_state_safety() {
  local canonical_manifest="$REPO_ROOT/.specify/command-manifest.yaml"
  local mirror_manifest="$REPO_ROOT/command-manifest.yaml"
  [ -f "$canonical_manifest" ] || fail "Missing canonical manifest: $canonical_manifest"
  if [ -f "$mirror_manifest" ] && ! cmp -s "$canonical_manifest" "$mirror_manifest"; then
    fail "state_drift_detected: command-manifest mirror diverges from canonical .specify/command-manifest.yaml"
  fi
}

validate_ledgers() {
  [ -f "$PIPELINE_LEDGER" ] && run_python scripts/pipeline_ledger.py validate --file "$PIPELINE_LEDGER" >/dev/null
  [ -f "$TASK_LEDGER" ] && run_python scripts/task_ledger.py validate --file "$TASK_LEDGER" >/dev/null
}

manual_gate() {
  local prompt="$1"
  if [ "$E2E_NON_INTERACTIVE" = "1" ]; then
    fail "blocked_manual: $prompt"
  fi
  local answer
  read -r -p "$prompt (yes/no): " answer
  [ "$answer" = "yes" ] || fail "blocked_manual: manual confirmation not granted"
}

prepare_temp_config() {
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/e2e-019.XXXXXX")"
  if [ -n "$CONFIG_FILE" ]; then
    [ -f "$CONFIG_FILE" ] || fail "Config file not found: $CONFIG_FILE"
    TEMP_CONFIG="$TMP_DIR/$(basename "$CONFIG_FILE")"
    cp "$CONFIG_FILE" "$TEMP_CONFIG"
  else
    TEMP_CONFIG="$TMP_DIR/e2e-default.yaml"
    cat >"$TEMP_CONFIG" <<EOF
feature_id: "$FEATURE_ID"
feature_dir: "$FEATURE_DIR"
uv_cache_dir: "$UV_CACHE_DIR_VALUE"
EOF
  fi
}

validate_prerequisites() {
  require_cmd python3
  require_cmd git
  require_cmd uv
  [ -d "$FEATURE_DIR" ] || fail "Missing feature directory: $FEATURE_DIR"
  [ -f "$FEATURE_DIR/spec.md" ] || fail "Missing required artifact: $FEATURE_DIR/spec.md"
  [ -f "$FEATURE_DIR/plan.md" ] || fail "Missing required artifact: $FEATURE_DIR/plan.md"
  [ -f "$FEATURE_DIR/tasks.md" ] || fail "Missing required artifact: $FEATURE_DIR/tasks.md"
  [ -f "$FEATURE_DIR/e2e.md" ] || fail "Missing required artifact: $FEATURE_DIR/e2e.md"
  [ -f "$REPO_ROOT/scripts/pipeline_ledger.py" ] || fail "Missing script: scripts/pipeline_ledger.py"
  [ -f "$REPO_ROOT/scripts/speckit_gate_status.py" ] || fail "Missing script: scripts/speckit_gate_status.py"
  mkdir -p "$E2E_LOG_DIR" "$UV_CACHE_DIR_VALUE"
}

run_preflight() {
  start_section "Section 1: Preflight (Dry-Run Smoke Test)"
  local log_file="$E2E_LOG_DIR/preflight.log"
  : >"$log_file"

  validate_prerequisites
  run_and_log "$log_file" run_python scripts/pipeline_ledger.py validate-manifest
  run_and_log "$log_file" run_python scripts/speckit_gate_status.py --mode implement --feature-dir "$FEATURE_DIR" --json
  run_and_log "$log_file" run_pytest --collect-only tests/unit/test_pipeline_driver.py tests/integration/test_pipeline_driver_feature_flow.py tests/contract/test_pipeline_driver_contract.py

  assert_timestamp_gate "$log_file"
  assert_no_event_loop_signals "$log_file"
  assert_manifest_state_safety
  assert_no_feature_lock_residue
  assert_no_orphan_processes
  assert_no_partial_db_residue

  log "Preflight passed"
}

run_us1() {
  start_section "Section 2: US1 Deterministic Step Routing"
  local log_file="$E2E_LOG_DIR/us1.log"
  : >"$log_file"

  run_and_log "$log_file" run_pytest \
    tests/integration/test_pipeline_driver_feature_flow.py::test_deterministic_route_success \
    tests/integration/test_pipeline_driver_feature_flow.py::test_deterministic_route_blocked \
    tests/unit/test_pipeline_driver.py::test_handoff_contract \
    tests/integration/test_pipeline_driver_feature_flow.py::test_reconcile_and_retry_guards
  run_and_log "$log_file" run_python scripts/pipeline_ledger.py validate --file "$PIPELINE_LEDGER"
  run_and_log "$log_file" run_python scripts/task_ledger.py validate --file "$TASK_LEDGER"

  assert_timestamp_gate "$log_file"
  assert_no_event_loop_signals "$log_file"
  assert_no_persistence_ambiguity "$log_file"
  assert_manifest_state_safety
  assert_no_feature_lock_residue
  assert_no_orphan_processes
  assert_no_partial_db_residue

  log "US1 passed"
}

run_us2() {
  start_section "Section 3: US2 Compact Parsing Contract"
  local log_file="$E2E_LOG_DIR/us2.log"
  : >"$log_file"

  run_and_log "$log_file" run_pytest \
    tests/contract/test_pipeline_driver_contract.py::test_step_result_schema \
    tests/integration/test_pipeline_driver_feature_flow.py::test_runtime_failure_verbose_rerun \
    tests/integration/test_pipeline_driver_feature_flow.py::test_dry_run_does_not_mutate_ledgers_or_artifacts \
    tests/unit/test_pipeline_driver.py::test_approval_breakpoint_blocks_without_token \
    tests/integration/test_pipeline_driver_feature_flow.py::test_approval_breakpoint_resume_flow

  assert_timestamp_gate "$log_file"
  assert_no_event_loop_signals "$log_file"
  assert_no_persistence_ambiguity "$log_file"
  assert_manifest_state_safety
  assert_no_feature_lock_residue
  assert_no_orphan_processes
  assert_no_partial_db_residue

  log "US2 passed"
}

run_us3() {
  start_section "Section 4: US3 Governance and Migration Safety"
  local log_file="$E2E_LOG_DIR/us3.log"
  : >"$log_file"

  run_and_log "$log_file" run_pytest \
    tests/integration/test_pipeline_driver_feature_flow.py::test_mixed_migration_mode \
    tests/unit/test_pipeline_driver.py::test_manifest_governance_guard

  [ -f "$REPO_ROOT/scripts/validate_command_script_coverage.py" ] || fail "Missing script: scripts/validate_command_script_coverage.py"
  run_and_log "$log_file" run_python scripts/validate_command_script_coverage.py
  run_and_log "$log_file" bash scripts/validate_doc_graph.sh
  run_and_log "$log_file" run_python scripts/pipeline_ledger.py validate-manifest

  if [ "$E2E_REQUIRE_MANUAL_REVIEW" = "1" ]; then
    manual_gate "Confirm migration and rollback policy docs were human-reviewed"
  fi

  assert_timestamp_gate "$log_file"
  assert_no_event_loop_signals "$log_file"
  assert_no_persistence_ambiguity "$log_file"
  assert_manifest_state_safety
  assert_no_feature_lock_residue
  assert_no_orphan_processes
  assert_no_partial_db_residue

  log "US3 passed"
}

run_final() {
  start_section "Section Final: Full Feature E2E"
  local log_file="$E2E_LOG_DIR/final.log"
  : >"$log_file"

  run_preflight
  run_us1
  run_us2
  run_us3

  run_and_log "$log_file" run_pytest tests/unit/test_pipeline_driver.py tests/integration/test_pipeline_driver_feature_flow.py tests/contract/test_pipeline_driver_contract.py
  run_and_log "$log_file" run_python scripts/pipeline_ledger.py validate --file "$PIPELINE_LEDGER"
  run_and_log "$log_file" run_python scripts/task_ledger.py validate --file "$TASK_LEDGER"

  assert_timestamp_gate "$log_file"
  assert_no_event_loop_signals "$log_file"
  assert_no_persistence_ambiguity "$log_file"
  assert_manifest_state_safety
  assert_no_feature_lock_residue
  assert_no_orphan_processes
  assert_no_partial_db_residue

  log "Final E2E passed"
}

print_verify_commands() {
  cat <<'EOF'
Verification commands:
  UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/pipeline_ledger.py validate-manifest
  UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/speckit_gate_status.py --mode implement --feature-dir specs/019-token-efficiency-docs --json
  UV_CACHE_DIR=/tmp/uv-cache uv run pytest --collect-only tests/unit/test_pipeline_driver.py tests/integration/test_pipeline_driver_feature_flow.py tests/contract/test_pipeline_driver_contract.py
  scripts/e2e_019_token_efficiency_docs.sh preflight
  scripts/e2e_019_token_efficiency_docs.sh run
EOF
}

cleanup() {
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
  jobs -p | xargs kill >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [ "$COMMAND" = "-h" ] || [ "$COMMAND" = "--help" ]; then
  usage
  exit 0
fi

case "$COMMAND" in
  preflight|run|verify|ci|full)
    ;;
  *)
    usage
    fail "Unknown mode: $COMMAND"
    ;;
esac

prepare_temp_config
log "Using temp config copy: $TEMP_CONFIG"

case "$COMMAND" in
  preflight)
    run_preflight
    ;;
  run)
    run_us1
    run_us2
    run_us3
    ;;
  verify)
    print_verify_commands
    run_python scripts/pipeline_ledger.py validate-manifest >/dev/null
    run_python scripts/speckit_gate_status.py --mode implement --feature-dir "$FEATURE_DIR" --json >/dev/null
    log "Lightweight verification checks passed"
    ;;
  ci)
    E2E_NON_INTERACTIVE=1
    run_preflight
    run_us1
    run_us2
    run_us3
    ;;
  full)
    run_final
    ;;
esac

log "E2E pipeline complete (mode: $COMMAND)"
