#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/e2e_002_watchlist_research.sh [preflight|run|verify|full|ci] [config.yaml] [section]
  scripts/e2e_002_watchlist_research.sh [us1|us2|us3|final] [config.yaml]

Commands:
  preflight   Dry-run smoke test with isolated temp config/runtime files
  run         Run interactive E2E sections (default section: all)
  verify      Print verification commands and run lightweight checks
  full        preflight -> run(all sections) -> verify
  ci          Non-interactive preflight + verify (no human-gated sections)

Sections (for run):
  all | us1 | us2 | us3 | final

Non-interactive mode:
  Set E2E_NON_INTERACTIVE=1 to disable prompts.
  Required human verification gates fail in non-interactive mode.
USAGE
}

die() {
  echo "Error: $*" >&2
  exit 1
}

info() {
  echo "[e2e-002] $*"
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
LOG_ROOT_DIR=""
RUN_LOG_FILE_NAME=""
LATEST_RUN_POINTER_FILE=""
DB_PATH=""
WATCHLIST_SYNC_PATH=""

TEMP_CONFIG_PATH=""
SESSION_LOG_PATH=""
SESSION_LOG_ROOT_DIR=""
SESSION_LOG_POINTER_PATH=""
SESSION_DB_PATH=""
TEMP_WATCHLIST_SYNC_PATH=""

PASS_COUNT=0
SKIP_COUNT=0

cleanup() {
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

# Default preflight/verify/ci to non-interactive unless explicitly overridden.
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
  # Preserve stdin for python "-" invocations so fallback execution
  # receives the same script content if uv invocation fails.
  if [ "$#" -gt 0 ] && [ "$1" = "-" ]; then
    local stdin_tmp
    stdin_tmp="$(mktemp "${TMPDIR:-/tmp}/e2e-002-stdin-XXXXXX")"
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

resolve_pointer_path() {
  local log_root_dir="$1"
  local pointer_file="$2"
  if [[ "$pointer_file" = /* ]]; then
    printf "%s" "$pointer_file"
  else
    printf "%s/%s" "$log_root_dir" "$pointer_file"
  fi
}

resolve_active_run_log_path() {
  local pointer_path="$1"
  run_py - "$pointer_path" <<'PY'
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

refresh_session_log_path() {
  [ -n "$SESSION_LOG_POINTER_PATH" ] || die "Session log pointer path is not set"
  local resolved
  resolved="$(resolve_active_run_log_path "$SESSION_LOG_POINTER_PATH")" \
    || die "Unable to resolve active run log from $SESSION_LOG_POINTER_PATH"
  SESSION_LOG_PATH="$resolved"
  info "Active run log: $SESSION_LOG_PATH"
}

require_env_var() {
  local var_name="$1"
  if [ -z "${!var_name:-}" ]; then
    die "Missing required env var: $var_name"
  fi
}

load_config_metadata() {
  [ -f "$CONFIG_PATH" ] || die "Config file not found: $CONFIG_PATH"

  CONFIG_DIR="$(cd "$(dirname "$CONFIG_PATH")" && pwd)"

  local output
  output="$(run_py - "$CONFIG_PATH" <<'PY'
import shlex
import sys

try:
    import yaml
except Exception:
    print("ERROR: PyYAML not available. Install dependencies before running E2E.", file=sys.stderr)
    sys.exit(1)

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}

storage = data.get("storage", {}) or {}

def find_watchlist_sync_path(cfg):
    target_price = cfg.get("target_price", {}) or {}
    target_price_sync = target_price.get("watchlist_sync", {}) or {}
    watchlist_sync = cfg.get("watchlist_sync", {}) or {}
    paths = cfg.get("paths", {}) or {}

    candidates = [
        target_price.get("watchlist_sync_path"),
        target_price_sync.get("path"),
        watchlist_sync.get("path"),
        paths.get("part1_watchlist_config"),
    ]

    flattened = []
    for c in candidates:
        if isinstance(c, tuple):
            flattened.extend(list(c))
        else:
            flattened.append(c)

    for c in flattened:
        if isinstance(c, str) and c.strip():
            return c.strip()
    return ""


def q(v):
    if v is None:
        v = ""
    return shlex.quote(str(v))

print(f"LOG_ROOT_DIR={q(storage.get('log_root_dir') or 'logs')}")
print(f"RUN_LOG_FILE_NAME={q(storage.get('run_log_file_name') or 'trading.jsonl')}")
print(f"LATEST_RUN_POINTER_FILE={q(storage.get('latest_run_pointer_file') or 'latest-run.json')}")
print(f"DB_PATH={q(storage.get('db_path') or 'trading_state.db')}")
print(f"WATCHLIST_SYNC_PATH={q(find_watchlist_sync_path(data))}")
PY
)"

  eval "$output"

  # Resolve configured paths relative to config directory.
  local resolved_db
  LOG_ROOT_DIR="$(resolve_path_from_config "${LOG_ROOT_DIR:-logs}")"
  resolved_db="$(resolve_path_from_config "$DB_PATH")"
  DB_PATH="$resolved_db"

  if [ -n "$WATCHLIST_SYNC_PATH" ]; then
    WATCHLIST_SYNC_PATH="$(resolve_path_from_config "$WATCHLIST_SYNC_PATH")"
  fi
}

create_temp_config() {
  local source_config="$1"
  local dest_config="$2"
  local db_path="$3"
  local watchlist_sync_path="$4"
  local log_root_dir="$5"
  local run_log_file_name="$6"
  local latest_run_pointer_file="$7"

  run_py - "$source_config" "$dest_config" "$db_path" "$watchlist_sync_path" "$log_root_dir" "$run_log_file_name" "$latest_run_pointer_file" <<'PY'
import os
import sys

try:
    import yaml
except Exception:
    print("PyYAML not available. Install dependencies before running E2E.", file=sys.stderr)
    sys.exit(1)

source, dest, db_path, watchlist_sync_path, log_root_dir, run_log_file_name, latest_run_pointer_file = sys.argv[1:8]

with open(source, "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}

storage = data.setdefault("storage", {})
storage["db_path"] = db_path
storage["log_root_dir"] = log_root_dir
storage["run_log_file_name"] = run_log_file_name or "trading.jsonl"
storage["latest_run_pointer_file"] = latest_run_pointer_file or "latest-run.json"
if "log_path" in storage:
    storage.pop("log_path", None)

# Patch common watchlist sync path keys so apply-curation cannot mutate a live file.
if watchlist_sync_path:
    if "target_price" in data and isinstance(data["target_price"], dict):
        tp = data["target_price"]
        if "watchlist_sync_path" in tp:
            tp["watchlist_sync_path"] = watchlist_sync_path
        if "watchlist_sync" in tp and isinstance(tp["watchlist_sync"], dict) and "path" in tp["watchlist_sync"]:
            tp["watchlist_sync"]["path"] = watchlist_sync_path

    if "watchlist_sync" in data and isinstance(data["watchlist_sync"], dict) and "path" in data["watchlist_sync"]:
        data["watchlist_sync"]["path"] = watchlist_sync_path

    if "paths" in data and isinstance(data["paths"], dict) and "part1_watchlist_config" in data["paths"]:
        data["paths"]["part1_watchlist_config"] = watchlist_sync_path

os.makedirs(os.path.dirname(dest), exist_ok=True)
with open(dest, "w", encoding="utf-8") as fh:
    yaml.safe_dump(data, fh, sort_keys=False)
PY
}

prepare_runtime() {
  load_config_metadata

  local temp_dir
  temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/e2e-002-XXXXXX")"
  TMP_DIRS+=("$temp_dir")

  SESSION_LOG_ROOT_DIR="$temp_dir/logs"
  SESSION_LOG_POINTER_PATH="$(resolve_pointer_path "$SESSION_LOG_ROOT_DIR" "latest-run.json")"
  SESSION_LOG_PATH=""
  SESSION_DB_PATH="$temp_dir/target_price_e2e.db"
  TEMP_CONFIG_PATH="$temp_dir/config.e2e.yaml"

  TEMP_WATCHLIST_SYNC_PATH=""
  if [ -n "$WATCHLIST_SYNC_PATH" ] && [ -f "$WATCHLIST_SYNC_PATH" ]; then
    TEMP_WATCHLIST_SYNC_PATH="$temp_dir/$(basename "$WATCHLIST_SYNC_PATH")"
    cp "$WATCHLIST_SYNC_PATH" "$TEMP_WATCHLIST_SYNC_PATH"
  fi

  create_temp_config \
    "$CONFIG_PATH" \
    "$TEMP_CONFIG_PATH" \
    "$SESSION_DB_PATH" \
    "$TEMP_WATCHLIST_SYNC_PATH" \
    "$SESSION_LOG_ROOT_DIR" \
    "${RUN_LOG_FILE_NAME:-trading.jsonl}" \
    "latest-run.json"

  info "Using temp config: $TEMP_CONFIG_PATH"
  info "Using temp log root: $SESSION_LOG_ROOT_DIR"
  info "Using latest pointer: $SESSION_LOG_POINTER_PATH"
  info "Using temp db:     $SESSION_DB_PATH"
  if [ -n "$TEMP_WATCHLIST_SYNC_PATH" ]; then
    info "Using temp watchlist sync path: $TEMP_WATCHLIST_SYNC_PATH"
  fi
}

run_target_price() {
  local cfg_path="$1"
  shift
  local passthrough=()
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --batch)
        # Legacy flag retained in the script for historical checkpoints;
        # current CLI runs a single batch per invocation.
        shift
        [ "$#" -gt 0 ] && shift
        ;;
      --apply-curation)
        # No dedicated apply-curation CLI flag exists in the current runtime.
        shift
        ;;
      *)
        passthrough+=("$1")
        shift
        ;;
    esac
  done

  if [ "${#passthrough[@]}" -gt 0 ]; then
    run_py -m csp_trader.main --config "$cfg_path" --mode target-price "${passthrough[@]}"
  else
    run_py -m csp_trader.main --config "$cfg_path" --mode target-price
  fi
}

assert_log_activity_since() {
  local log_path="$1"
  local since_ts="$2"
  local label="$3"

  run_py - "$log_path" "$since_ts" "$label" <<'PY'
import json
import os
import sys
from datetime import datetime

log_path, since_ts, label = sys.argv[1:4]

if not os.path.exists(log_path):
    print(f"{label} failed: log file not found: {log_path}", file=sys.stderr)
    sys.exit(1)


def parse_ts(value):
    if not value:
        return None
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None

since = parse_ts(since_ts)
if since is None:
    print(f"{label} failed: invalid timestamp: {since_ts}", file=sys.stderr)
    sys.exit(1)

found = False
with open(log_path, "r", encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = parse_ts(entry.get("ts") or entry.get("timestamp") or entry.get("time"))
        if ts and ts >= since:
            found = True
            break

if not found:
    print(f"{label} failed: no timestamped log activity after {since_ts}", file=sys.stderr)
    sys.exit(1)

print(f"{label} ok: timestamp-gated log activity found")
PY
}

assert_recent_rows() {
  local db_path="$1"
  local since_ts="$2"
  local label="$3"
  local tables_csv="$4"
  local columns_csv="$5"

  run_py - "$db_path" "$since_ts" "$label" "$tables_csv" "$columns_csv" <<'PY'
import sqlite3
import sys

(db_path, since_ts, label, tables_csv, columns_csv) = sys.argv[1:6]

tables = [t.strip() for t in tables_csv.split(",") if t.strip()]
columns = [c.strip() for c in columns_csv.split(",") if c.strip()]

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

existing = {row["name"] for row in conn.execute("select name from sqlite_master where type='table'")}
matched = []
for table in tables:
    if table not in existing:
        continue
    table_columns = [row["name"] for row in conn.execute(f"pragma table_info({table})")]
    chosen_column = next((c for c in columns if c in table_columns), None)
    if not chosen_column:
        continue
    count = conn.execute(
        f"select count(*) as c from {table} where {chosen_column} >= ?",
        (since_ts,),
    ).fetchone()["c"]
    matched.append((table, chosen_column, int(count)))
    if count > 0:
        print(f"{label} ok: {count} recent rows in {table}.{chosen_column}")
        sys.exit(0)

if not matched:
    print(f"{label} failed: no matching table/column pair found", file=sys.stderr)
    sys.exit(1)

details = ", ".join([f"{t}.{c}={n}" for (t, c, n) in matched])
print(f"{label} failed: no rows >= {since_ts} ({details})", file=sys.stderr)
sys.exit(1)
PY
}

assert_recent_ranking_entries() {
  local db_path="$1"
  local since_ts="$2"
  local label="$3"

  run_py - "$db_path" "$since_ts" "$label" <<'PY'
import sqlite3
import sys

db_path, since_ts, label = sys.argv[1:4]

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

existing = {row["name"] for row in conn.execute("select name from sqlite_master where type='table'")}
required = {"ranking_entries", "batch_runs"}
missing = sorted(required - existing)
if missing:
    print(f"{label} failed: missing tables: {', '.join(missing)}", file=sys.stderr)
    sys.exit(1)

count = conn.execute(
    """
    SELECT COUNT(*) AS c
    FROM ranking_entries r
    JOIN batch_runs b ON b.batch_id = r.batch_id
    WHERE COALESCE(b.started_at, b.scheduled_for) >= ?
    """,
    (since_ts,),
).fetchone()["c"]

if int(count) <= 0:
    print(f"{label} failed: no ranking rows linked to batches >= {since_ts}", file=sys.stderr)
    sys.exit(1)

print(f"{label} ok: {int(count)} ranking rows linked to recent batches")
PY
}

assert_recent_sheet_rows() {
  local spreadsheet_id="$1"
  local worksheet_name="$2"
  local since_ts="$3"
  local label="$4"

  run_py - "$spreadsheet_id" "$worksheet_name" "$since_ts" "$label" <<'PY'
import os
import sys
from datetime import datetime

spreadsheet_id, worksheet_name, since_ts, label = sys.argv[1:5]

credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
if not credentials_path:
    print(f"{label} failed: GOOGLE_APPLICATION_CREDENTIALS is not set", file=sys.stderr)
    sys.exit(1)
if not os.path.isfile(credentials_path):
    print(f"{label} failed: credentials file not found/readable", file=sys.stderr)
    sys.exit(1)

scopes_raw = os.environ.get("GOOGLE_SHEETS_SCOPES", "").strip()
scopes = (
    [scope.strip() for scope in scopes_raw.split(",") if scope.strip()]
    if scopes_raw
    else ["https://www.googleapis.com/auth/spreadsheets"]
)


def parse_ts(value):
    if not value:
        return None
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


since = parse_ts(since_ts)
if since is None:
    print(f"{label} failed: invalid timestamp: {since_ts}", file=sys.stderr)
    sys.exit(1)

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception as exc:
    print(f"{label} failed: missing Sheets dependencies ({type(exc).__name__})", file=sys.stderr)
    sys.exit(1)

try:
    credentials = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    client = gspread.authorize(credentials)
    worksheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    rows = worksheet.get_all_records()
except Exception as exc:
    print(
        f"{label} failed: unable to access worksheet '{worksheet_name}' ({type(exc).__name__})",
        file=sys.stderr,
    )
    sys.exit(1)

recent_count = 0
for row in rows:
    ts = parse_ts(row.get("created_at"))
    if ts and ts >= since:
        recent_count += 1

if recent_count == 0:
    print(
        f"{label} failed: no worksheet rows with created_at >= {since_ts}",
        file=sys.stderr,
    )
    sys.exit(1)

print(f"{label} ok: {recent_count} worksheet rows with created_at >= {since_ts}")
PY
}

confirm_section_gate() {
  local section_name="$1"
  shift

  echo ""
  echo "Before running ${section_name}, please confirm:"
  local item
  for item in "$@"; do
    echo "- [ ] $item"
  done

  local answer="yes"
  if is_interactive_mode; then
    read -r -p "Proceed? (yes/skip/stop) [yes]: " answer || true
    answer="${answer:-yes}"
  else
    echo "Non-interactive mode: proceeding with ${section_name}" >&2
  fi

  answer="$(printf "%s" "$answer" | tr '[:upper:]' '[:lower:]')"
  case "$answer" in
    y|yes|proceed|continue)
      return 0
      ;;
    s|skip)
      return 10
      ;;
    stop|n|no)
      return 20
      ;;
    *)
      echo "Unrecognized response '$answer' -> treating as stop" >&2
      return 20
      ;;
  esac
}

human_verify() {
  local prompt="$1"
  local answer="yes"
  if is_interactive_mode; then
    read -r -p "$prompt (yes/no) [yes]: " answer || true
    answer="${answer:-yes}"
  else
    echo "Manual verification required but non-interactive mode is enabled: $prompt" >&2
    return 2
  fi

  answer="$(printf "%s" "$answer" | tr '[:upper:]' '[:lower:]')"
  case "$answer" in
    y|yes)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

run_preflight() {
  echo ""
  info "Section 1: Preflight (dry-run smoke test)"
  local started_at
  started_at="$(timestamp_utc)"

  set +e
  run_target_price "$TEMP_CONFIG_PATH" --dry-run
  local status=$?
  set -e
  [ "$status" -eq 0 ] || die "Preflight dry-run failed with status $status"

  refresh_session_log_path
  assert_log_activity_since "$SESSION_LOG_PATH" "$started_at" "Preflight log check"

  assert_recent_rows \
    "$SESSION_DB_PATH" \
    "$started_at" \
    "Preflight DB check" \
    "batch_runs,valuation_versions,target_price_records,ranking_entries" \
    "started_at,created_at,computed_at,updated_at"

  PASS_COUNT=$((PASS_COUNT + 1))
  info "Preflight PASS"
}

check_us1_dependencies() {
  require_env_var GOOGLE_APPLICATION_CREDENTIALS
  require_env_var GOOGLE_SHEETS_SPREADSHEET_ID
  [ -r "$GOOGLE_APPLICATION_CREDENTIALS" ] || die "GOOGLE_APPLICATION_CREDENTIALS file is not readable"
}

run_us1() {
  info "Section 2: US1 - NPV Valuations"

  check_us1_dependencies
  confirm_section_gate \
    "US1" \
    "GOOGLE_APPLICATION_CREDENTIALS is readable" \
    "GOOGLE_SHEETS_SPREADSHEET_ID is set and sheet is accessible" \
    "IBKR fundamentals access is available (Gateway/TWS running)" \
    "valuations worksheet exists with contract columns"
  local gate_status=$?
  if [ "$gate_status" -eq 10 ]; then
    info "US1 skipped by user"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    return 0
  fi
  [ "$gate_status" -eq 0 ] || die "US1 stopped by user"

  local started_at
  started_at="$(timestamp_utc)"

  set +e
  run_target_price "$TEMP_CONFIG_PATH" --batch daily
  local status=$?
  set -e
  [ "$status" -eq 0 ] || die "US1 batch run failed with status $status"

  refresh_session_log_path
  assert_log_activity_since "$SESSION_LOG_PATH" "$started_at" "US1 log check"
  assert_recent_rows \
    "$SESSION_DB_PATH" \
    "$started_at" \
    "US1 valuation version check" \
    "valuation_versions,valuation_version,valuations" \
    "created_at,updated_at,computed_at"
  assert_recent_rows \
    "$SESSION_DB_PATH" \
    "$started_at" \
    "US1 valuation scenario check" \
    "valuation_scenarios,valuation_rows,valuations" \
    "created_at,updated_at,computed_at"
  assert_recent_sheet_rows \
    "$GOOGLE_SHEETS_SPREADSHEET_ID" \
    "valuations" \
    "$started_at" \
    "US1 worksheet write check"

  PASS_COUNT=$((PASS_COUNT + 1))
  info "US1 PASS"
}

check_us2_dependencies() {
  require_env_var GOOGLE_APPLICATION_CREDENTIALS
  require_env_var GOOGLE_SHEETS_SPREADSHEET_ID
  [ -r "$GOOGLE_APPLICATION_CREDENTIALS" ] || die "GOOGLE_APPLICATION_CREDENTIALS file is not readable"
}

run_us2() {
  info "Section 3: US2 - Risk-Adjusted Target Prices"

  check_us2_dependencies
  confirm_section_gate \
    "US2" \
    "US1 has passed at least once" \
    "margin_of_safety policy keys exist in config" \
    "targets worksheet exists with contract columns"
  local gate_status=$?
  if [ "$gate_status" -eq 10 ]; then
    info "US2 skipped by user"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    return 0
  fi
  [ "$gate_status" -eq 0 ] || die "US2 stopped by user"

  local started_at
  started_at="$(timestamp_utc)"

  set +e
  run_target_price "$TEMP_CONFIG_PATH" --batch daily
  local status=$?
  set -e
  [ "$status" -eq 0 ] || die "US2 batch run failed with status $status"

  refresh_session_log_path
  assert_log_activity_since "$SESSION_LOG_PATH" "$started_at" "US2 log check"
  assert_recent_rows \
    "$SESSION_DB_PATH" \
    "$started_at" \
    "US2 target record check" \
    "target_price_records,target_prices,targets" \
    "computed_at,created_at,updated_at"

  human_verify "Human verify: targets sheet reflects base fair value + risk margin + manual adjustment behavior" \
    || die "US2 failed human verification"

  PASS_COUNT=$((PASS_COUNT + 1))
  info "US2 PASS"
}

check_us3_dependencies() {
  require_env_var GOOGLE_APPLICATION_CREDENTIALS
  require_env_var GOOGLE_SHEETS_SPREADSHEET_ID
  [ -r "$GOOGLE_APPLICATION_CREDENTIALS" ] || die "GOOGLE_APPLICATION_CREDENTIALS file is not readable"

  if [ -n "$TEMP_WATCHLIST_SYNC_PATH" ]; then
    [ -w "$TEMP_WATCHLIST_SYNC_PATH" ] || die "Temp watchlist sync path is not writable: $TEMP_WATCHLIST_SYNC_PATH"
  fi
}

run_us3() {
  info "Section 4: US3 - Ranking + Part 1 Curation"

  check_us3_dependencies
  confirm_section_gate \
    "US3" \
    "curation_actions includes at least one approved action for apply testing" \
    "watchlist sync destination is writable" \
    "ranking and curation_actions worksheets match contract schemas"
  local gate_status=$?
  if [ "$gate_status" -eq 10 ]; then
    info "US3 skipped by user"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    return 0
  fi
  [ "$gate_status" -eq 0 ] || die "US3 stopped by user"

  local started_at
  started_at="$(timestamp_utc)"

  set +e
  run_target_price "$TEMP_CONFIG_PATH" --batch daily
  local batch_status=$?
  run_target_price "$TEMP_CONFIG_PATH" --apply-curation
  local apply_status=$?
  set -e

  [ "$batch_status" -eq 0 ] || die "US3 ranking batch failed with status $batch_status"
  [ "$apply_status" -eq 0 ] || die "US3 apply-curation failed with status $apply_status"

  refresh_session_log_path
  assert_log_activity_since "$SESSION_LOG_PATH" "$started_at" "US3 log check"
  assert_recent_ranking_entries "$SESSION_DB_PATH" "$started_at" "US3 ranking check"
  assert_recent_rows \
    "$SESSION_DB_PATH" \
    "$started_at" \
    "US3 curation check" \
    "curation_actions,curation_action" \
    "requested_at,approved_at,updated_at,created_at"

  human_verify "Human verify: approved push/pull actions applied correctly and backup/rollback expectations are satisfied" \
    || die "US3 failed human verification"

  PASS_COUNT=$((PASS_COUNT + 1))
  info "US3 PASS"
}

run_final_section() {
  info "Section Final: Full feature cross-story validation"

  confirm_section_gate \
    "Final" \
    "Sections 1-4 have each passed at least once" \
    "Google Sheets and IBKR fundamentals are reachable" \
    "curation approvals are staged"
  local gate_status=$?
  if [ "$gate_status" -eq 10 ]; then
    info "Final section skipped by user"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    return 0
  fi
  [ "$gate_status" -eq 0 ] || die "Final section stopped by user"

  local started_at
  started_at="$(timestamp_utc)"

  set +e
  run_target_price "$TEMP_CONFIG_PATH" --batch daily
  local batch_status=$?
  run_target_price "$TEMP_CONFIG_PATH" --apply-curation
  local apply_status=$?
  set -e

  [ "$batch_status" -eq 0 ] || die "Final section batch failed with status $batch_status"
  [ "$apply_status" -eq 0 ] || die "Final section apply-curation failed with status $apply_status"

  refresh_session_log_path
  assert_log_activity_since "$SESSION_LOG_PATH" "$started_at" "Final log check"
  assert_recent_rows \
    "$SESSION_DB_PATH" \
    "$started_at" \
    "Final valuation evidence" \
    "valuation_versions,valuation_scenarios,valuations" \
    "created_at,updated_at,computed_at"
  assert_recent_rows \
    "$SESSION_DB_PATH" \
    "$started_at" \
    "Final target evidence" \
    "target_price_records,target_prices,targets" \
    "computed_at,created_at,updated_at"
  assert_recent_ranking_entries "$SESSION_DB_PATH" "$started_at" "Final ranking evidence"

  human_verify "Human verify: valuations, targets, ranking, and curation actions are consistent end-to-end in Google Sheets and watchlist sync output" \
    || die "Final section failed human verification"

  PASS_COUNT=$((PASS_COUNT + 1))
  info "Final section PASS"
}

run_section_selection() {
  local section_lower
  section_lower="$(printf "%s" "$SECTION" | tr '[:upper:]' '[:lower:]')"
  case "$section_lower" in
    all)
      run_us1
      run_us2
      run_us3
      run_final_section
      ;;
    us1)
      run_us1
      ;;
    us2)
      run_us2
      ;;
    us3)
      run_us3
      ;;
    final)
      run_final_section
      ;;
    *)
      die "Unknown section '$SECTION'. Expected: all|us1|us2|us3|final"
      ;;
  esac
}

print_verify_commands() {
  echo ""
  echo "Verification commands:"
  echo "  scripts/e2e_002_watchlist_research.sh preflight $CONFIG_PATH"
  echo "  scripts/e2e_002_watchlist_research.sh run $CONFIG_PATH us1"
  echo "  scripts/e2e_002_watchlist_research.sh run $CONFIG_PATH us2"
  echo "  scripts/e2e_002_watchlist_research.sh run $CONFIG_PATH us3"
  echo "  scripts/e2e_002_watchlist_research.sh run $CONFIG_PATH final"
  echo ""
  echo "Current runtime artifact paths (temp):"
  echo "  config: $TEMP_CONFIG_PATH"
  echo "  latest pointer: $SESSION_LOG_POINTER_PATH"
  echo "  log:    $SESSION_LOG_PATH"
  echo "  db:     $SESSION_DB_PATH"
}

run_lightweight_verify() {
  print_verify_commands

  if [ -z "$SESSION_LOG_PATH" ] && [ -n "$SESSION_LOG_POINTER_PATH" ] && [ -f "$SESSION_LOG_POINTER_PATH" ]; then
    refresh_session_log_path
  fi

  if [ -f "$SESSION_LOG_PATH" ]; then
    echo ""
    echo "Recent log tail:"
    tail -n 40 "$SESSION_LOG_PATH" || true
  else
    echo ""
    echo "No log file present yet: $SESSION_LOG_PATH"
  fi

  if [ -f "$SESSION_DB_PATH" ]; then
    echo ""
    run_py - "$SESSION_DB_PATH" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
conn = sqlite3.connect(path)
conn.row_factory = sqlite3.Row

tables = [r["name"] for r in conn.execute("select name from sqlite_master where type='table' order by name")]
print("DB tables:")
for t in tables:
    print(f"  - {t}")

candidates = [
    "batch_runs",
    "valuation_versions",
    "valuation_scenarios",
    "target_price_records",
    "ranking_entries",
    "curation_actions",
]
print("\nCandidate row counts:")
for table in candidates:
    if table in tables:
        count = conn.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"  - {table}: {count}")
PY
  else
    echo ""
    echo "No DB file present yet: $SESSION_DB_PATH"
  fi

  PASS_COUNT=$((PASS_COUNT + 1))
  info "Verify PASS"
}

prepare_runtime

case "$COMMAND" in
  preflight)
    run_preflight
    ;;
  run)
    run_section_selection
    ;;
  verify)
    run_lightweight_verify
    ;;
  ci)
    run_preflight
    run_lightweight_verify
    ;;
  full)
    run_preflight
    run_section_selection
    run_lightweight_verify
    ;;
  *)
    die "Unhandled command: $COMMAND"
    ;;
esac

echo ""
info "Completed with ${PASS_COUNT} passed section(s), ${SKIP_COUNT} skipped section(s)."
