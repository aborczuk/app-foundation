#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  scripts/e2e_018_clickup_sync.sh [preflight|run|verify|full|ci] [env-file] [section]
  scripts/e2e_018_clickup_sync.sh [us1|us2|final] [env-file]

Commands:
  preflight  Dry-run checks: local setup + read-only ClickUp dependency checks
  run        Run interactive E2E sections (default section: all)
  verify     Print verification commands and run lightweight assertions
  full       preflight -> run(all) -> verify
  ci         Non-interactive preflight + verify only (no human-gated sections)

Sections (for run):
  all | us1 | us2 | final

Notes:
  - [env-file] is optional. If provided, it is copied to a temp file and sourced.
  - Required human gates fail in non-interactive mode with ERROR [blocked_manual].
USAGE
}

die() {
  echo "Error: $*" >&2
  exit 1
}

info() {
  echo "[e2e-018-clickup-sync] $*"
}

pass() {
  echo "[PASS] $*"
  PASS_COUNT=$((PASS_COUNT + 1))
}

skip() {
  echo "[SKIP] $*"
  SKIP_COUNT=$((SKIP_COUNT + 1))
}

blocked_manual() {
  echo "ERROR [blocked_manual]: $*" >&2
  exit 32
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    die "Required command not found: $cmd"
  fi
}

COMMAND="${1:-full}"
CONFIG_PATH=""
SECTION="all"
ORIGINAL_E2E_NON_INTERACTIVE="${E2E_NON_INTERACTIVE-__unset__}"
E2E_NON_INTERACTIVE="${E2E_NON_INTERACTIVE:-0}"

PYTHON_CMD=(python3)
USE_UV=0
TMP_FILES=()
TMP_DIRS=()

REPO_ROOT=""
FEATURE_DIR=""
SPECKIT_ROOT_VALUE=""
MANIFEST_PATH=""
TEMP_ENV_FILE=""

LAST_LOG_FILE=""
LAST_RUN_STARTED_AT=""

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
    CONFIG_PATH="${2:-}"
    ;;
  run)
    CONFIG_PATH="${2:-}"
    SECTION="${3:-all}"
    ;;
  us1|us2|final)
    SECTION="$COMMAND"
    COMMAND="run"
    CONFIG_PATH="${2:-}"
    ;;
  *.env)
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
require_cmd git
if command -v uv >/dev/null 2>&1; then
  USE_UV=1
  PYTHON_CMD=(uv run python)
fi

