#!/usr/bin/env bash
# End-to-end pipeline for control-plane HITL audit behavior.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

COMMAND="${1:-full}"
CONFIG_PATH="${2:-specs/017-control-plane-hitl-audit/e2e.env}"
E2E_NON_INTERACTIVE="${E2E_NON_INTERACTIVE:-0}"
BLOCKED_MANUAL_EXIT=86

PYTHON_CMD=(python3)
PYTEST_CMD=(python3 -m pytest)
if command -v uv >/dev/null 2>&1; then
  PYTHON_CMD=(uv run python)
  PYTEST_CMD=(uv run pytest)
fi

TMP_DIR=""
TMP_ENV=""
SECTION_START_EPOCH=0
US1_LOG=""
US2_LOG=""

usage() {
  cat <<'USAGE'
Usage:
  scripts/e2e_017_control_plane_hitl_audit.sh [preflight|run|verify|full|ci] [env_config]

Commands:
  preflight  Validate toolchain/env and external dependencies (non-destructive)
  run        Execute user-story sections (includes required manual gates)
  verify     Print useful verification commands and run lightweight deterministic checks
  full       preflight -> run -> final full-feature gate -> verify
  ci         Non-interactive automated checks only (preflight + automated sections + verify)

Config:
  env_config is a KEY=VALUE env file (default: specs/017-control-plane-hitl-audit/e2e.env)

Non-interactive mode:
  Set E2E_NON_INTERACTIVE=1.
  Required manual gates return blocked_manual (exit 86).
USAGE
}

info() { echo "  [INFO] $*"; }
pass() { echo "  [PASS] $*"; }
warn() { echo "  [WARN] $*"; }
fail() { echo "  [FAIL] $*" >&2; exit 1; }
die() { echo "ERROR: $*" >&2; exit 1; }

blocked_manual() {
  echo "blocked_manual: $*" >&2
  exit "$BLOCKED_MANUAL_EXIT"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' not found"
}

is_interactive_mode() {
  [ "$E2E_NON_INTERACTIVE" != "1" ] && [ -t 0 ]
}

start_section() {
  SECTION_START_EPOCH="$(date +%s)"
  echo ""
  echo "=== $1 ==="
}

stat_mtime_epoch() {
  local path="$1"
  stat -f %m "$path" 2>/dev/null || stat -c %Y "$path" 2>/dev/null
}

count_control_plane_procs() {
  local pids
  pids="$(pgrep -f 'uvicorn clickup_control_plane\.app:app' 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    echo 0
  else
    echo "$pids" | wc -l | tr -d ' '
  fi
}

assert_no_new_control_plane_procs() {
  local baseline="$1"
  local label="$2"
  local current
  current="$(count_control_plane_procs)"
  if [ "$current" -gt "$baseline" ]; then
    local waited=0
    while [ "$waited" -lt 5 ] && [ "$current" -gt "$baseline" ]; do
      sleep 1
      waited=$((waited + 1))
      current="$(count_control_plane_procs)"
    done
  fi
  if [ "$current" -gt "$baseline" ]; then
    fail "Orphan control-plane process detected after ${label} (baseline=${baseline}, current=${current})."
  fi
  pass "No orphan control-plane process drift after ${label}."
}

