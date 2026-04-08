#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

COMMAND="${1:-full}"
CONFIG_PATH="${2:-specs/015-control-plane-dispatch/e2e.env}"
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
TEST_LOG=""
SERVER_LOG=""
SERVER_PID=""
SECTION_START_EPOCH=0

usage() {
  cat <<'USAGE'
Usage:
  scripts/e2e_015_control_plane_dispatch.sh [preflight|run|verify|full|ci] [env_config]

Commands:
  preflight  Validate toolchain, env wiring, dependency reachability, and test collection
  run        Run interactive user-story sections (US1)
  verify     Print verification commands and run lightweight safety checks
  full       preflight -> run -> final -> verify
  ci         Non-interactive automated checks only (preflight + automated US1 + verify)

Config:
  env_config is a KEY=VALUE env file (default: specs/015-control-plane-dispatch/e2e.env)

Non-interactive mode:
  Set E2E_NON_INTERACTIVE=1.
  Required human gates return: blocked_manual (exit 86).
USAGE
}

info() { echo "  [INFO] $*"; }
pass() { echo "  [PASS] $*"; }
warn() { echo "  [WARN] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }
fail() { echo "  [FAIL] $*" >&2; exit 1; }

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
  pass "No orphan control-plane processes after ${label} (count=${current})."
}

stop_service_if_running() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    local waited=0
    while kill -0 "$SERVER_PID" 2>/dev/null && [ "$waited" -lt 8 ]; do
      sleep 1
      waited=$((waited + 1))
    done
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      kill -9 "$SERVER_PID" 2>/dev/null || true
    fi
    SERVER_PID=""
  fi

  # Ensure no residual uvicorn control-plane process survives teardown.
  pkill -f 'uvicorn clickup_control_plane\.app:app' 2>/dev/null || true
  sleep 1
  pkill -9 -f 'uvicorn clickup_control_plane\.app:app' 2>/dev/null || true
}