run_py() {
  if [ "$#" -gt 0 ] && [ "$1" = "-" ]; then
    local stdin_tmp
    stdin_tmp="$(mktemp "${TMPDIR:-/tmp}/e2e-018-stdin-XXXXXX")"
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

prepare_context() {
  REPO_ROOT="$(pwd)"
  FEATURE_DIR="$REPO_ROOT/specs/018-speckit-clickup-sync"
  SPECKIT_ROOT_VALUE="${SPECKIT_ROOT:-$REPO_ROOT}"
  MANIFEST_PATH="$SPECKIT_ROOT_VALUE/.speckit/clickup-manifest.json"

  [ -d "$FEATURE_DIR" ] || die "Feature directory missing: $FEATURE_DIR"
  [ -f "$FEATURE_DIR/spec.md" ] || die "Missing spec file: $FEATURE_DIR/spec.md"
  [ -f "$FEATURE_DIR/tasks.md" ] || die "Missing tasks file: $FEATURE_DIR/tasks.md"
}

load_env_file_if_present() {
  if [ -z "${CONFIG_PATH:-}" ]; then
    info "No env file provided; using current process environment."
    return 0
  fi

  [ -f "$CONFIG_PATH" ] || die "Env file not found: $CONFIG_PATH"

  TEMP_ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/e2e-018-env-XXXXXX")"
  TMP_FILES+=("$TEMP_ENV_FILE")
  cp "$CONFIG_PATH" "$TEMP_ENV_FILE"

  set -a
  # shellcheck disable=SC1090
  source "$TEMP_ENV_FILE"
  set +a
  info "Loaded env vars from temp copy of: $CONFIG_PATH"
}

assert_required_env() {
  local missing=()
  local key
  for key in CLICKUP_API_TOKEN CLICKUP_SPACE_ID; do
    if [ -z "${!key:-}" ]; then
      missing+=("$key")
    fi
  done

  if [ "${#missing[@]}" -gt 0 ]; then
    die "Missing required env var(s): ${missing[*]}"
  fi

  pass "Required ClickUp env vars are set."
}

assert_mcp_clickup_importable() {
  run_py - <<'PY'
import importlib
import sys

try:
    importlib.import_module("mcp_clickup")
except Exception as exc:
    print(f"FAIL: unable to import mcp_clickup ({type(exc).__name__}: {exc})", file=sys.stderr)
    raise SystemExit(1)

print("[PASS] mcp_clickup module import is valid.")
PY
  PASS_COUNT=$((PASS_COUNT + 1))
}

assert_clickup_space_reachable() {
  run_py - <<'PY'
import os
import sys

try:
    import httpx
except Exception as exc:
    print(f"FAIL: httpx import failed ({type(exc).__name__})", file=sys.stderr)
    raise SystemExit(1)

token = os.environ.get("CLICKUP_API_TOKEN", "").strip()
space_id = os.environ.get("CLICKUP_SPACE_ID", "").strip()
if not token or not space_id:
    print("FAIL: CLICKUP_API_TOKEN/CLICKUP_SPACE_ID must be set", file=sys.stderr)
    raise SystemExit(1)

url = f"https://api.clickup.com/api/v2/space/{space_id}"
headers = {"Authorization": token}

try:
    with httpx.Client(timeout=20.0) as client:
        response = client.get(url, headers=headers)
except Exception as exc:
    print(f"FAIL: ClickUp reachability check failed ({type(exc).__name__})", file=sys.stderr)
    raise SystemExit(1)

if response.status_code == 200:
    print("[PASS] ClickUp Space reachability check succeeded (adopted dependency verified).")
    raise SystemExit(0)
if response.status_code == 401:
    print("FAIL: ClickUp auth failed (401). Check CLICKUP_API_TOKEN.", file=sys.stderr)
    raise SystemExit(1)
if response.status_code == 404:
    print("FAIL: ClickUp Space not found (404). Check CLICKUP_SPACE_ID.", file=sys.stderr)
    raise SystemExit(1)

print(f"FAIL: ClickUp reachability returned HTTP {response.status_code}.", file=sys.stderr)
raise SystemExit(1)
PY
  PASS_COUNT=$((PASS_COUNT + 1))
}

manifest_signature() {
  run_py - "$MANIFEST_PATH" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("missing")
    raise SystemExit(0)

raw = path.read_bytes()
try:
    json.loads(raw.decode("utf-8"))
except Exception:
    print("invalid-json")
    raise SystemExit(0)

digest = hashlib.sha256(raw).hexdigest()
stat = path.stat()
print(f"{digest}:{len(raw)}:{stat.st_mtime_ns}")
PY
}

manifest_counts() {
  run_py - "$MANIFEST_PATH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("missing")
    raise SystemExit(0)

data = json.loads(path.read_text(encoding="utf-8"))
folders = len(data.get("folders", {}) or {})
lists = len(data.get("lists", {}) or {})
tasks = len(data.get("tasks", {}) or {})
subtasks = len(data.get("subtasks", {}) or {})
print(f"{folders},{lists},{tasks},{subtasks}")
PY
}

assert_manifest_integrity() {
  run_py - "$MANIFEST_PATH" "${CLICKUP_SPACE_ID:-}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_space = sys.argv[2]

if not path.exists():
    print(f"FAIL: manifest not found: {path}", file=sys.stderr)
    raise SystemExit(1)

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"FAIL: manifest is not valid JSON ({type(exc).__name__})", file=sys.stderr)
    raise SystemExit(1)

required = ["version", "workspace_id", "space_id", "folders", "lists", "tasks", "subtasks"]
missing = [k for k in required if k not in data]
if missing:
    print(f"FAIL: manifest missing required key(s): {missing}", file=sys.stderr)
    raise SystemExit(1)

if str(data.get("version")) != "1":
    print(f"FAIL: manifest version expected '1', got {data.get('version')!r}", file=sys.stderr)
    raise SystemExit(1)

if expected_space and str(data.get("space_id", "")).strip() != expected_space:
    print(
        f"FAIL: manifest space_id mismatch. expected={expected_space!r} actual={data.get('space_id')!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)

for section in ("folders", "lists", "tasks", "subtasks"):
    mapping = data.get(section)
    if not isinstance(mapping, dict):
        print(f"FAIL: manifest section {section!r} is not a mapping", file=sys.stderr)
        raise SystemExit(1)
    for key, value in mapping.items():
        if not str(key).strip():
            print(f"FAIL: manifest section {section!r} contains blank key", file=sys.stderr)
            raise SystemExit(1)
        if not str(value).strip():
            print(f"FAIL: manifest section {section!r} contains blank ID for key {key!r}", file=sys.stderr)
            raise SystemExit(1)

print(
    "[PASS] Manifest integrity valid: "
    f"folders={len(data['folders'])} lists={len(data['lists'])} "
    f"tasks={len(data['tasks'])} subtasks={len(data['subtasks'])}"
)
PY
  PASS_COUNT=$((PASS_COUNT + 1))
}

extract_sync_summary_counts() {
  local log_path="$1"
  run_py - "$log_path" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
match = re.search(r"Summary:\s*(\d+)\s+created,\s*(\d+)\s+updated,\s*(\d+)\s+skipped", text)
if not match:
    print("missing")
    raise SystemExit(0)
print(f"{match.group(1)},{match.group(2)},{match.group(3)}")
PY
}

assert_manifest_timestamp_if_mutation_reported() {
  local log_path="$1"
  local section_started_at="$2"
  local summary
  summary="$(extract_sync_summary_counts "$log_path")"
  if [ "$summary" = "missing" ]; then
    skip "Sync summary line not found; timestamp-gated manifest mutation check skipped."
    return 0
  fi

  local created updated skipped_count
  IFS=',' read -r created updated skipped_count <<<"$summary"
  if [ $((created + updated)) -le 0 ]; then
    skip "No created/updated items reported; timestamp-gated mutation check not required."
    return 0
  fi

  run_py - "$MANIFEST_PATH" "$section_started_at" <<'PY'
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
started = sys.argv[2]

if not path.exists():
    print("FAIL: manifest missing after mutation run", file=sys.stderr)
    raise SystemExit(1)

started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
mtime_dt = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
if mtime_dt < started_dt:
    print(
        "FAIL: manifest mtime predates section start despite created/updated summary",
        file=sys.stderr,
    )
    raise SystemExit(1)

print(f"[PASS] Timestamp-gated manifest persistence check passed (mtime={mtime_dt.isoformat()}).")
PY
  PASS_COUNT=$((PASS_COUNT + 1))
}

assert_manifest_unchanged() {
  local before_sig="$1"
  local after_sig="$2"
  if [ "$before_sig" != "$after_sig" ]; then
    die "Manifest changed during read-only step. before=$before_sig after=$after_sig"
  fi
  pass "Manifest signature unchanged during read-only status mode."
}

file_contains_any_pattern() {
  local file_path="$1"
  shift

  if command -v rg >/dev/null 2>&1; then
    local rg_args=()
    local pattern
    for pattern in "$@"; do
      rg_args+=("-e" "$pattern")
    done
    rg -n "${rg_args[@]}" "$file_path" >/dev/null 2>&1
    return $?
  fi

  local grep_pattern
  for grep_pattern in "$@"; do
    if grep -E "$grep_pattern" "$file_path" >/dev/null 2>&1; then
      return 0
    fi
  done
  return 1
}

assert_no_lifecycle_errors() {
  local log_path="$1"
  if file_contains_any_pattern "$log_path" \
    "event loop is already running" \
    "Task was destroyed but it is pending" \
    "Cannot run the event loop while another loop is running" \
    "coroutine .* was never awaited"; then
    die "Lifecycle error signature found in command output: $log_path"
  fi
  pass "No async lifecycle regression signals in output."
}

assert_status_output_shape() {
  local log_path="$1"
  run_py - "$log_path" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
required_tokens = ["Done", "In Progress", "Blocked", "Not Started"]
missing = [t for t in required_tokens if t not in text]
if missing:
    print(f"FAIL: status output missing expected bucket(s): {missing}", file=sys.stderr)
    raise SystemExit(1)

groups = re.findall(r"^\s*\d{3}[-\w]*", text, flags=re.MULTILINE)
if not groups and "ClickUp Subtask Status" not in text:
    print("FAIL: status output missing expected heading/group structure", file=sys.stderr)
    raise SystemExit(1)

print("[PASS] Status output includes grouped state buckets.")
PY
  PASS_COUNT=$((PASS_COUNT + 1))
}

assert_no_unresolved_drift() {
  local log_path="$1"
  if file_contains_any_pattern "$log_path" \
    "Drift detected" \
    "schema_drift" \
    "manifest but not found in ClickUp"; then
    die "Unresolved live-vs-local drift detected in output: $log_path"
  fi
  pass "No unresolved live-vs-local drift markers detected."
}

assert_no_orphan_processes() {
  local orphans
  orphans="$(pgrep -f "mcp_clickup" 2>/dev/null || true)"
  if [ -n "$orphans" ]; then
    die "Orphan mcp_clickup process(es) detected: $orphans"
  fi
  pass "No orphan mcp_clickup processes remain."
}

run_clickup() {
  local label="$1"
  shift

  local log_file
  log_file="$(mktemp "${TMPDIR:-/tmp}/e2e-018-run-XXXXXX.log")"
  TMP_FILES+=("$log_file")

  LAST_RUN_STARTED_AT="$(timestamp_utc)"
  info "Running [$label]: ${PYTHON_CMD[*]} -m mcp_clickup $*"

  set +e
  "${PYTHON_CMD[@]}" -m mcp_clickup "$@" 2>&1 | tee "$log_file"
  local status=${PIPESTATUS[0]}
  set -e

  LAST_LOG_FILE="$log_file"
  if [ "$status" -ne 0 ]; then
    die "Command failed (exit $status): ${PYTHON_CMD[*]} -m mcp_clickup $*"
  fi

  pass "$label command exited with code 0."
  assert_no_lifecycle_errors "$log_file"
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
    blocked_manual "Manual section gate required for ${section_name}; rerun interactively."
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

require_human_verify() {
  local prompt="$1"
  local answer="yes"
  if is_interactive_mode; then
    read -r -p "$prompt (yes/no) [yes]: " answer || true
    answer="${answer:-yes}"
  else
    blocked_manual "$prompt"
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

print_summary() {
  info "Command: $COMMAND"
  info "Section: $SECTION"
  info "Env file: ${CONFIG_PATH:-<none>}"
  info "SPECKIT_ROOT: $SPECKIT_ROOT_VALUE"
  info "Manifest path: $MANIFEST_PATH"
}

run_preflight() {
  echo ""
  info "Section 1: Preflight (dry-run)"

  prepare_context
  load_env_file_if_present
  assert_required_env
  assert_mcp_clickup_importable
  assert_clickup_space_reachable

  if [ -f "$MANIFEST_PATH" ]; then
    assert_manifest_integrity
  else
    skip "Manifest missing (expected on first bootstrap): $MANIFEST_PATH"
  fi
}

run_us1() {
  echo ""
  info "Section 2: US1 - Bootstrap hierarchy idempotently"

  local gate_status
  if confirm_section_gate \
    "US1" \
    "Custom fields workflow_type/context_ref/execution_policy exist in ClickUp Space" \
    "You are okay with writing/updating .speckit/clickup-manifest.json"; then
    gate_status=0
  else
    gate_status=$?
  fi
  if [ "$gate_status" -eq 10 ]; then
    info "US1 skipped by user"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    return 0
  fi
  [ "$gate_status" -eq 0 ] || die "US1 stopped by user"

  local counts_after_first counts_after_second
  run_clickup "US1 bootstrap pass 1"
  assert_manifest_integrity
  assert_manifest_timestamp_if_mutation_reported "$LAST_LOG_FILE" "$LAST_RUN_STARTED_AT"
  counts_after_first="$(manifest_counts)"

  run_clickup "US1 bootstrap pass 2"
  assert_manifest_integrity
  counts_after_second="$(manifest_counts)"
  if [ "$counts_after_first" != "$counts_after_second" ]; then
    die "Idempotency check failed: manifest counts changed across unchanged rerun. pass1=$counts_after_first pass2=$counts_after_second"
  fi
  pass "Idempotency check passed (manifest counts unchanged on rerun)."

  run_clickup "US1 post-bootstrap status check" --status
  assert_status_output_shape "$LAST_LOG_FILE"
  assert_no_unresolved_drift "$LAST_LOG_FILE"
  assert_no_orphan_processes
}

run_us2() {
  echo ""
  info "Section 3: US2 - Read-only live status reflection"

  [ -f "$MANIFEST_PATH" ] || die "US2 requires existing manifest. Run US1/bootstrap first."

  local gate_status
  if confirm_section_gate \
    "US2" \
    "Bootstrap has completed at least once (manifest exists)" \
    "At least one ClickUp subtask was moved to Done/In Progress/Blocked for status reflection validation"; then
    gate_status=0
  else
    gate_status=$?
  fi
  if [ "$gate_status" -eq 10 ]; then
    info "US2 skipped by user"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    return 0
  fi
  [ "$gate_status" -eq 0 ] || die "US2 stopped by user"

  local manifest_before manifest_after
  manifest_before="$(manifest_signature)"
  [ "$manifest_before" != "missing" ] || die "Manifest missing before status run."
  [ "$manifest_before" != "invalid-json" ] || die "Manifest invalid before status run."

  run_clickup "US2 status read-only check" --status
  assert_status_output_shape "$LAST_LOG_FILE"
  assert_no_unresolved_drift "$LAST_LOG_FILE"

  manifest_after="$(manifest_signature)"
  assert_manifest_unchanged "$manifest_before" "$manifest_after"

  require_human_verify \
    "Human verify required: confirm you changed at least one ClickUp subtask status before this US2 run" \
    || die "US2 failed required manual confirmation gate."
  pass "US2 required manual verification confirmed."

  assert_no_orphan_processes
}

run_final_section() {
  echo ""
  info "Section Final: Full feature integration flow"

  local gate_status
  if confirm_section_gate \
    "Final" \
    "Preflight, US1, and US2 have each passed at least once" \
    "ClickUp Space and required custom fields are still available"; then
    gate_status=0
  else
    gate_status=$?
  fi
  if [ "$gate_status" -eq 10 ]; then
    info "Final section skipped by user"
    SKIP_COUNT=$((SKIP_COUNT + 1))
    return 0
  fi
  [ "$gate_status" -eq 0 ] || die "Final section stopped by user"

  local before_counts after_counts
  before_counts="$(manifest_counts)"

  run_clickup "Final bootstrap"
  assert_manifest_integrity
  assert_manifest_timestamp_if_mutation_reported "$LAST_LOG_FILE" "$LAST_RUN_STARTED_AT"

  run_clickup "Final status" --status
  assert_status_output_shape "$LAST_LOG_FILE"
  assert_no_unresolved_drift "$LAST_LOG_FILE"

  after_counts="$(manifest_counts)"
  if [ "$before_counts" != "missing" ] && [ "$after_counts" != "missing" ] && [ "$before_counts" != "$after_counts" ]; then
    info "Manifest counts changed across final run: before=$before_counts after=$after_counts"
    info "This can be valid if new specs/tasks were added; verify expected change."
  else
    pass "Final manifest count stability check passed."
  fi

  assert_no_orphan_processes
}

run_section_selection() {
  local section_lower
  section_lower="$(printf "%s" "$SECTION" | tr '[:upper:]' '[:lower:]')"
  case "$section_lower" in
    all)
      run_us1
      run_us2
      run_final_section
      ;;
    us1)
      run_us1
      ;;
    us2)
      run_us2
      ;;
    final)
      run_final_section
      ;;
    *)
      die "Unknown section '$SECTION'. Expected: all|us1|us2|final"
      ;;
  esac
}