cleanup() {
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

create_temp_workspace() {
  [ -f "$CONFIG_PATH" ] || die "Missing env config: $CONFIG_PATH"
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/e2e017-XXXXXX")"
  TMP_ENV="$TMP_DIR/e2e.env"
  cp "$CONFIG_PATH" "$TMP_ENV"

  set -a
  # shellcheck disable=SC1090
  . "$TMP_ENV"
  set +a

  CONTROL_PLANE_DB_PATH="$TMP_DIR/control-plane.db"
  CONTROL_PLANE_HOST="${CONTROL_PLANE_HOST:-127.0.0.1}"
  CONTROL_PLANE_PORT="${CONTROL_PLANE_PORT:-8090}"

  export CONTROL_PLANE_DB_PATH
  export CONTROL_PLANE_HOST
  export CONTROL_PLANE_PORT

  info "Using env config: $CONFIG_PATH"
  info "Using temp db path: $CONTROL_PLANE_DB_PATH"
}

require_env_var() {
  local name="$1"
  local value="${!name:-}"
  if [ -z "$value" ]; then
    fail "Required env var missing: $name"
  fi
  if [ "$value" = "..." ]; then
    fail "Required env var placeholder value detected: $name"
  fi
}

validate_required_env() {
  require_env_var CLICKUP_API_TOKEN
  require_env_var CLICKUP_WEBHOOK_SECRET
  require_env_var CONTROL_PLANE_ALLOWLIST
  require_env_var N8N_DISPATCH_BASE_URL
  require_env_var CONTROL_PLANE_COMPLETION_TOKEN
  pass "Required environment variables are present."
}

validate_clickup_dependency() {
  local code
  code="$(curl -sS --max-time 12 -o /dev/null -w '%{http_code}' \
    -H "Authorization: ${CLICKUP_API_TOKEN}" \
    https://api.clickup.com/api/v2/user || true)"
  if [ "$code" != "200" ]; then
    fail "ClickUp dependency check failed (HTTP ${code})."
  fi
  pass "ClickUp dependency reachable (HTTP 200)."
}

validate_n8n_dependency() {
  local code
  code="$(curl -sS --max-time 12 -o /dev/null -w '%{http_code}' "${N8N_DISPATCH_BASE_URL}" || true)"
  if [ "$code" = "000" ]; then
    fail "n8n dependency check failed (unreachable: ${N8N_DISPATCH_BASE_URL})."
  fi
  pass "n8n dependency reachable (HTTP ${code})."
}

collect_tests() {
  (
    cd "$REPO_ROOT"
    "${PYTEST_CMD[@]}" --collect-only \
      tests/contract/test_clickup_control_plane_contract.py \
      tests/unit/clickup_control_plane \
      tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py \
      -q >/dev/null
  ) || fail "pytest collection failed for control-plane targets."
  pass "pytest collection succeeded."
}

assert_no_lifecycle_errors() {
  local log_file="$1"
  if rg -n "event loop is already running|Task was destroyed but it is pending|pending task|RuntimeError:.*event loop" "$log_file" >/dev/null 2>&1; then
    fail "Lifecycle error signals detected in ${log_file}."
  fi
  pass "No lifecycle error signals detected."
}

materialize_state_evidence() {
  "${PYTHON_CMD[@]}" - "$CONTROL_PLANE_DB_PATH" <<'PY' || fail "Failed to materialize deterministic state evidence."
import asyncio
import sys

from clickup_control_plane.state_store import StateStore


async def main(db_path: str) -> None:
    store = StateStore(db_path)
    await store.initialize()

    task_id = "e2e-017-task"
    event_id = "e2e-017-event"
    run_id = "e2e-017-run"

    lock = await store.record_event_and_acquire_lock(
        task_id=task_id,
        event_id=event_id,
        run_id=run_id,
    )
    if lock.decision == "dispatch":
        await store.upsert_paused_run(
            task_id=task_id,
            run_id=run_id,
            workflow_type="build_spec",
            context_ref="specs/017-control-plane-hitl-audit/spec.md",
            execution_policy="manual-test",
            timeout_at_utc="2099-01-01T00:00:00+00:00",
            prompt="Approve?",
        )
        await store.clear_paused_run(task_id=task_id, run_id=run_id)
        await store.persist_terminal_decision(
            task_id=task_id,
            event_id=event_id,
            decision="dispatch",
            active_run_id=run_id,
            release_lock=True,
            final_state="released",
        )
    else:
        await store.update_processed_event_decision(
            event_id=event_id,
            decision="dispatch",
        )


asyncio.run(main(sys.argv[1]))
PY
  pass "Deterministic state evidence materialized."
}

assert_timestamp_gated_evidence() {
  local log_file="$1"
  [ -f "$log_file" ] || fail "Missing section log: $log_file"
  local log_mtime
  log_mtime="$(stat_mtime_epoch "$log_file")"
  [ -n "$log_mtime" ] || fail "Unable to stat section log mtime."
  if [ "$log_mtime" -lt "$SECTION_START_EPOCH" ]; then
    fail "Timestamp gate failed: section log predates section start."
  fi

  [ -f "$CONTROL_PLANE_DB_PATH" ] || fail "Expected DB artifact missing: $CONTROL_PLANE_DB_PATH"
  local db_mtime
  db_mtime="$(stat_mtime_epoch "$CONTROL_PLANE_DB_PATH")"
  [ -n "$db_mtime" ] || fail "Unable to stat DB mtime."
  if [ "$db_mtime" -lt "$SECTION_START_EPOCH" ]; then
    fail "Timestamp gate failed: DB artifact predates section start."
  fi
  pass "Timestamp-gated evidence checks passed."
}

assert_state_safety_and_tx_integrity() {
  "${PYTHON_CMD[@]}" - "$CONTROL_PLANE_DB_PATH" "$SECTION_START_EPOCH" <<'PY'
import sqlite3
import sys
from pathlib import Path


def fail(msg: str) -> None:
    print(f"state/transaction check failed: {msg}", file=sys.stderr)
    raise SystemExit(1)


db_path = Path(sys.argv[1])
start_epoch = int(sys.argv[2])
if not db_path.exists():
    fail(f"db not found: {db_path}")
if int(db_path.stat().st_mtime) < start_epoch:
    fail("db mtime predates section start")

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()
tables = {row[0] for row in cur.execute("select name from sqlite_master where type='table'")}
for required in ("processed_events", "active_task_runs", "paused_task_runs"):
    if required not in tables:
        fail(f"missing required table: {required}")

processed_count = cur.execute("select count(*) from processed_events").fetchone()[0]
if processed_count < 1:
    fail("processed_events has no rows")

dup_events = cur.execute(
    "select count(*) from (select event_id from processed_events group by event_id having count(*) > 1)"
).fetchone()[0]
if dup_events != 0:
    fail(f"duplicate processed event ids detected: {dup_events}")

running_rows = cur.execute("select count(*) from active_task_runs where state='running'").fetchone()[0]
if running_rows != 0:
    fail(f"orphan active task runs detected: {running_rows}")

paused_rows = cur.execute("select count(*) from paused_task_runs").fetchone()[0]
if paused_rows != 0:
    fail(f"orphan paused runs detected: {paused_rows}")

columns = {row[1] for row in cur.execute("pragma table_info(active_task_runs)")}
if "released_at_utc" in columns:
    bad_released = cur.execute(
        "select count(*) from active_task_runs where state='released' and released_at_utc is null"
    ).fetchone()[0]
    if bad_released != 0:
        fail(f"released rows missing release timestamp: {bad_released}")

null_integrity = cur.execute(
    "select count(*) from processed_events where event_id is null or decision is null"
).fetchone()[0]
if null_integrity != 0:
    fail(f"processed_events integrity violation count: {null_integrity}")

conn.close()
print("state/transaction checks passed")
PY
  pass "State-safety and transaction-integrity assertions passed."
}

run_pytest_to_log() {
  local log_file="$1"
  shift
  (
    cd "$REPO_ROOT"
    set +e
    "${PYTEST_CMD[@]}" "$@" -v --tb=short | tee "$log_file"
    local rc=${PIPESTATUS[0]}
    set -e
    exit "$rc"
  ) || fail "pytest run failed for: $*"
}

run_us1_automated() {
  start_section "Section 2 (US1) Automated"
  local baseline
  baseline="$(count_control_plane_procs)"

  US1_LOG="$TMP_DIR/us1.log"
  run_pytest_to_log "$US1_LOG" \
    tests/contract/test_clickup_control_plane_contract.py \
    tests/unit/clickup_control_plane/test_schemas.py \
    tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -k \
    "workflow_waiting_input_then_operator_response_resumes_paused_run or workflow_timeout_marks_blocked_and_releases_lock_for_next_dispatch"

  assert_no_lifecycle_errors "$US1_LOG"
  materialize_state_evidence
  assert_timestamp_gated_evidence "$US1_LOG"
  assert_state_safety_and_tx_integrity
  assert_no_new_control_plane_procs "$baseline" "US1 automated section"
}

run_us2_automated() {
  start_section "Section 3 (US2) Automated"
  local baseline
  baseline="$(count_control_plane_procs)"

  US2_LOG="$TMP_DIR/us2.log"
  run_pytest_to_log "$US2_LOG" \
    tests/unit/clickup_control_plane/test_dispatcher.py \
    tests/unit/clickup_control_plane/test_clickup_client.py \
    tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -k \
    "manual_status_change_out_of_controlled_state_cancels_active_run"

  assert_no_lifecycle_errors "$US2_LOG"
  materialize_state_evidence
  assert_timestamp_gated_evidence "$US2_LOG"
  assert_state_safety_and_tx_integrity
  assert_no_new_control_plane_procs "$baseline" "US2 automated section"
}

confirm_manual_gate() {
  local prompt="$1"
  if ! is_interactive_mode; then
    blocked_manual "$prompt"
  fi
  local answer
  read -r -p "$prompt [y/N]: " answer || true
  case "$answer" in
    y|Y|yes|YES) pass "Manual gate confirmed." ;;
    *) fail "Manual gate not confirmed." ;;
  esac
}

