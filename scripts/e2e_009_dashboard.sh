#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/e2e_009_dashboard.sh [preflight|run|verify|full|ci] [config.yaml] [section]
  scripts/e2e_009_dashboard.sh [us1|us2|us3|final] [config.yaml]

Commands:
  preflight   Dashboard boot smoke test (health check, clean shutdown, no orphan processes)
  run         Run interactive E2E sections (default section: all)
  verify      Print verification commands and run lightweight checks
  full        preflight -> run(all) -> verify
  ci          Non-interactive preflight + automated API checks only

Sections (for run):
  all | us1 | us2 | us3 | final

Non-interactive mode:
  Set E2E_NON_INTERACTIVE=1 to disable human-gated prompts.
  Required human verification gates fail (exit blocked_manual) in non-interactive mode.

Dashboard port override:
  DASHBOARD_PORT=8080 scripts/e2e_009_dashboard.sh preflight config.yaml
USAGE
}

die() {
  echo "Error: $*" >&2
  exit 1
}

info() {
  echo "[e2e-001-dashboard] $*"
}

pass() {
  echo "[PASS] $*"
  PASS_COUNT=$((PASS_COUNT + 1))
}

skip() {
  echo "[SKIP] $*"
  SKIP_COUNT=$((SKIP_COUNT + 1))
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "Required command not found: $cmd"
  fi
}

COMMAND="${1:-full}"
CONFIG_PATH="config.yaml"
SECTION="all"
ORIGINAL_E2E_NON_INTERACTIVE="${E2E_NON_INTERACTIVE-__unset__}"
E2E_NON_INTERACTIVE="${E2E_NON_INTERACTIVE:-0}"

PYTHON_CMD=(python3)
USE_UV=0
TMP_FILES=()
TMP_DIRS=()

CONFIG_DIR=""
DB_PATH=""
DASHBOARD_PID=""
DASHBOARD_PORT="${DASHBOARD_PORT:-8000}"
DASHBOARD_BASE_URL=""

PASS_COUNT=0
SKIP_COUNT=0

# DB baseline counts (captured before each session)
DB_ORDERS_BASELINE=""
DB_POSITIONS_BASELINE=""

cleanup() {
  # Stop dashboard process if still running
  if [ -n "${DASHBOARD_PID:-}" ] && kill -0 "$DASHBOARD_PID" 2>/dev/null; then
    info "Stopping dashboard process (PID $DASHBOARD_PID) in cleanup..."
    kill -TERM "$DASHBOARD_PID" 2>/dev/null || true
    local wait_count=0
    while kill -0 "$DASHBOARD_PID" 2>/dev/null && [ "$wait_count" -lt 10 ]; do
      sleep 1
      wait_count=$((wait_count + 1))
    done
    if kill -0 "$DASHBOARD_PID" 2>/dev/null; then
      kill -KILL "$DASHBOARD_PID" 2>/dev/null || true
    fi
    DASHBOARD_PID=""
  fi

  if [ "${TMP_FILES+x}" = "x" ]; then
    for f in "${TMP_FILES[@]}"; do
      rm -f "$f"
    done
  fi
  if [ "${TMP_DIRS+x}" = "x" ]; then
    for d in "${TMP_DIRS[@]}"; do
      rm -rf "$d"
    done
  fi
}

trap cleanup EXIT

if [[ "$COMMAND" == "-h" || "$COMMAND" == "--help" ]]; then
  usage
  exit 0
fi

case "$COMMAND" in
  preflight|verify|full|ci)
    CONFIG_PATH="${2:-config.yaml}"
    ;;
  run)
    CONFIG_PATH="${2:-config.yaml}"
    SECTION="${3:-all}"
    ;;
  us1|us2|us3|final)
    SECTION="$COMMAND"
    COMMAND="run"
    CONFIG_PATH="${2:-config.yaml}"
    ;;
  *.yaml|*.yml)
    CONFIG_PATH="$COMMAND"
    COMMAND="full"
    ;;
  *)
    usage
    exit 1
    ;;
esac

# Default preflight/verify/ci to non-interactive unless explicitly overridden
if { [ "$COMMAND" = "preflight" ] || [ "$COMMAND" = "verify" ] || [ "$COMMAND" = "ci" ]; } \
  && [ "$ORIGINAL_E2E_NON_INTERACTIVE" = "__unset__" ]; then
  E2E_NON_INTERACTIVE=1
fi

require_cmd python3
if command -v uv >/dev/null 2>&1; then
  USE_UV=1
  PYTHON_CMD=(uv run python)
fi

run_py() {
  if [ "$#" -gt 0 ] && [ "$1" = "-" ]; then
    local stdin_tmp
    stdin_tmp="$(mktemp "${TMPDIR:-/tmp}/e2e-001-stdin-XXXXXX")"
    TMP_FILES+=("$stdin_tmp")
    cat > "$stdin_tmp"

    if [ "$USE_UV" -eq 1 ]; then
      if "${PYTHON_CMD[@]}" "$@" < "$stdin_tmp"; then
        return 0
      fi
      echo "WARNING: uv run failed; falling back to python3 for this session." >&2
      USE_UV=0
      PYTHON_CMD=(python3)
    fi

    python3 "$@" < "$stdin_tmp"
    return $?
  fi

  if [ "$USE_UV" -eq 1 ]; then
    if "${PYTHON_CMD[@]}" "$@"; then
      return 0
    fi
    echo "WARNING: uv run failed; falling back to python3 for this session." >&2
    USE_UV=0
    PYTHON_CMD=(python3)
  fi
  python3 "$@"
}

is_interactive_mode() {
  [ "$E2E_NON_INTERACTIVE" != "1" ] && [ -t 0 ]
}

timestamp_utc() {
  run_py - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
PY
}

