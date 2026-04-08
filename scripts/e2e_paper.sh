#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/e2e_paper.sh [preflight|run|verify|observe|full] [config/profile.yaml]

Commands:
  preflight  Connects with --dry-run using live config (no orders)
  run        Runs entry + optional exit phases using runtime env overrides
  verify     Prints log/DB checks and runs lightweight queries
  observe    Streams structured events from the active run log (latest-run pointer)
  full       preflight -> run -> verify (default)

Non-interactive run mode:
  Set E2E_NON_INTERACTIVE=1 and pass overrides via env vars:
    E2E_TARGET_TICKER
    E2E_TARGET_PRICE_OVERRIDE (default: 100000.0 for run)
    E2E_ENTRY_FLOOR (default: 1.0 for run)
    E2E_MIN_DTE (default: 1 for run)
    E2E_EXIT_FLOOR (default: 1000.0 for run)
    E2E_RUN_EXIT (Y/N)
    E2E_SPREAD_INTERVAL_SECONDS (default: 1.0 for run)
    E2E_SPREAD_INCREMENT (default: 0.10 for run)

Observe mode env vars:
  E2E_OBSERVE_EVENTS       Comma-separated event filter (default: all)
  E2E_OBSERVE_TAIL_LINES   Initial tail count before follow (default: 200)
  E2E_LOG_FORWARD_FILE     Optional append-only sink file for matched JSON lines
  E2E_LOG_FORWARD_CMD      Optional shell command that receives each JSON line on stdin
USAGE
}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "$cmd not found"
  fi
}