cleanup() {
  stop_service_if_running
  if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

start_section() {
  SECTION_START_EPOCH="$(date +%s)"
  echo ""
  echo "=== $1 ==="
}

create_temp_workspace() {
  [ -f "$CONFIG_PATH" ] || die "Missing env config: $CONFIG_PATH"

  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/e2e015-XXXXXX")"
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
    fail "Required env var has placeholder value: $name"
  fi
}

validate_required_env() {
  require_env_var CLICKUP_API_TOKEN
  require_env_var CLICKUP_WEBHOOK_SECRET
  require_env_var CONTROL_PLANE_ALLOWLIST
  require_env_var N8N_DISPATCH_BASE_URL
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
  pass "ClickUp dependency reachable and token accepted (HTTP 200)."
}

validate_n8n_dependency() {
  local code
  code="$(curl -sS --max-time 12 -o /dev/null -w '%{http_code}' "${N8N_DISPATCH_BASE_URL}" || true)"
  if [ "$code" = "000" ]; then
    fail "n8n dependency check failed (unreachable endpoint: ${N8N_DISPATCH_BASE_URL})."
  fi
  pass "n8n dependency reachable (HTTP ${code})."
}

collect_control_plane_tests() {
  (
    cd "$REPO_ROOT"
    "${PYTEST_CMD[@]}" --collect-only \
      tests/contract/test_clickup_control_plane_contract.py \
      tests/unit/clickup_control_plane \
      tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py \
      -q >/dev/null
  ) || fail "Control-plane pytest collection failed."
  pass "Control-plane test collection succeeded."
}

run_us1_automated_suite() {
  local baseline
  baseline="$(count_control_plane_procs)"

  TEST_LOG="$TMP_DIR/us1-tests.log"
  (
    cd "$REPO_ROOT"
    set +e
    "${PYTEST_CMD[@]}" \
      tests/contract/test_clickup_control_plane_contract.py \
      tests/unit/clickup_control_plane \
      tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py \
      -v --tb=short | tee "$TEST_LOG"
    local rc=${PIPESTATUS[0]}
    set -e
    exit "$rc"
  ) || fail "US1 automated test suite failed."

  if rg -n "event loop is already running|Task was destroyed but it is pending|pending task|RuntimeError:.*event loop" "$TEST_LOG" >/dev/null 2>&1; then
    fail "Lifecycle error signals detected in US1 test output."
  fi
  pass "No lifecycle error signals detected in US1 test output."

  materialize_control_plane_state_evidence
  assert_timestamp_gated_evidence
  assert_state_safety_and_tx_integrity
  assert_no_new_control_plane_procs "$baseline" "US1 automated suite"
}

materialize_control_plane_state_evidence() {
  "${PYTHON_CMD[@]}" - "$CONTROL_PLANE_DB_PATH" <<'PY' || fail "Failed to materialize deterministic control-plane DB evidence."
import asyncio
import sys
from pathlib import Path

from clickup_control_plane.state_store import StateStore


async def main(db_path_raw: str) -> None:
    db_path = Path(db_path_raw)
    store = StateStore(db_path)
    await store.initialize()

    task_id = "e2e-evidence-task"
    event_id = "e2e-evidence-event"
    run_id = "e2e-evidence-run"

    lock = await store.record_event_and_acquire_lock(
        task_id=task_id,
        event_id=event_id,
        run_id=run_id,
    )
    if lock.decision == "dispatch":
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

  pass "Deterministic control-plane DB evidence materialized."
}

assert_timestamp_gated_evidence() {
  [ -f "$TEST_LOG" ] || fail "US1 test log missing: $TEST_LOG"

  local log_mtime
  log_mtime="$(stat_mtime_epoch "$TEST_LOG")"
  [ -n "$log_mtime" ] || fail "Unable to stat test log mtime."
  if [ "$log_mtime" -lt "$SECTION_START_EPOCH" ]; then
    fail "Timestamp gate failed: test log predates section start."
  fi

  [ -f "$CONTROL_PLANE_DB_PATH" ] || fail "Expected DB artifact missing: $CONTROL_PLANE_DB_PATH"

  local db_mtime
  db_mtime="$(stat_mtime_epoch "$CONTROL_PLANE_DB_PATH")"
  [ -n "$db_mtime" ] || fail "Unable to stat DB mtime."
  if [ "$db_mtime" -lt "$SECTION_START_EPOCH" ]; then
    fail "Timestamp gate failed: DB updates predate section start."
  fi

  pass "Timestamp-gated artifact checks passed."
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
    fail(f"db path missing: {db_path}")
if int(db_path.stat().st_mtime) < start_epoch:
    fail("db mtime predates section start")

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

tables = {row[0] for row in cur.execute("select name from sqlite_master where type='table'")}
for required in ("processed_events", "active_task_runs"):
    if required not in tables:
        fail(f"required table missing: {required}")

processed_count = cur.execute("select count(*) from processed_events").fetchone()[0]
if processed_count < 1:
    fail("processed_events has no rows (no deterministic state evidence)")

dup_events = cur.execute(
    "select count(*) from (select event_id from processed_events group by event_id having count(*) > 1)"
).fetchone()[0]
if dup_events != 0:
    fail(f"duplicate processed event ids detected: {dup_events}")

null_integrity = cur.execute(
    "select count(*) from processed_events where event_id is null or decision is null"
).fetchone()[0]
if null_integrity != 0:
    fail(f"processed_events contains null integrity fields: {null_integrity}")

running_dup = cur.execute(
    "select count(*) from (select task_id from active_task_runs where state='running' group by task_id having count(*) > 1)"
).fetchone()[0]
if running_dup != 0:
    fail(f"multiple running rows for same task detected: {running_dup}")

running_rows = cur.execute("select count(*) from active_task_runs where state='running'").fetchone()[0]
if running_rows != 0:
    fail(f"orphan active-task-run rows remain: {running_rows}")

columns = {row[1] for row in cur.execute("pragma table_info(active_task_runs)")}
release_col = "released_at_utc" if "released_at_utc" in columns else ("released_at" if "released_at" in columns else None)
if release_col:
    released_missing_ts = cur.execute(
        f"select count(*) from active_task_runs where state='released' and {release_col} is null"
    ).fetchone()[0]
    if released_missing_ts != 0:
        fail(f"released rows missing release timestamp: {released_missing_ts}")

conn.close()
print("state/transaction checks passed")
PY

  pass "State-safety and transaction-integrity assertions passed."
}

start_service_for_manual_gate() {
  local baseline
  baseline="$(count_control_plane_procs)"

  SERVER_LOG="$TMP_DIR/service.log"
  (
    cd "$REPO_ROOT"
    "${PYTHON_CMD[@]}" -m uvicorn clickup_control_plane.app:app \
      --host "$CONTROL_PLANE_HOST" \
      --port "$CONTROL_PLANE_PORT" \
      --log-level warning >"$SERVER_LOG" 2>&1
  ) &
  SERVER_PID=$!

  local waited=0
  while [ "$waited" -lt 15 ]; do
    if curl -sS --max-time 2 -o /dev/null "http://${CONTROL_PLANE_HOST}:${CONTROL_PLANE_PORT}/docs"; then
      break
    fi
    sleep 1
    waited=$((waited + 1))
  done

  if ! curl -sS --max-time 2 -o /dev/null "http://${CONTROL_PLANE_HOST}:${CONTROL_PLANE_PORT}/docs"; then
    fail "Control-plane service failed to start for manual gate (see $SERVER_LOG)."
  fi

  pass "Control-plane service started for manual verification."
  info "Webhook URL: http://${CONTROL_PLANE_HOST}:${CONTROL_PLANE_PORT}/control-plane/clickup/webhook"

  stop_service_if_running
  assert_no_new_control_plane_procs "$baseline" "manual-gate service shutdown"
}

require_manual_confirmation() {
  local prompt="$1"
  if ! is_interactive_mode; then
    blocked_manual "$prompt"
  fi

  local reply
  read -r -p "$prompt [y/N]: " reply
  case "$reply" in
    y|Y|yes|YES)
      pass "Manual verification confirmed."
      ;;
    *)
      fail "Manual verification not confirmed."
      ;;
  esac
}