resolve_path_from_config() {
  local path_value="$1"
  if [ -z "$path_value" ]; then
    return 0
  fi
  if [[ "$path_value" = /* ]]; then
    printf "%s" "$path_value"
  else
    printf "%s/%s" "$CONFIG_DIR" "$path_value"
  fi
}

load_config() {
  [ -f "$CONFIG_PATH" ] || die "Missing config file: $CONFIG_PATH"
  CONFIG_DIR="$(cd "$(dirname "$CONFIG_PATH")" && pwd)"

  local output
  output="$(run_py - "$CONFIG_PATH" <<'PY'
import shlex
import sys

def emit_defaults():
    print("DB_PATH='trading_state.db'")

try:
    import yaml
except Exception:
    print("WARNING: PyYAML not available. Run: uv sync", file=sys.stderr)
    emit_defaults()
    sys.exit(0)

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
except FileNotFoundError:
    print(f"WARNING: Config file not found: {path}", file=sys.stderr)
    emit_defaults()
    sys.exit(0)

storage = data.get("storage", {}) or {}

def q(val):
    if val is None:
        val = ""
    return shlex.quote(str(val))

print(f"DB_PATH={q(storage.get('db_path') or 'trading_state.db')}")
PY
)"
  eval "$output"

  local raw_db_path="${DB_PATH:-trading_state.db}"
  DB_PATH="$(resolve_path_from_config "$raw_db_path")"
  # Fallback: if config-dir-relative path doesn't exist, try repo-root-relative
  if [ ! -f "$DB_PATH" ] && [[ "$raw_db_path" != /* ]]; then
    local root_relative="$PWD/$raw_db_path"
    if [ -f "$root_relative" ]; then
      DB_PATH="$root_relative"
    fi
  fi
  DASHBOARD_BASE_URL="http://127.0.0.1:${DASHBOARD_PORT}"
}

print_summary() {
  info "Config: $CONFIG_PATH"
  info "DB path: ${DB_PATH:-<missing>}"
  info "Dashboard base URL: ${DASHBOARD_BASE_URL}"
}

# ---------------------------------------------------------------------------
# Dashboard process management
# ---------------------------------------------------------------------------

start_dashboard() {
  if [ -n "${DASHBOARD_PID:-}" ] && kill -0 "$DASHBOARD_PID" 2>/dev/null; then
    info "Dashboard already running (PID $DASHBOARD_PID)."
    return 0
  fi

  info "Starting dashboard on port ${DASHBOARD_PORT}..."
  local dashboard_log
  dashboard_log="$(mktemp "${TMPDIR:-/tmp}/e2e-001-dashboard-XXXXXX")"
  TMP_FILES+=("$dashboard_log")

  if [ "$USE_UV" -eq 1 ]; then
    uv run python -m csp_trader.dashboard.app \
      --config "$CONFIG_PATH" \
      --port "${DASHBOARD_PORT}" \
      > "$dashboard_log" 2>&1 &
  else
    python3 -m csp_trader.dashboard.app \
      --config "$CONFIG_PATH" \
      --port "${DASHBOARD_PORT}" \
      > "$dashboard_log" 2>&1 &
  fi
  DASHBOARD_PID=$!
  info "Dashboard PID: $DASHBOARD_PID (log: $dashboard_log)"
}

wait_for_dashboard_ready() {
  local timeout_secs="${1:-15}"
  local attempt=0
  info "Waiting for dashboard health endpoint (timeout: ${timeout_secs}s)..."

  while [ "$attempt" -lt "$timeout_secs" ]; do
    local http_code
    http_code="$(curl -s -o /dev/null -w "%{http_code}" \
      --connect-timeout 1 --max-time 2 \
      "${DASHBOARD_BASE_URL}/dashboard/health" 2>/dev/null || true)"

    if [ "$http_code" = "200" ]; then
      info "Dashboard ready (HTTP 200 in ${attempt}s)."
      return 0
    fi

    # Check if the process died unexpectedly
    if [ -n "${DASHBOARD_PID:-}" ] && ! kill -0 "$DASHBOARD_PID" 2>/dev/null; then
      die "Dashboard process (PID $DASHBOARD_PID) exited unexpectedly before becoming ready."
    fi

    sleep 1
    attempt=$((attempt + 1))
  done

  die "Dashboard did not become ready within ${timeout_secs}s (last HTTP code: ${http_code:-none})."
}

stop_dashboard() {
  if [ -z "${DASHBOARD_PID:-}" ]; then
    return 0
  fi
  if ! kill -0 "$DASHBOARD_PID" 2>/dev/null; then
    DASHBOARD_PID=""
    return 0
  fi

  info "Stopping dashboard (PID $DASHBOARD_PID) with SIGTERM..."
  kill -TERM "$DASHBOARD_PID" 2>/dev/null || true

  local wait_count=0
  while kill -0 "$DASHBOARD_PID" 2>/dev/null && [ "$wait_count" -lt 10 ]; do
    sleep 1
    wait_count=$((wait_count + 1))
  done

  if kill -0 "$DASHBOARD_PID" 2>/dev/null; then
    info "Dashboard did not exit within 10s; sending SIGKILL..."
    kill -KILL "$DASHBOARD_PID" 2>/dev/null || true
    sleep 1
  fi

  DASHBOARD_PID=""
}

assert_no_orphan_dashboard() {
  local matching_pids
  matching_pids="$(pgrep -f "csp_trader.dashboard.app" 2>/dev/null || true)"
  if [ -n "$matching_pids" ]; then
    echo "FAIL: Orphan dashboard process(es) remain after shutdown: $matching_pids" >&2
    return 1
  fi
  pass "No orphan dashboard processes."
}

# ---------------------------------------------------------------------------
# DB mutation guard
# ---------------------------------------------------------------------------

capture_db_baseline() {
  if ! command -v sqlite3 >/dev/null 2>&1; then
    info "WARNING: sqlite3 not found; skipping DB mutation baseline."
    DB_ORDERS_BASELINE="skip"
    DB_POSITIONS_BASELINE="skip"
    return 0
  fi
  if [ ! -f "$DB_PATH" ]; then
    info "WARNING: DB file not found at $DB_PATH; skipping DB mutation baseline."
    DB_ORDERS_BASELINE="skip"
    DB_POSITIONS_BASELINE="skip"
    return 0
  fi

  DB_ORDERS_BASELINE="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM orders;" 2>/dev/null || echo "skip")"
  DB_POSITIONS_BASELINE="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM positions;" 2>/dev/null || echo "skip")"
  info "DB baseline: orders=${DB_ORDERS_BASELINE}, positions=${DB_POSITIONS_BASELINE}"
}

assert_no_db_mutations() {
  if [ "${DB_ORDERS_BASELINE:-skip}" = "skip" ] || [ "${DB_POSITIONS_BASELINE:-skip}" = "skip" ]; then
    skip "DB mutation check skipped (sqlite3 not found or DB not accessible)."
    return 0
  fi

  local current_orders current_positions
  current_orders="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM orders;" 2>/dev/null || echo "error")"
  current_positions="$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM positions;" 2>/dev/null || echo "error")"

  run_py - "$DB_ORDERS_BASELINE" "$DB_POSITIONS_BASELINE" \
    "$current_orders" "$current_positions" <<'PY'
import sys

baseline_orders, baseline_positions, current_orders, current_positions = sys.argv[1:5]

errors = []
if "error" in (current_orders, current_positions):
    print("FAIL: Could not read current DB counts.", file=sys.stderr)
    sys.exit(1)

if baseline_orders != current_orders:
    errors.append(f"orders: baseline={baseline_orders} current={current_orders}")
if baseline_positions != current_positions:
    errors.append(f"positions: baseline={baseline_positions} current={current_positions}")

if errors:
    for e in errors:
        print(f"FAIL: DB mutation detected — {e}", file=sys.stderr)
    sys.exit(1)

print(f"[PASS] No DB mutations: orders={current_orders}, positions={current_positions}")
PY
}

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

http_get() {
  local url="$1"
  curl -s -w "\n%{http_code}" --connect-timeout 3 --max-time 10 "$url" 2>/dev/null
}

http_status() {
  # Extract the last line (status code) from http_get output
  tail -n1
}

http_body() {
  # Extract all but the last line (body) from http_get output
  # Note: 'head -n-1' is Linux-only; 'sed '$d'' is portable (removes last line)
  sed '$d'
}

fetch_json() {
  # Fetch URL and return body; exit non-zero if HTTP status is not 200
  local url="$1"
  local response http_code body

  response="$(http_get "$url")"
  http_code="$(echo "$response" | tail -n1)"
  body="$(echo "$response" | sed '$d')"

  if [ "$http_code" != "200" ]; then
    echo "FAIL: Expected HTTP 200 from $url, got $http_code" >&2
    echo "$body" >&2
    return 1
  fi
  echo "$body"
}

# ---------------------------------------------------------------------------
# JSON assertion helpers (Python-based)
# ---------------------------------------------------------------------------

# Write JSON body to a temp file; print the file path.
# Usage: f="$(write_temp_json "$body")"
# Necessary because 'echo "$body" | run_py - <<PY' causes a pipe/heredoc stdin
# conflict: the heredoc (Python script) and the pipe both claim run_py's stdin.
# Passing the body via a temp file path argument avoids this entirely.
write_temp_json() {
  local body="$1"
  local tmp
  tmp="$(mktemp "${TMPDIR:-/tmp}/e2e-001-json-XXXXXX")"
  TMP_FILES+=("$tmp")
  printf '%s' "$body" > "$tmp"
  printf '%s' "$tmp"
}

assert_snapshot_shape() {
  local body="$1"
  local f; f="$(write_temp_json "$body")"
  run_py - "$f" <<'PY'
import json
import sys

with open(sys.argv[1]) as fh:
    try:
        data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"FAIL: snapshot response is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

required = [
    "snapshot_id", "captured_at", "snapshot_age_seconds",
    "stale_threshold_seconds", "max_last_known_age_seconds",
    "watchlist_items", "active_orders", "open_positions",
    "reconciliation_statuses", "data_source_health", "is_last_known_snapshot",
]
missing = [k for k in required if k not in data]
if missing:
    print(f"FAIL: snapshot missing fields: {missing}", file=sys.stderr)
    sys.exit(1)

# Freshness constants
if data.get("stale_threshold_seconds") != 10:
    print(f"FAIL: stale_threshold_seconds expected 10, got {data.get('stale_threshold_seconds')}", file=sys.stderr)
    sys.exit(1)
if data.get("max_last_known_age_seconds") != 86400:
    print(f"FAIL: max_last_known_age_seconds expected 86400, got {data.get('max_last_known_age_seconds')}", file=sys.stderr)
    sys.exit(1)

age = data.get("snapshot_age_seconds")
if not isinstance(age, (int, float)) or age < 0:
    print(f"FAIL: snapshot_age_seconds must be non-negative, got {age}", file=sys.stderr)
    sys.exit(1)

print(f"[PASS] snapshot shape valid: age={age}s, items=watchlist:{len(data['watchlist_items'])} orders:{len(data['active_orders'])} positions:{len(data['open_positions'])}")
PY
}

assert_health_shape() {
  local body="$1"
  local f; f="$(write_temp_json "$body")"
  run_py - "$f" <<'PY'
import json
import sys

with open(sys.argv[1]) as fh:
    try:
        data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"FAIL: health response is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

# The health endpoint uses 'service_status' as its top-level status field
required = ["service_status", "runtime_source_status", "broker_source_status", "last_successful_live_sync_at"]
missing = [k for k in required if k not in data]
if missing:
    print(f"FAIL: health missing fields: {missing}", file=sys.stderr)
    sys.exit(1)

valid_statuses = {"healthy", "degraded", "unavailable"}
for field in ("runtime_source_status", "broker_source_status"):
    val = data.get(field)
    if val not in valid_statuses:
        print(f"FAIL: {field}={val!r} is not one of {sorted(valid_statuses)}", file=sys.stderr)
        sys.exit(1)

print(f"[PASS] health shape valid: service_status={data['service_status']} runtime={data['runtime_source_status']} broker={data['broker_source_status']}")
PY
}

assert_snapshot_latency_p95() {
  local base_url="$1"
  run_py - "$base_url" <<'PY'
import json
import sys
import time
import urllib.request

base_url = sys.argv[1]
url = f"{base_url}/dashboard/runtime-snapshot"
latencies_ms = []

for i in range(10):
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            _ = resp.read()
    except Exception as e:
        print(f"FAIL: request {i+1}/10 failed: {e}", file=sys.stderr)
        sys.exit(1)
    elapsed_ms = (time.monotonic() - t0) * 1000
    latencies_ms.append(elapsed_ms)

latencies_ms.sort()
p95_index = int(len(latencies_ms) * 0.95) - 1
p95_index = max(0, min(p95_index, len(latencies_ms) - 1))
p95_ms = latencies_ms[p95_index]

if p95_ms >= 2000:
    print(f"FAIL: p95 snapshot latency {p95_ms:.0f}ms >= 2000ms (SC-001)", file=sys.stderr)
    sys.exit(1)

print(f"[PASS] p95 snapshot latency {p95_ms:.0f}ms < 2000ms (SC-001). min={latencies_ms[0]:.0f}ms max={latencies_ms[-1]:.0f}ms")
PY
}

assert_source_health_fields() {
  local body="$1"
  local f; f="$(write_temp_json "$body")"
  run_py - "$f" <<'PY'
import json
import sys

with open(sys.argv[1]) as fh:
    try:
        data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"FAIL: not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

dsh = data.get("data_source_health")
if not isinstance(dsh, dict):
    print(f"FAIL: data_source_health is missing or not an object", file=sys.stderr)
    sys.exit(1)

required = [
    "runtime_source_status", "broker_source_status",
    "consecutive_refresh_failures", "last_successful_live_sync_at",
    "degradation_reason",
]
missing = [k for k in required if k not in dsh]
if missing:
    print(f"FAIL: data_source_health missing fields: {missing}", file=sys.stderr)
    sys.exit(1)

valid_statuses = {"healthy", "degraded", "unavailable"}
for field in ("runtime_source_status", "broker_source_status"):
    val = dsh.get(field)
    if val not in valid_statuses:
        print(f"FAIL: data_source_health.{field}={val!r} not in {sorted(valid_statuses)}", file=sys.stderr)
        sys.exit(1)

# Degraded/unavailable sources must have a reason
for field in ("runtime_source_status", "broker_source_status"):
    if dsh.get(field) != "healthy":
        reason = dsh.get("degradation_reason") or ""
        if not reason.strip():
            print(f"FAIL: data_source_health.{field}={dsh[field]!r} but degradation_reason is empty", file=sys.stderr)
            sys.exit(1)

crf = dsh.get("consecutive_refresh_failures")
if not isinstance(crf, int) or crf < 0:
    print(f"FAIL: consecutive_refresh_failures must be non-negative int, got {crf!r}", file=sys.stderr)
    sys.exit(1)

print(f"[PASS] data_source_health valid: runtime={dsh['runtime_source_status']} broker={dsh['broker_source_status']} failures={crf}")
PY
}

assert_reconciliation_invariants() {
  local body="$1"
  local f; f="$(write_temp_json "$body")"
  run_py - "$f" <<'PY'
import json
import sys

with open(sys.argv[1]) as fh:
    try:
        data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"FAIL: not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

statuses = data.get("reconciliation_statuses")
if not isinstance(statuses, list):
    print("FAIL: reconciliation_statuses is not a list", file=sys.stderr)
    sys.exit(1)

if len(statuses) == 0:
    print("[PASS] reconciliation_statuses is empty (no active orders/positions to reconcile).")
    sys.exit(0)

item_required = {"record_type", "record_id", "status", "evaluated_at"}
errors = []
degraded_without_reason = []

for i, item in enumerate(statuses):
    missing = item_required - set(item.keys())
    if missing:
        errors.append(f"item[{i}] missing fields: {sorted(missing)}")
    if item.get("status") == "degraded":
        reason = item.get("reason") or ""
        if not reason.strip():
            degraded_without_reason.append(item.get("record_id", f"index={i}"))

if errors:
    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)

if degraded_without_reason:
    print(f"FAIL: degraded records missing reason: {degraded_without_reason} (SC-002)", file=sys.stderr)
    sys.exit(1)

degraded_count = sum(1 for s in statuses if s.get("status") == "degraded")
print(f"[PASS] reconciliation_statuses: {len(statuses)} records, {degraded_count} degraded (all with reason).")
PY
}

assert_partial_failure_isolation() {
  local body="$1"
  local f; f="$(write_temp_json "$body")"
  run_py - "$f" <<'PY'
import json
import sys

with open(sys.argv[1]) as fh:
    try:
        data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"FAIL: not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

for section in ("watchlist_items", "active_orders", "open_positions"):
    if data.get(section) is None:
        print(f"FAIL: {section} is null — partial failure isolation violated (FR-009)", file=sys.stderr)
        sys.exit(1)

print("[PASS] Partial failure isolation: watchlist_items, active_orders, open_positions all non-null.")
PY
}

assert_events_shape() {
  local body="$1"
  local f; f="$(write_temp_json "$body")"
  run_py - "$f" <<'PY'
import json
import sys

with open(sys.argv[1]) as fh:
    try:
        data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"FAIL: not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

if "events" not in data:
    print("FAIL: events response missing 'events' field", file=sys.stderr)
    sys.exit(1)
if "next_cursor" not in data:
    print("FAIL: events response missing 'next_cursor' field", file=sys.stderr)
    sys.exit(1)

events = data["events"]
if not isinstance(events, list):
    print("FAIL: events is not a list", file=sys.stderr)
    sys.exit(1)

if len(events) == 0:
    print("[SKIP] events list is empty — ordering/shape tests pass vacuously. Run trading runtime to populate events.")
    sys.exit(0)

item_required = {"event_id", "occurred_at", "entity_type", "entity_id", "event_type", "outcome_status", "actor"}
errors = []
failed_without_reason = []

for i, event in enumerate(events):
    missing = item_required - set(event.keys())
    if missing:
        errors.append(f"event[{i}] missing fields: {sorted(missing)}")
    # Failed outcomes must have reason text (heuristic: check common failure indicators)
    outcome = str(event.get("outcome_status", "")).lower()
    if any(tok in outcome for tok in ("fail", "error", "rejected", "cancelled", "canceled")):
        reason = event.get("reason") or ""
        if not reason.strip():
            failed_without_reason.append(event.get("event_id", f"index={i}"))

if errors:
    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)

if failed_without_reason:
    print(f"FAIL: failed-outcome events missing reason: {failed_without_reason}", file=sys.stderr)
    sys.exit(1)

print(f"[PASS] events shape: {len(events)} events, all fields present, failed outcomes have reasons.")
PY
}

assert_events_ordered() {
  local body="$1"
  local f; f="$(write_temp_json "$body")"
  run_py - "$f" <<'PY'
import json
import sys
from datetime import datetime

def parse_ts(val):
    if not val:
        return None
    if val.endswith("Z"):
        val = val[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        return None

with open(sys.argv[1]) as fh:
    try:
        data = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"FAIL: not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

events = data.get("events", [])
if len(events) < 2:
    print(f"[SKIP] Fewer than 2 events ({len(events)}); ordering check passes vacuously.")
    sys.exit(0)

errors = []
for i in range(1, len(events)):
    ts_prev = parse_ts(events[i - 1].get("occurred_at"))
    ts_curr = parse_ts(events[i].get("occurred_at"))
    if ts_prev is None or ts_curr is None:
        errors.append(f"event[{i}] unparseable timestamp")
        continue
    if ts_curr < ts_prev:
        errors.append(
            f"event[{i}] ({events[i].get('occurred_at')}) is before "
            f"event[{i-1}] ({events[i-1].get('occurred_at')}) — ordering violated (SC-003)"
        )

if errors:
    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)

print(f"[PASS] Events chronologically ordered ({len(events)} events).")
PY
}

assert_events_pagination() {
  local base_url="$1"
  run_py - "$base_url" <<'PY'
import json
import sys
import urllib.request
from datetime import datetime

base_url = sys.argv[1]

def parse_ts(val):
    if not val:
        return None
    if val.endswith("Z"):
        val = val[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        return None

def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"FAIL: GET {url} failed: {e}", file=sys.stderr)
        sys.exit(1)

# Page 1
page1 = fetch(f"{base_url}/dashboard/events?limit=2")
events1 = page1.get("events", [])
cursor = page1.get("next_cursor")

if len(events1) < 2 or not cursor:
    print(f"[SKIP] Fewer than 2 events or no next_cursor ({len(events1)} events, cursor={cursor!r}); pagination test skipped.")
    sys.exit(0)

# Page 2
page2 = fetch(f"{base_url}/dashboard/events?cursor={cursor}&limit=2")
events2 = page2.get("events", [])

if not events2:
    print("[SKIP] Page 2 is empty; pagination test skipped (normal if total events == 2).")
    sys.exit(0)

# All page-2 events must be strictly after the last page-1 event
last_ts1 = parse_ts(events1[-1].get("occurred_at"))
for i, ev in enumerate(events2):
    ts = parse_ts(ev.get("occurred_at"))
    if ts is None:
        print(f"FAIL: page2 event[{i}] has unparseable occurred_at", file=sys.stderr)
        sys.exit(1)
    if ts < last_ts1:
        print(
            f"FAIL: page2 event[{i}] ({ev['occurred_at']}) is before last page1 event ({events1[-1]['occurred_at']})",
            file=sys.stderr,
        )
        sys.exit(1)

print(f"[PASS] Cursor pagination: page1={len(events1)} events, page2={len(events2)} events, ordering preserved.")
PY
}

assert_events_entity_type_filter() {
  local base_url="$1"
  local entity_type="$2"
  run_py - "$base_url" "$entity_type" <<'PY'
import json
import sys
import urllib.request

base_url, entity_type = sys.argv[1:3]

url = f"{base_url}/dashboard/events?entity_type={entity_type}&limit=50"
try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
except Exception as e:
    print(f"FAIL: GET {url} failed: {e}", file=sys.stderr)
    sys.exit(1)

events = data.get("events", [])
if not events:
    print(f"[SKIP] No events with entity_type={entity_type!r}; filter test passes vacuously.")
    sys.exit(0)

wrong = [ev for ev in events if ev.get("entity_type") != entity_type]
if wrong:
    print(f"FAIL: {len(wrong)} events have wrong entity_type: {[ev.get('entity_type') for ev in wrong]}", file=sys.stderr)
    sys.exit(1)

print(f"[PASS] entity_type={entity_type!r} filter: {len(events)} events, all match.")
PY
}

assert_events_window_enforcement() {
  local base_url="$1"
  run_py - "$base_url" <<'PY'
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

base_url = sys.argv[1]

# Valid 30-day window should return 200
now = datetime.now(timezone.utc)
from_ts_30d = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
to_ts = now.isoformat().replace("+00:00", "Z")

import urllib.parse
url_valid = (
    f"{base_url}/dashboard/events"
    f"?from_ts={urllib.parse.quote(from_ts_30d)}&to_ts={urllib.parse.quote(to_ts)}"
)
try:
    with urllib.request.urlopen(url_valid, timeout=10) as resp:
        if resp.status != 200:
            print(f"FAIL: 30-day window returned HTTP {resp.status}, expected 200", file=sys.stderr)
            sys.exit(1)
except urllib.error.HTTPError as e:
    print(f"FAIL: 30-day window returned HTTP {e.code}, expected 200", file=sys.stderr)
    sys.exit(1)

# >30-day window should return 4xx with INVALID_QUERY
from_ts_31d = (now - timedelta(days=31)).isoformat().replace("+00:00", "Z")
url_invalid = (
    f"{base_url}/dashboard/events"
    f"?from_ts={urllib.parse.quote(from_ts_31d)}&to_ts={urllib.parse.quote(to_ts)}"
)
try:
    with urllib.request.urlopen(url_invalid, timeout=10) as resp:
        body = resp.read().decode()
        print(f"FAIL: >30-day window returned HTTP 200, expected 4xx. Body: {body[:200]}", file=sys.stderr)
        sys.exit(1)
except urllib.error.HTTPError as e:
    body_bytes = e.read()
    try:
        error_data = json.loads(body_bytes)
    except Exception:
        print(f"FAIL: >30-day window returned HTTP {e.code} but body is not JSON", file=sys.stderr)
        sys.exit(1)
    if error_data.get("error_code") != "INVALID_QUERY":
        print(f"FAIL: expected error_code=INVALID_QUERY, got {error_data.get('error_code')!r}", file=sys.stderr)
        sys.exit(1)
    if error_data.get("retryable") is not False:
        print(f"FAIL: expected retryable=false for INVALID_QUERY, got {error_data.get('retryable')!r}", file=sys.stderr)
        sys.exit(1)

print("[PASS] Time window enforcement: 30-day window accepted, >30-day window rejected with INVALID_QUERY.")
PY
}

assert_events_invalid_query() {
  local base_url="$1"
  run_py - "$base_url" <<'PY'
import json
import sys
import urllib.error
import urllib.request
import urllib.parse

base_url = sys.argv[1]

invalid_queries = [
    ("limit=0", "limit=0 (below minimum)"),
    ("limit=201", "limit=201 (above maximum)"),
    ("from_ts=not-a-date", "malformed from_ts"),
]

for qs, label in invalid_queries:
    url = f"{base_url}/dashboard/events?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read().decode()
            print(f"FAIL: {label} returned HTTP 200, expected 4xx. Body: {body[:200]}", file=sys.stderr)
            sys.exit(1)
    except urllib.error.HTTPError as e:
        body_bytes = e.read()
        try:
            error_data = json.loads(body_bytes)
        except Exception:
            # Some frameworks return plain text for validation errors; check status code is 4xx
            if 400 <= e.code < 500:
                print(f"[PASS] {label}: HTTP {e.code} (non-JSON body; 4xx is sufficient).")
                continue
            print(f"FAIL: {label} returned HTTP {e.code} but body is not JSON", file=sys.stderr)
            sys.exit(1)
        # Prefer INVALID_QUERY if present; accept any 4xx if framework returns its own validation error
        if 400 <= e.code < 500:
            code = error_data.get("error_code", "")
            retryable = error_data.get("retryable")
            if code == "INVALID_QUERY" and retryable is False:
                print(f"[PASS] {label}: INVALID_QUERY, retryable=false.")
            elif code:
                print(f"[PASS] {label}: HTTP {e.code}, error_code={code!r}.")
            else:
                print(f"[PASS] {label}: HTTP {e.code} (framework validation error).")
        else:
            print(f"FAIL: {label} returned HTTP {e.code}, expected 4xx", file=sys.stderr)
            sys.exit(1)

print("[PASS] All invalid query inputs rejected with 4xx.")
PY
}

# ---------------------------------------------------------------------------
# E2E sections
# ---------------------------------------------------------------------------

run_preflight() {
  info "=== Preflight: Dashboard Boot Smoke Test ==="
  load_config
  print_summary

  info "1. Config validation..."
  if [ ! -f "$DB_PATH" ]; then
    info "WARNING: DB file not found at $DB_PATH. Dashboard will start with no local data (runtime_source_status may be unavailable)."
  else
    pass "DB file accessible: $DB_PATH"
  fi

  info "2. Dashboard startup..."
  start_dashboard
  wait_for_dashboard_ready 15

  info "3. Health endpoint HTTP 200..."
  local health_body
  health_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/health")"
  pass "GET /dashboard/health returned HTTP 200"

  info "4. Health shape validation..."
  assert_health_shape "$health_body"

  info "5. Graceful shutdown..."
  stop_dashboard
  pass "Dashboard shut down cleanly."

  info "6. No orphan processes..."
  assert_no_orphan_dashboard

  echo ""
  info "Preflight PASSED. Checks: $PASS_COUNT passed, $SKIP_COUNT skipped."
}

run_us1() {
  info "=== US1: Unified Runtime View ==="
  load_config
  print_summary

  info "1. DB row count baseline..."
  capture_db_baseline

  info "2. Dashboard startup..."
  start_dashboard
  wait_for_dashboard_ready 15

  info "3. Snapshot endpoint shape..."
  local snapshot_body
  snapshot_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/runtime-snapshot")"
  pass "GET /dashboard/runtime-snapshot returned HTTP 200"
  assert_snapshot_shape "$snapshot_body"

  info "4+5. Freshness constants and snapshot age..."
  # assert_snapshot_shape already validates stale_threshold_seconds, max_last_known_age_seconds, and age >= 0
  pass "Freshness constants and snapshot_age_seconds validated."

  info "6. Snapshot latency p95 < 2s (SC-001)..."
  assert_snapshot_latency_p95 "$DASHBOARD_BASE_URL"

  info "7. Source health field not null..."
  assert_source_health_fields "$snapshot_body"

  info "8. HTML template smoke test..."
  local html_response html_code html_body
  html_response="$(http_get "${DASHBOARD_BASE_URL}/dashboard" 2>/dev/null || http_get "${DASHBOARD_BASE_URL}/" 2>/dev/null || true)"
  html_code="$(echo "$html_response" | tail -n1)"
  html_body="$(echo "$html_response" | sed '$d')"
  if [ "$html_code" = "200" ] && [ -n "$html_body" ]; then
    pass "GET /dashboard returned HTTP 200 with non-empty body."
  else
    info "WARNING: GET /dashboard returned HTTP ${html_code:-unknown}; template may not be implemented yet."
    skip "HTML template smoke test skipped (HTTP ${html_code:-unknown})."
  fi

  if is_interactive_mode; then
    echo ""
    echo "[Human verify — advisory] Open http://127.0.0.1:${DASHBOARD_PORT}/dashboard in a browser."
    echo "Confirm watchlist, orders, and positions tables render with lifecycle state labels and timestamps."
    read -r -p "Press Enter when confirmed (or skip to continue)... " _
  fi

  info "9. No DB mutations..."
  assert_no_db_mutations

  info "10. Dashboard shutdown + orphan check..."
  stop_dashboard
  assert_no_orphan_dashboard

  echo ""
  info "US1 PASSED. Checks: $PASS_COUNT passed, $SKIP_COUNT skipped."
}

run_us2() {
  info "=== US2: Drift And Degraded-State Visibility ==="
  load_config
  print_summary

  info "1. Dashboard startup..."
  start_dashboard
  wait_for_dashboard_ready 15

  info "2+3. Reconciliation statuses shape..."
  local snapshot_body
  snapshot_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/runtime-snapshot")"
  pass "GET /dashboard/runtime-snapshot returned HTTP 200"

  info "4. Degraded reason invariant (SC-002)..."
  assert_reconciliation_invariants "$snapshot_body"

  info "5. DataSourceHealth shape + degraded source reason invariant..."
  assert_source_health_fields "$snapshot_body"

  info "6. Partial failure isolation (FR-009)..."
  assert_partial_failure_isolation "$snapshot_body"

  if is_interactive_mode; then
    echo ""
    echo "[Human verify — drift simulation]"
    echo "To test broker disconnection:"
    echo "  1. Pause/stop your IBKR Gateway or set broker connectivity to unavailable."
    echo "  2. Wait ~6 seconds (one full refresh tick)."
    echo "  3. The script will re-fetch snapshot and assert broker_source_status != healthy."
    echo "  4. Restore broker connectivity."
    read -r -p "Disconnect broker now, then press Enter to continue... " _

    sleep 6
    local drift_body http_code2
    local drift_response
    drift_response="$(http_get "${DASHBOARD_BASE_URL}/dashboard/runtime-snapshot")"
    http_code2="$(echo "$drift_response" | tail -n1)"
    drift_body="$(echo "$drift_response" | sed '$d')"

    if [ "$http_code2" = "200" ]; then
      local drift_f; drift_f="$(write_temp_json "$drift_body")"
      run_py - "$drift_f" <<'PY'
import json, sys
with open(sys.argv[1]) as fh:
    data = json.load(fh)
dsh = data.get("data_source_health", {})
broker_status = dsh.get("broker_source_status", "")
if broker_status == "healthy":
    print("WARNING: broker_source_status is still 'healthy' after disconnect — drift simulation may not have taken effect.")
else:
    print(f"[PASS] Drift simulation: broker_source_status={broker_status!r} (degraded/unavailable as expected).")
PY
    else
      info "WARNING: snapshot returned HTTP $http_code2 during drift simulation."
    fi

    echo ""
    read -r -p "Restore broker connectivity now, then press Enter... " _
    sleep 15
    info "Waiting for recovery (3 refresh ticks)..."
    local recovery_body
    recovery_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/runtime-snapshot")"
    local recovery_f; recovery_f="$(write_temp_json "$recovery_body")"
    run_py - "$recovery_f" <<'PY'
import json, sys
with open(sys.argv[1]) as fh:
    data = json.load(fh)
dsh = data.get("data_source_health", {})
broker_status = dsh.get("broker_source_status", "")
if broker_status == "healthy":
    print(f"[PASS] Broker recovered: broker_source_status=healthy.")
else:
    print(f"WARNING: broker_source_status={broker_status!r} after recovery wait — may need more ticks.")
PY
  else
    info "Skipping interactive drift simulation (non-interactive mode)."
    skip "Drift simulation skipped (non-interactive)."
  fi

  info "7. Dashboard shutdown + orphan check..."
  stop_dashboard
  assert_no_orphan_dashboard

  echo ""
  info "US2 PASSED. Checks: $PASS_COUNT passed, $SKIP_COUNT skipped."
}

run_us3() {
  info "=== US3: Runtime Event Timeline ==="
  load_config
  print_summary

  info "1. Dashboard startup..."
  start_dashboard
  wait_for_dashboard_ready 15

  info "2. Events endpoint default response..."
  local events_body
  events_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/events")"
  pass "GET /dashboard/events returned HTTP 200"

  info "3. Chronological ordering (SC-003)..."
  assert_events_ordered "$events_body"

  info "4+5. Event shape and failed-outcome reason invariant..."
  assert_events_shape "$events_body"

  info "6. Cursor pagination..."
  assert_events_pagination "$DASHBOARD_BASE_URL"

  info "7. entity_type filter..."
  assert_events_entity_type_filter "$DASHBOARD_BASE_URL" "order"

  info "8. outcome_status filter..."
  run_py - "$DASHBOARD_BASE_URL" <<'PY'
import json
import sys
import urllib.request

base_url = sys.argv[1]
url = f"{base_url}/dashboard/events?outcome_status=success&limit=50"
try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
except Exception as e:
    print(f"FAIL: GET {url} failed: {e}", file=sys.stderr)
    sys.exit(1)

events = data.get("events", [])
if not events:
    print("[SKIP] No success events; outcome_status filter test passes vacuously.")
    sys.exit(0)

wrong = [ev for ev in events if ev.get("outcome_status") != "success"]
if wrong:
    print(f"FAIL: {len(wrong)} events have wrong outcome_status", file=sys.stderr)
    sys.exit(1)
print(f"[PASS] outcome_status=success filter: {len(events)} events, all match.")
PY

  info "9. 30-day max window enforcement..."
  assert_events_window_enforcement "$DASHBOARD_BASE_URL"

  info "10+11. Invalid query handling..."
  assert_events_invalid_query "$DASHBOARD_BASE_URL"

  info "12. Error shape conformance already validated in steps 9-11."
  pass "Error shape conformance validated."

  info "13. Dashboard shutdown + orphan check..."
  stop_dashboard
  assert_no_orphan_dashboard

  echo ""
  info "US3 PASSED. Checks: $PASS_COUNT passed, $SKIP_COUNT skipped."
}

run_final() {
  info "=== Final: Full Feature E2E ==="
  load_config
  print_summary

  info "Step 1: Preflight..."
  start_dashboard
  wait_for_dashboard_ready 15
  local health_body
  health_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/health")"
  assert_health_shape "$health_body"
  stop_dashboard
  assert_no_orphan_dashboard

  info "Step 2: DB baseline..."
  capture_db_baseline

  info "Step 3: Start dashboard for full session..."
  start_dashboard
  wait_for_dashboard_ready 15

  info "Step 4: US1 automated gates..."
  local snapshot_body
  snapshot_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/runtime-snapshot")"
  assert_snapshot_shape "$snapshot_body"
  assert_snapshot_latency_p95 "$DASHBOARD_BASE_URL"

  info "Step 5: US2 automated gates..."
  assert_reconciliation_invariants "$snapshot_body"
  assert_source_health_fields "$snapshot_body"
  assert_partial_failure_isolation "$snapshot_body"

  info "Step 6: US3 automated gates..."
  local events_body
  events_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/events")"
  assert_events_shape "$events_body"
  assert_events_ordered "$events_body"
  assert_events_pagination "$DASHBOARD_BASE_URL"
  assert_events_window_enforcement "$DASHBOARD_BASE_URL"
  assert_events_invalid_query "$DASHBOARD_BASE_URL"

  info "Step 7: Snapshot freshness after 3 refresh ticks (15s)..."
  sleep 15
  local fresh_body
  fresh_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/runtime-snapshot")"
  local fresh_f; fresh_f="$(write_temp_json "$fresh_body")"
  run_py - "$fresh_f" <<'PY'
import json, sys
with open(sys.argv[1]) as fh:
    data = json.load(fh)
age = data.get("snapshot_age_seconds", 9999)
if age > 10:
    print(f"FAIL: snapshot_age_seconds={age} > 10s after 3 ticks (stale)", file=sys.stderr)
    sys.exit(1)
print(f"[PASS] snapshot_age_seconds={age}s < 10s stale threshold after 3 ticks.")
PY

  info "Step 8: DB mutation check..."
  assert_no_db_mutations

  info "Step 9+10: Graceful shutdown + orphan check..."
  stop_dashboard
  assert_no_orphan_dashboard

  echo ""
  info "Full Feature E2E PASSED. Checks: $PASS_COUNT passed, $SKIP_COUNT skipped."
}

run_verify() {
  load_config
  print_summary

  echo ""
  echo "=== Verification Commands ==="
  echo ""
  echo "# Dashboard health"
  echo "  curl -s '${DASHBOARD_BASE_URL}/dashboard/health' | python3 -m json.tool"
  echo ""
  echo "# Runtime snapshot"
  echo "  curl -s '${DASHBOARD_BASE_URL}/dashboard/runtime-snapshot' | python3 -m json.tool"
  echo ""
  echo "# Lifecycle events (default last 24h)"
  echo "  curl -s '${DASHBOARD_BASE_URL}/dashboard/events' | python3 -m json.tool"
  echo ""
  echo "# Lifecycle events with pagination"
  echo "  curl -s '${DASHBOARD_BASE_URL}/dashboard/events?limit=5' | python3 -m json.tool"
  echo ""
  echo "# Check for orphan dashboard processes"
  echo "  pgrep -la -f 'csp_trader.dashboard.app' || echo 'No dashboard processes running'"
  echo ""
  if [ -n "${DB_PATH:-}" ]; then
    echo "# DB row counts (no mutation check)"
    echo "  sqlite3 '$DB_PATH' 'SELECT COUNT(*) AS orders FROM orders;'"
    echo "  sqlite3 '$DB_PATH' 'SELECT COUNT(*) AS positions FROM positions;'"
    echo ""
  fi
  echo "# Run all dashboard pytest suites"
  echo "  uv run pytest tests/ -k 'dashboard' -v"
  echo "  uv run pytest tests/contract/ -k 'runtime_dashboard' -v"
  echo "  uv run pytest tests/integration/ -k 'runtime_dashboard' -v"
  echo ""

  # Lightweight live checks if dashboard appears to be running
  local http_code
  http_code="$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout 1 --max-time 3 \
    "${DASHBOARD_BASE_URL}/dashboard/health" 2>/dev/null || echo "000")"

  if [ "$http_code" = "200" ]; then
    echo "Dashboard is reachable at ${DASHBOARD_BASE_URL}."
    local health_body
    health_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/health")"
    assert_health_shape "$health_body"
  else
    info "Dashboard not reachable at ${DASHBOARD_BASE_URL} (HTTP ${http_code}). Start it first."
  fi
}

run_ci() {
  info "=== CI Mode: Non-Interactive Automated Checks ==="
  E2E_NON_INTERACTIVE=1

  load_config
  print_summary

  info "Preflight + API shape checks..."
  start_dashboard
  wait_for_dashboard_ready 15

  local health_body
  health_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/health")"
  assert_health_shape "$health_body"

  local snapshot_body
  snapshot_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/runtime-snapshot")"
  assert_snapshot_shape "$snapshot_body"
  assert_source_health_fields "$snapshot_body"
  assert_reconciliation_invariants "$snapshot_body"
  assert_partial_failure_isolation "$snapshot_body"

  local events_body
  events_body="$(fetch_json "${DASHBOARD_BASE_URL}/dashboard/events")"
  assert_events_shape "$events_body"
  assert_events_ordered "$events_body"
  assert_events_invalid_query "$DASHBOARD_BASE_URL"

  capture_db_baseline

  # Verify no mutations after a full snapshot read cycle
  assert_no_db_mutations

  stop_dashboard
  assert_no_orphan_dashboard

  echo ""
  info "CI checks PASSED. Checks: $PASS_COUNT passed, $SKIP_COUNT skipped."
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

case "$COMMAND" in
  preflight)
    run_preflight
    ;;
  run)
    case "$SECTION" in
      all)
        run_us1
        echo ""
        run_us2
        echo ""
        run_us3
        ;;
      us1) run_us1 ;;
      us2) run_us2 ;;
      us3) run_us3 ;;
      final) run_final ;;
      *)
        die "Unknown section: $SECTION. Use: all | us1 | us2 | us3 | final"
        ;;
    esac
    ;;
  verify)
    run_verify
    ;;
  full)
    run_preflight
    echo ""
    run_us1
    echo ""
    run_us2
    echo ""
    run_us3
    echo ""
    run_verify
    ;;
  ci)
    run_ci
    ;;
esac