resolve_path_from_config() {
  local path_value="$1"
  if [ -z "$path_value" ]; then
    printf ""
    return
  fi

  if [[ "$path_value" = /* ]]; then
    printf "%s" "$path_value"
  else
    printf "%s/%s" "$CONFIG_DIR" "$path_value"
  fi
}

resolve_pointer_path() {
  local log_root_dir="$1"
  local pointer_name="$2"
  if [[ "$pointer_name" = /* ]]; then
    printf "%s" "$pointer_name"
  else
    printf "%s/%s" "$log_root_dir" "$pointer_name"
  fi
}

resolve_latest_run_log_path() {
  local pointer_path="$1"
  "${PYTHON_CMD[@]}" - "$pointer_path" <<'PY'
import json
import sys
from pathlib import Path

pointer_path = Path(sys.argv[1])
if not pointer_path.exists():
    print(f"latest run pointer not found: {pointer_path}", file=sys.stderr)
    sys.exit(1)

try:
    payload = json.loads(pointer_path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"failed to parse latest run pointer {pointer_path}: {exc}", file=sys.stderr)
    sys.exit(1)

log_path = str(payload.get("log_path") or "").strip()
if not log_path:
    print(f"latest run pointer missing log_path: {pointer_path}", file=sys.stderr)
    sys.exit(1)

print(log_path)
PY
}

COMMAND="${1:-full}"
CONFIG_PATH="config/e2e.yaml"
CONFIG_DIR=""
PYTHON_CMD=(python3)
E2E_NON_INTERACTIVE="${E2E_NON_INTERACTIVE:-0}"
E2E_TEST_TARGET_PRICE_OVERRIDE_DEFAULT="100000.0"
E2E_TEST_ENTRY_FLOOR_DEFAULT="1.0"
E2E_TEST_MIN_DTE_DEFAULT="1"
# Keep exit phase very strict by default so E2E focuses on close behavior.
E2E_TEST_EXIT_FLOOR_DEFAULT="1000.0"
E2E_TEST_SPREAD_INTERVAL_DEFAULT="1.0"
E2E_TEST_SPREAD_INCREMENT_DEFAULT="0.10"

LOG_ROOT_DIR=""
LATEST_RUN_POINTER=""
LATEST_RUN_POINTER_PATH=""

if [[ "$COMMAND" == "-h" || "$COMMAND" == "--help" ]]; then
  usage
  exit 0
fi

case "$COMMAND" in
  preflight|run|verify|observe|full)
    CONFIG_PATH="${2:-$CONFIG_PATH}"
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

[ -f "$CONFIG_PATH" ] || die "Missing config file: $CONFIG_PATH"

if command -v uv >/dev/null 2>&1; then
  PYTHON_CMD=(uv run python)
fi
require_cmd "${PYTHON_CMD[0]}"

load_config() {
  CONFIG_DIR="$(cd "$(dirname "$CONFIG_PATH")" && pwd)"

  local output
  output="$("${PYTHON_CMD[@]}" - "$CONFIG_PATH" <<'PY'
import shlex
import sys

def emit_defaults():
    print("IBKR_HOST=''")
    print("IBKR_PORT=''")
    print("IBKR_CLIENT_ID=''")
    print("LOG_PATH=''")
    print("LOG_ROOT_DIR='logs'")
    print("LATEST_RUN_POINTER='latest-run.json'")
    print("LOG_PATH_TEMPLATE=''")
    print("DB_PATH='trading_state.db'")
    print("DEFAULT_TICKER=''")
    print("DEFAULT_TARGET_PRICE=''")
    print("DEFAULT_MIN_DTE=''")
    print("DEFAULT_ENTRY_FLOOR=''")
    print("DEFAULT_SPREAD_INTERVAL=''")
    print("DEFAULT_SPREAD_INCREMENT=''")

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

ibkr = data.get("ibkr", {}) or {}
storage = data.get("storage", {}) or {}
rules = data.get("rules", {}) or {}
watchlist = data.get("watchlist", []) or []

default_ticker = ""
default_target = ""
if watchlist:
    default_ticker = watchlist[0].get("ticker", "") or ""
    default_target = watchlist[0].get("target_price", "") or ""

def q(val):
    if val is None:
        val = ""
    return shlex.quote(str(val))

print(f"IBKR_HOST={q(ibkr.get('host') or '127.0.0.1')}")
print(f"IBKR_PORT={q(ibkr.get('port'))}")
print(f"IBKR_CLIENT_ID={q(ibkr.get('client_id'))}")
print(f"LOG_PATH={q(storage.get('log_path') or '')}")
print(f"LOG_ROOT_DIR={q(storage.get('log_root_dir') or 'logs')}")
print(f"LATEST_RUN_POINTER={q(storage.get('latest_run_pointer_file') or 'latest-run.json')}")
print(f"LOG_PATH_TEMPLATE={q(storage.get('log_path_template') or '')}")
print(f"DB_PATH={q(storage.get('db_path') or 'trading_state.db')}")
print(f"DEFAULT_TICKER={q(default_ticker)}")
print(f"DEFAULT_TARGET_PRICE={q(default_target)}")
print(f"DEFAULT_MIN_DTE={q(rules.get('min_dte') or '')}")
print(f"DEFAULT_ENTRY_FLOOR={q(rules.get('annualized_return_floor_pct') or '')}")
print(f"DEFAULT_SPREAD_INTERVAL={q(rules.get('spread_adjustment_interval_seconds') or '')}")
print(f"DEFAULT_SPREAD_INCREMENT={q(rules.get('spread_adjustment_increment') or '')}")
PY
)"
  eval "$output"

  LOG_ROOT_DIR="$(resolve_path_from_config "${LOG_ROOT_DIR:-logs}")"
  DB_PATH="$(resolve_path_from_config "${DB_PATH:-trading_state.db}")"

  if [ -n "${LOG_PATH:-}" ]; then
    LOG_PATH="$(resolve_path_from_config "$LOG_PATH")"
  fi

  LATEST_RUN_POINTER_PATH="$(
    resolve_pointer_path \
      "${LOG_ROOT_DIR:-$(resolve_path_from_config "logs")}" \
      "${LATEST_RUN_POINTER:-latest-run.json}"
  )"
}

print_summary() {
  echo "E2E Paper Trading Flow"
  echo "Config: $CONFIG_PATH"
  echo "ibkr.host: ${IBKR_HOST:-<missing>}"
  echo "ibkr.port: ${IBKR_PORT:-<missing>}"
  echo "ibkr.client_id: ${IBKR_CLIENT_ID:-<missing>}"
  echo "log_root_dir: ${LOG_ROOT_DIR:-<missing>}"
  echo "latest_run_pointer: ${LATEST_RUN_POINTER_PATH:-<missing>}"
  echo "db_path: ${DB_PATH:-trading_state.db}"
  if [ -n "${IBKR_PORT:-}" ] && [ "$IBKR_PORT" != "4001" ]; then
    echo "WARNING: ibkr.port is not 4001 (paper)."
  fi
}

warn_if_after_hours() {
  local warning_msg
  warning_msg="$("${PYTHON_CMD[@]}" - <<'PY'
from datetime import datetime, time
from zoneinfo import ZoneInfo

now = datetime.now(ZoneInfo("America/New_York"))
weekday = now.weekday()  # 0=Mon
open_time = time(9, 30)
close_time = time(16, 0)

if weekday < 5 and open_time <= now.time() <= close_time:
    raise SystemExit(0)

if weekday >= 5:
    reason = "weekend"
elif now.time() < open_time:
    reason = "before 09:30 ET"
else:
    reason = "after 16:00 ET"

stamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")
print(f"WARNING: Current time {stamp} is outside regular US options hours ({reason}).")
print("         E2E may show all_options_stale / fresh: 0 and fail order_filled checks.")
print("         Re-run during market hours for entry/exit validation.")
PY
)"
  if [ -n "${warning_msg:-}" ]; then
    echo "$warning_msg"
    echo ""
  fi
}

pause() {
  read -r -p "Press Enter to continue..." _
}

is_interactive_mode() {
  [ "$E2E_NON_INTERACTIVE" != "1" ] && [ -t 0 ]
}

prompt_value() {
  local prompt="$1"
  local default="$2"
  local provided_value="${3:-}"
  local value=""

  if [ -n "$provided_value" ]; then
    printf "%s" "$provided_value"
    return
  fi

  if is_interactive_mode; then
    read -r -p "$prompt" value || true
    value="${value:-$default}"
  else
    value="$default"
    echo "Non-interactive mode: ${prompt}${value}" >&2
  fi

  printf "%s" "$value"
}

timestamp_utc() {
  "${PYTHON_CMD[@]}" - <<'PY'
from datetime import datetime, timezone

print(datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
PY
}

assert_order_filled_since() {
  local log_path="$1"
  local since_ts="$2"
  local ticker="$3"
  local phase="$4"

  "${PYTHON_CMD[@]}" - "$log_path" "$since_ts" "$ticker" "$phase" <<'PY'
import json
import sys
from datetime import datetime

log_path, since_ts, ticker, phase = sys.argv[1:5]

def parse_ts(val: str | None):
    if not val:
        return None
    if val.endswith("Z"):
        val = val[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        return None

since = parse_ts(since_ts)
if since is None:
    print(f"{phase} failed: invalid since timestamp {since_ts}", file=sys.stderr)
    sys.exit(2)

found = False
try:
    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_ts(entry.get("ts"))
            if ts is None or ts < since:
                continue
            if entry.get("event") != "order_filled":
                continue
            event_ticker = entry.get("ticker")
            if ticker and event_ticker and event_ticker != ticker:
                continue
            found = True
            break
except FileNotFoundError:
    print(f"{phase} failed: log file not found: {log_path}", file=sys.stderr)
    sys.exit(2)

if not found:
    if ticker:
        print(f"{phase} failed: no order_filled for {ticker} since {since_ts}", file=sys.stderr)
    else:
        print(f"{phase} failed: no order_filled since {since_ts}", file=sys.stderr)
    sys.exit(1)

print(f"{phase} ok: order_filled observed")
PY
}

active_run_log_path_or_die() {
  local run_log_path
  run_log_path="$(resolve_latest_run_log_path "$LATEST_RUN_POINTER_PATH")" \
    || die "Unable to resolve active run log via $LATEST_RUN_POINTER_PATH"

  if [[ "$run_log_path" != /* ]]; then
    run_log_path="$PWD/$run_log_path"
  fi
  printf "%s" "$run_log_path"
}

run_trader_with_overrides() {
  local target_ticker="$1"
  local target_price_override="$2"
  local floor="$3"
  local min_dte="$4"
  local spread_interval="$5"
  local spread_increment="$6"
  local dry_run_flag="${7:-0}"

  local -a env_args=()
  [ -n "$floor" ] && env_args+=("CSP_OVERRIDE_ANNUALIZED_RETURN_FLOOR_PCT=$floor")
  [ -n "$min_dte" ] && env_args+=("CSP_OVERRIDE_MIN_DTE=$min_dte")
  [ -n "$spread_interval" ] && env_args+=("CSP_OVERRIDE_SPREAD_ADJUSTMENT_INTERVAL_SECONDS=$spread_interval")
  [ -n "$spread_increment" ] && env_args+=("CSP_OVERRIDE_SPREAD_ADJUSTMENT_INCREMENT=$spread_increment")

  if [ -n "$target_ticker" ] && [ -n "$target_price_override" ]; then
    env_args+=("CSP_OVERRIDE_TARGET_TICKER=$target_ticker")
    env_args+=("CSP_OVERRIDE_TARGET_PRICE=$target_price_override")
  fi

  local -a cmd=(uv run csp-trader --config "$CONFIG_PATH")
  if [ "$dry_run_flag" = "1" ]; then
    cmd+=(--dry-run)
  fi

  if [ "${#env_args[@]}" -gt 0 ]; then
    env "${env_args[@]}" "${cmd[@]}"
  else
    "${cmd[@]}"
  fi
}

run_preflight() {
  require_cmd uv
  load_config
  print_summary
  warn_if_after_hours
  assert_runner_lock_available
  echo ""
  echo "Preflight: starting dry-run with live config."
  echo "Press Ctrl+C after a cycle completes (look for cycle_end in logs)."
  run_trader_with_overrides "" "" "" "" "" "" 1
}

assert_runner_lock_available() {
  "${PYTHON_CMD[@]}" - "${IBKR_HOST:-127.0.0.1}" "${IBKR_PORT:-}" "${IBKR_CLIENT_ID:-}" <<'PY'
import json
import sys

from csp_trader.runtime.runner_lock import RunnerInstanceLock, build_ibkr_session_lock

host = (sys.argv[1] or "127.0.0.1").strip()
port_raw = (sys.argv[2] or "").strip()
client_id_raw = (sys.argv[3] or "").strip()

try:
    port = int(port_raw)
except ValueError:
    print("ERROR: ibkr.port missing/invalid; cannot perform runner lock guard", file=sys.stderr)
    sys.exit(2)
try:
    client_id = int(client_id_raw)
except ValueError:
    print("ERROR: ibkr.client_id missing/invalid; cannot perform runner lock guard", file=sys.stderr)
    sys.exit(2)

def fail_busy(probe, owner, *, label: str) -> None:
    owner_text = json.dumps(owner or {}, sort_keys=True)
    print(
        f"ERROR: {label} lock already active. "
        "Stop the existing process before launching E2E.",
        file=sys.stderr,
    )
    print(f"       lock_path={probe.lock_path}", file=sys.stderr)
    print(f"       owner={owner_text}", file=sys.stderr)
    sys.exit(1)

session_probe = build_ibkr_session_lock(host=host, port=port)
session_busy, session_owner = session_probe.probe_busy()
if session_busy:
    fail_busy(session_probe, session_owner, label="IBKR session")

runner_probe = RunnerInstanceLock(
    mode="trading",
    host=host,
    port=port,
    client_id=client_id,
)
runner_busy, runner_owner = runner_probe.probe_busy()
if runner_busy:
    fail_busy(runner_probe, runner_owner, label="Runner")

sys.exit(0)
PY
}

run_verify() {
  load_config
  print_summary

  local active_log_path=""
  if active_log_path="$(active_run_log_path_or_die 2>/dev/null)"; then
    :
  else
    active_log_path="${LOG_PATH:-}"
  fi

  echo ""
  echo "Verification commands:"
  if [ -n "$active_log_path" ]; then
    echo "  tail -n 200 \"$active_log_path\""
  else
    echo "  # No active run log found yet (run preflight or run first)"
  fi
  echo "  sqlite3 \"$DB_PATH\" \"select count(*) from orders;\""
  echo "  sqlite3 \"$DB_PATH\" \"select count(*) from positions;\""

  if [ -n "$active_log_path" ] && [ -f "$active_log_path" ]; then
    echo ""
    echo "Log tail ($active_log_path):"
    tail -n 50 "$active_log_path"
  else
    echo ""
    echo "Log file not found (from latest run pointer): ${active_log_path:-<unset>}"
  fi

  if command -v sqlite3 >/dev/null 2>&1; then
    if [ -f "$DB_PATH" ]; then
      echo ""
      echo "DB counts:"
      sqlite3 "$DB_PATH" "select count(*) as orders from orders;"
      sqlite3 "$DB_PATH" "select count(*) as positions from positions;"
    else
      echo ""
      echo "DB file not found: $DB_PATH"
    fi
  else
    echo ""
    echo "sqlite3 not found; install it to run DB checks."
  fi
}

run_observe() {
  load_config
  print_summary

  local active_log_path
  active_log_path="$(active_run_log_path_or_die)"

  [ -f "$active_log_path" ] || die "Active run log not found: $active_log_path"

  local observe_events="${E2E_OBSERVE_EVENTS:-}"
  local tail_lines="${E2E_OBSERVE_TAIL_LINES:-200}"
  local forward_file="${E2E_LOG_FORWARD_FILE:-}"
  local forward_cmd="${E2E_LOG_FORWARD_CMD:-}"

  echo ""
  echo "Observe mode: streaming structured events from active run log."
  echo "active_log_path: $active_log_path"
  if [ -n "$observe_events" ]; then
    echo "event_filter: $observe_events"
  else
    echo "event_filter: <none>"
  fi
  if [ -n "$forward_file" ]; then
    echo "forward_file: $forward_file"
  fi
  if [ -n "$forward_cmd" ]; then
    echo "forward_cmd: $forward_cmd"
  fi
  echo "Press Ctrl+C to stop."
  echo ""

  tail -n "$tail_lines" -F "$active_log_path" | "${PYTHON_CMD[@]}" - "$observe_events" "$forward_file" "$forward_cmd" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

events_csv, forward_file, forward_cmd = sys.argv[1:4]
allowed_events = {e.strip() for e in events_csv.split(",") if e.strip()}

sink = None
if forward_file:
    sink_path = Path(forward_file).expanduser()
    sink_path.parent.mkdir(parents=True, exist_ok=True)
    sink = sink_path.open("a", encoding="utf-8")

try:
    for raw_line in sys.stdin:
        line = raw_line.rstrip("\n")
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_name = str(payload.get("event") or "").strip()
        if allowed_events and event_name not in allowed_events:
            continue

        print(line, flush=True)

        if sink is not None:
            sink.write(f"{line}\n")
            sink.flush()

        if forward_cmd:
            subprocess.run(
                forward_cmd,
                input=f"{line}\n",
                text=True,
                shell=True,
                check=False,
            )
finally:
    if sink is not None:
        sink.close()
PY
}

run_entry_exit() {
  require_cmd uv
  load_config
  print_summary
  warn_if_after_hours

  local default_ticker="${DEFAULT_TICKER:-}"
  local default_target_price_override="$E2E_TEST_TARGET_PRICE_OVERRIDE_DEFAULT"
  local default_min_dte="$E2E_TEST_MIN_DTE_DEFAULT"
  local default_entry_floor="$E2E_TEST_ENTRY_FLOOR_DEFAULT"
  local default_exit_floor="$E2E_TEST_EXIT_FLOOR_DEFAULT"
  local default_spread_interval="$E2E_TEST_SPREAD_INTERVAL_DEFAULT"
  local default_spread_increment="$E2E_TEST_SPREAD_INCREMENT_DEFAULT"

  local TARGET_TICKER
  local TARGET_PRICE_OVERRIDE
  local ENTRY_FLOOR
  local MIN_DTE
  local EXIT_FLOOR
  local SPREAD_INTERVAL_SECONDS
  local SPREAD_INCREMENT
  local RUN_EXIT_REPLY

  echo ""
  echo "Run profile defaults (runtime overrides): target_override=${default_target_price_override}, entry_floor=${default_entry_floor}, min_dte=${default_min_dte}, exit_floor=${default_exit_floor}, spread_interval=${default_spread_interval}, spread_increment=${default_spread_increment}"
  TARGET_TICKER="$(prompt_value "Ticker to target for entry [${default_ticker}]: " "$default_ticker" "${E2E_TARGET_TICKER:-}")"
  TARGET_PRICE_OVERRIDE="$(prompt_value "Target price override for ${TARGET_TICKER} [${default_target_price_override}]: " "$default_target_price_override" "${E2E_TARGET_PRICE_OVERRIDE:-}")"
  ENTRY_FLOOR="$(prompt_value "Entry annualized_return_floor_pct [${default_entry_floor}]: " "$default_entry_floor" "${E2E_ENTRY_FLOOR:-}")"
  MIN_DTE="$(prompt_value "Minimum DTE [${default_min_dte}]: " "$default_min_dte" "${E2E_MIN_DTE:-}")"
  EXIT_FLOOR="$(prompt_value "Exit annualized_return_floor_pct [${default_exit_floor}]: " "$default_exit_floor" "${E2E_EXIT_FLOOR:-}")"
  SPREAD_INTERVAL_SECONDS="$(
    prompt_value \
      "Spread adjustment interval seconds [${default_spread_interval}]: " \
      "$default_spread_interval" \
      "${E2E_SPREAD_INTERVAL_SECONDS:-}"
  )"
  SPREAD_INCREMENT="$(
    prompt_value \
      "Spread adjustment increment [${default_spread_increment}]: " \
      "$default_spread_increment" \
      "${E2E_SPREAD_INCREMENT:-}"
  )"

  echo ""
  echo "Entry phase: start the trader and wait for an STO order to fill."
  echo "Press Ctrl+C after you see order_filled for any ticker (or after a few cycles if you need to abort)."
  assert_runner_lock_available
  local entry_start_ts
  entry_start_ts="$(timestamp_utc)"
  set +e
  run_trader_with_overrides \
    "$TARGET_TICKER" \
    "$TARGET_PRICE_OVERRIDE" \
    "$ENTRY_FLOOR" \
    "$MIN_DTE" \
    "$SPREAD_INTERVAL_SECONDS" \
    "$SPREAD_INCREMENT" \
    0
  local entry_status=$?
  set -e
  if [ "$entry_status" -ne 0 ]; then
    echo "Entry run exited with status $entry_status."
  fi
  local entry_log_path
  entry_log_path="$(active_run_log_path_or_die)"
  echo "Entry active log path: $entry_log_path"
  echo ""
  echo "Entry verification: require order_filled (any ticker) since $entry_start_ts."
  assert_order_filled_since "$entry_log_path" "$entry_start_ts" "" "Entry phase"

  RUN_EXIT_REPLY="$(prompt_value "Run exit/close phase now? [Y/n] " "Y" "${E2E_RUN_EXIT:-}")"
  if [[ "${RUN_EXIT_REPLY}" =~ ^([Yy]|[Yy][Ee][Ss]|1|true|TRUE)$ ]]; then
    echo ""
    echo "Exit phase: start the trader and wait for a BTC order to fill."
    echo "Press Ctrl+C after you see order_filled for any ticker."
    assert_runner_lock_available
    local exit_start_ts
    exit_start_ts="$(timestamp_utc)"
    set +e
    run_trader_with_overrides \
      "$TARGET_TICKER" \
      "$TARGET_PRICE_OVERRIDE" \
      "$EXIT_FLOOR" \
      "$MIN_DTE" \
      "$SPREAD_INTERVAL_SECONDS" \
      "$SPREAD_INCREMENT" \
      0
    local exit_status=$?
    set -e
    if [ "$exit_status" -ne 0 ]; then
      echo "Exit run exited with status $exit_status."
    fi
    local exit_log_path
    exit_log_path="$(active_run_log_path_or_die)"
    echo "Exit active log path: $exit_log_path"
    echo ""
    echo "Exit verification: require order_filled (any ticker) since $exit_start_ts."
    assert_order_filled_since "$exit_log_path" "$exit_start_ts" "" "Exit phase"
  fi
}

case "$COMMAND" in
  preflight)
    run_preflight
    ;;
  run)
    run_entry_exit
    ;;
  verify)
    run_verify
    ;;
  observe)
    run_observe
    ;;
  full)
    run_preflight
    run_entry_exit
    run_verify
    ;;
esac