run_manual_us1_gate() {
  start_section "Section 2 (US1) Manual Gate"
  confirm_manual_gate "Did you run one live wait/resume cycle in ClickUp and observe resumed dispatch + visible outcome?"
}

run_manual_us2_gate() {
  start_section "Section 3 (US2) Manual Gate"
  confirm_manual_gate "Did you perform controlled->non-controlled status change and observe cancel behavior + visible task outcome?"
}

run_final_gate() {
  start_section "Section Final (Full Feature)"
  assert_state_safety_and_tx_integrity
  confirm_manual_gate "Did you confirm lifecycle history appears chronological in ClickUp across multiple runs?"
}

run_preflight() {
  start_section "Section 1 (Preflight)"
  require_cmd "${PYTHON_CMD[0]}"
  require_cmd curl
  require_cmd rg
  create_temp_workspace
  validate_required_env
  validate_clickup_dependency
  validate_n8n_dependency
  collect_tests
}

run_verify() {
  start_section "Verification"
  create_temp_workspace
  validate_required_env
  validate_clickup_dependency
  validate_n8n_dependency
  info "Verification commands:"
  cat <<'CMDS'
scripts/e2e_017_control_plane_hitl_audit.sh preflight specs/017-control-plane-hitl-audit/e2e.env
uv run pytest tests/contract/test_clickup_control_plane_contract.py -q
uv run pytest tests/unit/clickup_control_plane -q
uv run pytest tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q
sqlite3 .speckit/control-plane.db "select count(*) from active_task_runs where state='running';"
sqlite3 .speckit/control-plane.db "select count(*) from paused_task_runs;"
CMDS
  pass "Verification checklist printed."
}

run_interactive_story_sections() {
  create_temp_workspace
  run_us1_automated
  run_manual_us1_gate
  run_us2_automated
  run_manual_us2_gate
}

run_ci_sections() {
  create_temp_workspace
  run_us1_automated
  run_us2_automated
}

case "$COMMAND" in
  -h|--help)
    usage
    exit 0
    ;;
  preflight)
    run_preflight
    ;;
  run)
    run_interactive_story_sections
    ;;
  verify)
    run_verify
    ;;
  ci)
    run_preflight
    run_ci_sections
    run_verify
    ;;
  full)
    run_preflight
    run_interactive_story_sections
    run_final_gate
    run_verify
    ;;
  *)
    usage
    exit 1
    ;;
esac

echo ""
echo "E2E pipeline command '${COMMAND}' completed."