print_verify_commands() {
  cat <<'CMDS'
Verification commands:

  scripts/e2e_015_control_plane_dispatch.sh verify specs/015-control-plane-dispatch/e2e.env
  uv run pytest tests/contract/test_clickup_control_plane_contract.py -q
  uv run pytest tests/unit/clickup_control_plane -q
  uv run pytest tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q
  sqlite3 .speckit/control-plane.db ".tables"
  sqlite3 .speckit/control-plane.db "select count(*) from processed_events;"
  sqlite3 .speckit/control-plane.db "select count(*) from active_task_runs where state='running';"
CMDS
}

section_preflight() {
  start_section "Section 1: Preflight"

  require_cmd curl
  require_cmd "${PYTHON_CMD[0]}"

  create_temp_workspace
  validate_required_env
  validate_clickup_dependency
  validate_n8n_dependency
  collect_control_plane_tests

  pass "Section 1 complete."
}

section_us1() {
  start_section "Section 2: User Story 1"

  create_temp_workspace
  validate_required_env
  validate_clickup_dependency
  validate_n8n_dependency

  run_us1_automated_suite

  # Manual external-system verification gate
  start_service_for_manual_gate
  require_manual_confirmation \
    "Move an allowlisted ClickUp task to trigger status, confirm exactly one n8n dispatch, and confirm visible outcome update on task"

  pass "Section 2 complete."
}

section_final() {
  start_section "Section Final: Full Feature E2E"

  create_temp_workspace
  validate_required_env
  validate_clickup_dependency
  validate_n8n_dependency

  print_verify_commands
  require_manual_confirmation \
    "Confirm final end-to-end external behavior in ClickUp and n8n is correct for this run"

  pass "Final section complete."
}

section_verify() {
  start_section "Verification"

  create_temp_workspace
  validate_required_env
  validate_clickup_dependency
  validate_n8n_dependency
  print_verify_commands

  local baseline
  baseline="$(count_control_plane_procs)"
  assert_no_new_control_plane_procs "$baseline" "verify section"

  if [ -f "$CONTROL_PLANE_DB_PATH" ]; then
    "${PYTHON_CMD[@]}" - "$CONTROL_PLANE_DB_PATH" <<'PY'
import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("verify: db not present yet")
    raise SystemExit(0)

conn = sqlite3.connect(str(path))
cur = conn.cursor()

tables = [row[0] for row in cur.execute("select name from sqlite_master where type='table'")]
print("verify: db tables:", ", ".join(sorted(tables)))

if "processed_events" in tables:
    n = cur.execute("select count(*) from processed_events").fetchone()[0]
    print(f"verify: processed_events={n}")
if "active_task_runs" in tables:
    n = cur.execute("select count(*) from active_task_runs where state='running'").fetchone()[0]
    print(f"verify: active_task_runs_running={n}")

conn.close()
PY
  else
    warn "DB file not present for lightweight DB verify yet: $CONTROL_PLANE_DB_PATH"
  fi

  pass "Verify section complete."
}

section_ci() {
  E2E_NON_INTERACTIVE=1

  section_preflight

  start_section "Section 2 (CI): Automated US1"
  create_temp_workspace
  validate_required_env
  validate_clickup_dependency
  validate_n8n_dependency
  run_us1_automated_suite

  section_verify
  pass "CI mode complete."
}

if [[ "$COMMAND" == "-h" || "$COMMAND" == "--help" ]]; then
  usage
  exit 0
fi

case "$COMMAND" in
  preflight|run|verify|full|ci)
    CONFIG_PATH="${2:-$CONFIG_PATH}"
    ;;
  *.env|*.yaml|*.yml)
    CONFIG_PATH="$COMMAND"
    COMMAND="full"
    ;;
  *)
    usage
    exit 1
    ;;
esac

case "$COMMAND" in
  preflight)
    section_preflight
    ;;
  run)
    section_us1
    ;;
  verify)
    section_verify
    ;;
  full)
    section_preflight
    section_us1
    section_final
    section_verify
    ;;
  ci)
    section_ci
    ;;
esac

echo ""
echo "E2E pipeline command '$COMMAND' completed."