print_verify_commands() {
  echo ""
  echo "Verification commands:"
  echo "  scripts/e2e_018_clickup_sync.sh preflight ${CONFIG_PATH:-<env-file>}"
  echo "  scripts/e2e_018_clickup_sync.sh run ${CONFIG_PATH:-<env-file>} us1"
  echo "  scripts/e2e_018_clickup_sync.sh run ${CONFIG_PATH:-<env-file>} us2"
  echo "  scripts/e2e_018_clickup_sync.sh run ${CONFIG_PATH:-<env-file>} final"
  echo "  scripts/e2e_018_clickup_sync.sh ci ${CONFIG_PATH:-<env-file>}"
  echo ""
  echo "Direct module commands:"
  echo "  ${PYTHON_CMD[*]} -m mcp_clickup"
  echo "  ${PYTHON_CMD[*]} -m mcp_clickup --status"
  echo ""
  echo "Manifest path: $MANIFEST_PATH"
}

run_verify() {
  echo ""
  info "Verify: lightweight checks"
  print_verify_commands

  prepare_context
  load_env_file_if_present
  assert_required_env
  assert_mcp_clickup_importable

  if [ ! -f "$MANIFEST_PATH" ]; then
    skip "Manifest missing; run bootstrap first for deeper verify checks."
    return 0
  fi

  assert_manifest_integrity
  local before_sig after_sig
  before_sig="$(manifest_signature)"

  run_clickup "Verify status read-only check" --status
  assert_status_output_shape "$LAST_LOG_FILE"
  assert_no_unresolved_drift "$LAST_LOG_FILE"

  after_sig="$(manifest_signature)"
  assert_manifest_unchanged "$before_sig" "$after_sig"
  assert_no_orphan_processes
}

prepare_context
load_env_file_if_present
print_summary

case "$COMMAND" in
  preflight)
    run_preflight
    ;;
  run)
    assert_required_env
    run_section_selection
    ;;
  verify)
    run_verify
    ;;
  ci)
    run_preflight
    run_verify
    ;;
  full)
    run_preflight
    assert_required_env
    run_section_selection
    run_verify
    ;;
  *)
    die "Unhandled command: $COMMAND"
    ;;
esac

echo ""
info "Completed with ${PASS_COUNT} passed check(s), ${SKIP_COUNT} skipped check(s)."
