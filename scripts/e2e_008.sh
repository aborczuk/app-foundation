#!/usr/bin/env bash
# E2E pipeline for 008-codebase-mcp-toolkit (Codebase MCP Toolkit)
# Usage: scripts/e2e_008.sh [preflight|us1|us2|us3|final|full|ci]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

COMMAND="${1:-full}"
E2E_NON_INTERACTIVE="${E2E_NON_INTERACTIVE:-0}"

LSP_LOG_ROOT="$REPO_ROOT/logs/codebase-lsp"
LATEST_RUN_POINTER="$LSP_LOG_ROOT/latest-run.json"

SERVER_PID=""
TMPDIR_LOCAL=""

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

die() {
  echo "ERROR: $*" >&2
  exit 1
}

info() {
  echo "  [INFO] $*"
}

pass() {
  echo "  [PASS] $*"
}

fail() {
  echo "  [FAIL] $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' not found — run: uv sync"
}

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    info "Stopping server (PID $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    local waited=0
    while kill -0 "$SERVER_PID" 2>/dev/null && [ "$waited" -lt 5 ]; do
      sleep 1
      waited=$((waited + 1))
    done
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      kill -9 "$SERVER_PID" 2>/dev/null || true
      info "Server force-killed."
    else
      info "Server stopped."
    fi
  fi
  if [ -n "$TMPDIR_LOCAL" ] && [ -d "$TMPDIR_LOCAL" ]; then
    rm -rf "$TMPDIR_LOCAL"
  fi
}
trap cleanup EXIT

PYTHON_CMD=(python3)
if command -v uv >/dev/null 2>&1; then
  PYTHON_CMD=(uv run python)
fi

# ---------------------------------------------------------------------------
# Pyright orphan-process tracking
# ---------------------------------------------------------------------------

count_pyright_procs() {
  # Count live pyright processes; returns 0 if none
  # pgrep returns exit 1 when no matches — guard with || true for pipefail
  local pids
  pids="$(pgrep -f "pyright" 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    echo 0
  else
    echo "$pids" | wc -l | tr -d ' '
  fi
}

assert_no_new_pyright_procs() {
  local baseline="$1"
  local label="$2"
  local current
  current="$(count_pyright_procs)"
  if [ "$current" -gt "$baseline" ]; then
    fail "Orphan pyright process detected after $label (baseline=$baseline, current=$current). Run: pgrep -fl pyright"
  fi
  pass "No orphan pyright processes after $label (count=$current)."
}

# ---------------------------------------------------------------------------
# Startup observability helpers
# ---------------------------------------------------------------------------

start_server_bg() {
  # Start mcp_codebase in background, capture PID
  info "Starting mcp_codebase server..."
  rm -f "$LATEST_RUN_POINTER"
  cd "$REPO_ROOT"
  "${PYTHON_CMD[@]}" -m mcp_codebase >/dev/null 2>&1 &
  SERVER_PID=$!
  info "Server PID: $SERVER_PID"
}

wait_for_pointer() {
  local timeout=8
  local waited=0
  info "Waiting for latest-run pointer (up to ${timeout}s)..."
  while [ ! -f "$LATEST_RUN_POINTER" ] && [ "$waited" -lt "$timeout" ]; do
    sleep 1
    waited=$((waited + 1))
  done
  [ -f "$LATEST_RUN_POINTER" ] || fail "latest-run.json not written after ${timeout}s — startup failed or T011 not yet implemented."
  pass "latest-run.json written."
}

assert_startup_observability() {
  # Resolve log_path from pointer, verify run_id and log_path appear in the log
  local pointer_script
  pointer_script="$(mktemp "${TMPDIR:-/tmp}/e2e008-XXXXXX")"
  cat > "$pointer_script" << 'PY'
import json
import sys
from pathlib import Path

pointer = Path(sys.argv[1])
try:
    payload = json.loads(pointer.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"Failed to parse pointer: {exc}", file=sys.stderr)
    sys.exit(1)

log_path = str(payload.get("log_path") or "").strip()
if not log_path:
    print("Pointer missing 'log_path'", file=sys.stderr)
    sys.exit(1)

log_file = Path(log_path)
if not log_file.exists():
    print(f"Log file not found: {log_path}", file=sys.stderr)
    sys.exit(1)

events = []
for line in log_file.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        events.append(json.loads(line))
    except Exception:
        pass

has_run_id = any("run_id" in e for e in events)
has_log_path = any("log_path" in e for e in events)

if not has_run_id:
    print("Startup events missing 'run_id'", file=sys.stderr)
    sys.exit(2)
if not has_log_path:
    print("Startup events missing 'log_path'", file=sys.stderr)
    sys.exit(2)

print(f"run_id and log_path confirmed in: {log_path}")
PY
  "${PYTHON_CMD[@]}" "$pointer_script" "$LATEST_RUN_POINTER"
  local rc=$?
  rm -f "$pointer_script"
  [ "$rc" -eq 0 ] || fail "Startup observability check failed (see above)."
  pass "Startup observability: run_id + log_path confirmed in active log."
}

stop_server() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    local waited=0
    while kill -0 "$SERVER_PID" 2>/dev/null && [ "$waited" -lt 5 ]; do
      sleep 1
      waited=$((waited + 1))
    done
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      kill -9 "$SERVER_PID" 2>/dev/null || true
    fi
    SERVER_PID=""
    pass "Server stopped."
  fi
}

# ---------------------------------------------------------------------------
# Section: Preflight
# ---------------------------------------------------------------------------

section_preflight() {
  echo ""
  echo "=== Section 1: Preflight ==="

  require_cmd "uv"
  pass "uv found: $(uv --version)"

  info "Checking pyright via uv..."
  local pv
  pv="$(uv run pyright --version 2>&1)" || die "pyright not available — run: uv sync"
  pass "pyright available: $pv"

  info "Checking mcp_codebase importable..."
  cd "$REPO_ROOT"
  "${PYTHON_CMD[@]}" -c "import mcp_codebase" 2>&1 || fail "mcp_codebase not importable — run: uv sync; confirm src/mcp_codebase/ is in pyproject.toml"
  pass "mcp_codebase importable."

  info "Checking codegraphcontext importable..."
  cd "$REPO_ROOT"
  "${PYTHON_CMD[@]}" -c "import codegraphcontext" 2>&1 || fail "codegraphcontext not importable — run: uv sync; confirm codegraphcontext is in pyproject.toml dev deps"
  pass "codegraphcontext importable."

  info "Checking cgc CLI..."
  uv run cgc --help >/dev/null 2>&1 || fail "cgc CLI not available — run: uv sync"
  pass "cgc CLI available."

  info "Running pytest collection smoke test..."
  cd "$REPO_ROOT"
  uv run pytest tests/mcp_codebase/ --collect-only -q 2>&1 | tail -5 || fail "pytest collection failed — fix import errors before proceeding."
  pass "pytest collection succeeded."

  echo "[PASS] Preflight complete."
}

# ---------------------------------------------------------------------------
# Section: US1 — get_type
# ---------------------------------------------------------------------------

section_us1() {
  echo ""
  echo "=== Section 2: US1 — Type Inference (get_type) ==="

  local baseline
  baseline="$(count_pyright_procs)"
  info "Baseline pyright process count: $baseline"

  cd "$REPO_ROOT"

  # Startup observability gate
  start_server_bg
  wait_for_pointer
  sleep 1  # brief settle for log flush
  assert_startup_observability
  stop_server
  assert_no_new_pyright_procs "$baseline" "server shutdown"

  # Unit + integration tests for get_type (against real pyright)
  info "Running get_type + path security + pyright client tests..."
  uv run pytest \
    tests/mcp_codebase/test_type_tool.py \
    tests/mcp_codebase/test_pyright_client.py \
    tests/mcp_codebase/test_path_security.py \
    -v --tb=short 2>&1 || fail "US1 tests failed — see above."
  pass "get_type + path security + pyright client tests passed."

  # Event-loop regression (non-fatal if no matching tests yet — flag as gap)
  info "Running event-loop regression tests for get_type..."
  local el_out
  el_out="$(uv run pytest tests/mcp_codebase/test_pyright_client.py -k "event_loop or running_loop" -v --tb=short 2>&1)" || true
  if echo "$el_out" | grep -q "no tests ran"; then
    echo "  [WARN] No event-loop regression tests collected — task T014 may not yet be implemented."
  elif echo "$el_out" | grep -q "FAILED"; then
    fail "Event-loop regression tests FAILED:\n$el_out"
  else
    pass "Event-loop regression tests passed."
  fi

  assert_no_new_pyright_procs "$baseline" "US1 test suite"

  echo "[PASS] Section US1 complete."
}

# ---------------------------------------------------------------------------
# Section: US2 — get_diagnostics
# ---------------------------------------------------------------------------

section_us2() {
  echo ""
  echo "=== Section 3: US2 — Diagnostics After Editing (get_diagnostics) ==="

  local baseline
  baseline="$(count_pyright_procs)"
  info "Baseline pyright process count: $baseline"

  cd "$REPO_ROOT"

  # Unit + integration tests for get_diagnostics
  info "Running get_diagnostics tests..."
  uv run pytest \
    tests/mcp_codebase/test_diag_tool.py \
    -v --tb=short 2>&1 || fail "US2 diagnostics tests failed — see above."
  pass "get_diagnostics tests passed."

  # Server-level integration for diagnostics
  info "Running server-level get_diagnostics integration tests..."
  local srv_out
  srv_out="$(uv run pytest tests/mcp_codebase/test_server.py -k "diagnostics or get_diagnostics" -v --tb=short 2>&1)" || true
  if echo "$srv_out" | grep -q "no tests ran"; then
    echo "  [WARN] No server-level diagnostics tests collected — task T021 may not yet be implemented."
  elif echo "$srv_out" | grep -q "FAILED"; then
    fail "Server-level diagnostics tests FAILED."
  else
    pass "Server-level diagnostics integration tests passed."
  fi

  # Timeout/orphan kill test
  info "Running timeout+orphan kill validation tests..."
  local to_out
  to_out="$(uv run pytest tests/mcp_codebase/test_diag_tool.py -k "timeout or orphan" -v --tb=short 2>&1)" || true
  if echo "$to_out" | grep -q "no tests ran"; then
    echo "  [WARN] No timeout/orphan tests collected — tasks T024/T031 may not yet be implemented."
  elif echo "$to_out" | grep -q "FAILED"; then
    fail "Timeout/orphan kill tests FAILED."
  else
    pass "Timeout/orphan kill tests passed."
  fi

  # Event-loop regression for diagnostics
  info "Running event-loop regression tests for get_diagnostics..."
  local el_out
  el_out="$(uv run pytest tests/mcp_codebase/test_diag_tool.py -k "event_loop or running_loop" -v --tb=short 2>&1)" || true
  if echo "$el_out" | grep -q "no tests ran"; then
    echo "  [WARN] No event-loop regression tests collected — task T023 may not yet be implemented."
  elif echo "$el_out" | grep -q "FAILED"; then
    fail "Event-loop regression tests FAILED."
  else
    pass "Event-loop regression tests passed."
  fi

  assert_no_new_pyright_procs "$baseline" "US2 test suite"

  echo "[PASS] Section US2 complete."
}

# ---------------------------------------------------------------------------
# Section: US3 — CGC Integration (Adopted Dependency)
# ---------------------------------------------------------------------------

section_us3() {
  echo ""
  echo "=== Section 4: US3 — Code Graph Intelligence (CGC Integration) ==="

  cd "$REPO_ROOT"

  # 1. Package importable
  info "Verifying codegraphcontext package is importable..."
  "${PYTHON_CMD[@]}" -c "import codegraphcontext" 2>&1 || fail "codegraphcontext not importable."
  pass "codegraphcontext importable."

  # 2. CGC CLI works
  info "Verifying cgc CLI responds to --help..."
  uv run cgc --help >/dev/null 2>&1 || fail "cgc CLI not available."
  pass "cgc CLI available."

  # 3. CGC index artifacts exist
  info "Checking for CGC index artifacts..."
  if [ -d "$REPO_ROOT/.codegraph" ] || find "$REPO_ROOT" -maxdepth 2 -name "*.kuzudb" -o -name "kuzu*" 2>/dev/null | grep -q .; then
    pass "CGC index artifacts found."
  else
    fail "No CGC index artifacts found — run: $REPO_ROOT/scripts/cgc_index_repo.sh"
  fi

  # 4. .mcp.json has correct registration
  info "Verifying .mcp.json has correct CGC registration..."
  local mcp_check_script
  mcp_check_script="$(mktemp "${TMPDIR:-/tmp}/e2e008-mcp-XXXXXX")"
  cat > "$mcp_check_script" << 'PY'
import json, sys
d = json.loads(open(sys.argv[1]).read())
cg = d.get("mcpServers", {}).get("codegraph", {})
cmd = cg.get("command", "")
args = cg.get("args", [])
if cmd != "uv":
    print(f"FAIL: codegraph command is '{cmd}', expected 'uv'", file=sys.stderr)
    sys.exit(1)
if "cgc" not in args:
    print(f"FAIL: codegraph args {args} do not contain 'cgc'", file=sys.stderr)
    sys.exit(1)
if "npx" in cmd or "codegraph-mcp" in str(args):
    print("FAIL: .mcp.json still has fabricated codegraph-mcp reference", file=sys.stderr)
    sys.exit(1)
print("OK: .mcp.json codegraph uses 'uv run cgc mcp start'")
PY
  "${PYTHON_CMD[@]}" "$mcp_check_script" "$REPO_ROOT/.mcp.json"
  local rc=$?
  rm -f "$mcp_check_script"
  [ "$rc" -eq 0 ] || fail ".mcp.json CGC registration check failed."
  pass ".mcp.json has correct CGC registration."

  # 5. Restart/probe CGC MCP and verify required tools + latency thresholds
  info "Verifying CGC MCP tool list and SC-005/SC-006 latency gates..."
  local cgc_verify_script
  cgc_verify_script="$(mktemp "${TMPDIR:-/tmp}/e2e008-cgc-XXXXXX")"
  cat > "$cgc_verify_script" << 'PY'
import asyncio
import json
import sys
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

repo_root = sys.argv[1]
target = "_parse_rfc3339"
context = f"{repo_root}/src/csp_trader/dashboard/timeline_view.py"

def _text_payload(resp):
    return "\n".join(
        item.text for item in (resp.content or [])
        if getattr(item, "text", None) is not None
    )

async def main():
    params = StdioServerParameters(
        command="uv",
        args=["run", "cgc", "mcp", "start"],
        cwd=repo_root,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            if "find_code" not in names or "analyze_code_relationships" not in names:
                print(
                    "Missing required CGC tools. "
                    f"find_code={'find_code' in names}, "
                    f"analyze_code_relationships={'analyze_code_relationships' in names}",
                    file=sys.stderr,
                )
                return 2

            t0 = time.monotonic()
            find_resp = await session.call_tool(
                "find_code",
                {"query": target, "repo_path": repo_root},
            )
            find_s = time.monotonic() - t0
            find_json = json.loads(_text_payload(find_resp))
            find_total = int(find_json.get("results", {}).get("total_matches", 0))
            if find_total <= 0:
                print(
                    f"find_code returned no matches for '{target}'",
                    file=sys.stderr,
                )
                return 3
            if find_s >= 2.0:
                print(
                    f"find_code latency {find_s:.3f}s exceeds 2.0s",
                    file=sys.stderr,
                )
                return 4

            t1 = time.monotonic()
            rel_resp = await session.call_tool(
                "analyze_code_relationships",
                {
                    "query_type": "find_callers",
                    "target": target,
                    "context": context,
                    "repo_path": repo_root,
                },
            )
            rel_s = time.monotonic() - t1
            rel_json = json.loads(_text_payload(rel_resp))
            rel_count = len(rel_json.get("results", {}).get("results", []))
            if rel_count <= 0:
                print(
                    "analyze_code_relationships returned no callers for "
                    f"'{target}'",
                    file=sys.stderr,
                )
                return 5
            if rel_s >= 3.0:
                print(
                    f"analyze_code_relationships latency {rel_s:.3f}s exceeds 3.0s",
                    file=sys.stderr,
                )
                return 6

            print(
                "OK: tools present + latency pass "
                f"(find_code={find_s:.3f}s, analyze_code_relationships={rel_s:.3f}s)"
            )
            return 0

rc = asyncio.run(main())
raise SystemExit(rc)
PY
  "${PYTHON_CMD[@]}" "$cgc_verify_script" "$REPO_ROOT" 2>&1 || fail "CGC MCP tool/latency verification failed."
  rm -f "$cgc_verify_script"
  pass "CGC MCP tool list + SC-005/SC-006 latency checks passed."

  # 6. CLAUDE.md has real CGC tool names
  info "Verifying CLAUDE.md has real CGC tool names (not fabricated)..."
  if grep -q "find_code" "$REPO_ROOT/CLAUDE.md" && grep -q "analyze_code_relationships" "$REPO_ROOT/CLAUDE.md"; then
    if grep -q "codegraph_search" "$REPO_ROOT/CLAUDE.md" || grep -q "codegraph_context" "$REPO_ROOT/CLAUDE.md" || grep -q "codegraph_node" "$REPO_ROOT/CLAUDE.md"; then
      fail "CLAUDE.md still contains fabricated tool names (codegraph_search, codegraph_context, etc.)."
    fi
    pass "CLAUDE.md has real CGC tool names."
  else
    fail "CLAUDE.md missing real CGC tool names (find_code, analyze_code_relationships)."
  fi

  # 7. .gitignore excludes CGC index artifacts
  info "Verifying .gitignore excludes CGC index artifacts..."
  if grep -q "codegraph\|\.codegraph" "$REPO_ROOT/.gitignore" 2>/dev/null; then
    pass ".gitignore excludes CGC index artifacts."
  else
    fail ".gitignore does not exclude CGC index artifacts — add .codegraph/ pattern."
  fi

  # 8. codebase-lsp independence test
  info "Running CGC integration tests (including degraded-mode independence)..."
  if [ -f "$REPO_ROOT/tests/mcp_codebase/test_cgc_integration.py" ]; then
    uv run pytest tests/mcp_codebase/test_cgc_integration.py -v --tb=short 2>&1 || fail "CGC integration tests failed."
    pass "CGC integration tests passed."
  else
    echo "  [WARN] tests/mcp_codebase/test_cgc_integration.py not found — T036/T037 not yet implemented."
  fi

  echo "[PASS] Section US3 complete."
}

# ---------------------------------------------------------------------------
# Section: Final — Definition of Done
# ---------------------------------------------------------------------------

section_final() {
  echo ""
  echo "=== Section Final: Full Feature E2E (Definition of Done) ==="

  local baseline
  baseline="$(count_pyright_procs)"
  info "Baseline pyright process count: $baseline"

  cd "$REPO_ROOT"

  # Full test suite
  info "Running full tests/mcp_codebase/ suite..."
  uv run pytest tests/mcp_codebase/ -v --tb=short 2>&1 || fail "Full test suite failed — see above."
  pass "Full test suite passed."

  # Definition-of-done integration test (T030)
  info "Running definition-of-done test (get_type → edit → get_diagnostics → revert)..."
  local dod_out
  dod_out="$(uv run pytest tests/mcp_codebase/test_server.py -k "e2e or dod or definition_of_done" -v --tb=short 2>&1)" || true
  if echo "$dod_out" | grep -q "no tests ran"; then
    echo "  [WARN] No DoD test collected — task T030 may not yet be implemented."
  elif echo "$dod_out" | grep -q "FAILED"; then
    fail "Definition-of-done test FAILED."
  else
    pass "Definition-of-done test passed."
  fi

  # Cross-story orphan cleanup (T031)
  info "Running cross-story orphan cleanup verification..."
  local orphan_out
  orphan_out="$(uv run pytest tests/mcp_codebase/test_server.py -k "orphan or cleanup" -v --tb=short 2>&1)" || true
  if echo "$orphan_out" | grep -q "no tests ran"; then
    echo "  [WARN] No cross-story orphan tests collected — task T031 may not yet be implemented."
  elif echo "$orphan_out" | grep -q "FAILED"; then
    fail "Cross-story orphan cleanup tests FAILED."
  else
    pass "Cross-story orphan cleanup tests passed."
  fi

  assert_no_new_pyright_procs "$baseline" "full suite"

  # CGC artifact verification (same checks as section_us3 steps 4-6)
  info "Verifying CGC integration artifacts in final gate..."
  if grep -q "find_code" "$REPO_ROOT/CLAUDE.md" && ! grep -q "codegraph_search" "$REPO_ROOT/CLAUDE.md"; then
    pass "CLAUDE.md: real CGC tool names confirmed."
  else
    fail "CLAUDE.md: fabricated CGC tool names still present."
  fi

  # Final startup observability check
  info "Final startup observability verification..."
  start_server_bg
  wait_for_pointer
  sleep 1
  assert_startup_observability
  stop_server
  assert_no_new_pyright_procs "$baseline" "final server shutdown"

  echo "[PASS] Section Final complete."
}

# ---------------------------------------------------------------------------
# CI mode (non-interactive, automation-safe only)
# ---------------------------------------------------------------------------

section_ci() {
  echo ""
  echo "=== CI Mode (non-interactive checks only) ==="
  section_preflight
  # Collection-only confirms package is wired; full live tests need pyright subprocess
  # which is fine in CI if pyright is installed. Run full suite.
  cd "$REPO_ROOT"
  info "Running full test suite in CI mode..."
  uv run pytest tests/mcp_codebase/ -v --tb=short 2>&1 || fail "CI test suite failed."
  pass "CI test suite passed."
  # CGC artifact checks (non-interactive, automation-safe)
  section_us3
  echo "[PASS] CI mode complete."
}

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

usage() {
  cat << 'USAGE'
Usage:
  scripts/e2e_008.sh [preflight|us1|us2|us3|final|full|ci]

Commands:
  preflight   Dependency checks + import smoke test (pyright + CGC, no live subprocess)
  us1         US1: get_type — startup observability + type inference tests
  us2         US2: get_diagnostics — diagnostics tests + orphan subprocess validation
  us3         US3: CGC integration — package, index, .mcp.json, CLAUDE.md, independence
  final       Definition of Done: full suite + DoD test + cross-story orphan check + CGC artifacts
  full        preflight → us1 → us2 → us3 → final (default)
  ci          Non-interactive: preflight + full test suite (automation-safe)

Non-interactive mode:
  Set E2E_NON_INTERACTIVE=1 — interactive prompts become hard failures.
  (This server has no interactive human gates; E2E_NON_INTERACTIVE has no effect currently.)
USAGE
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

case "$COMMAND" in
  preflight)
    section_preflight
    ;;
  us1)
    section_us1
    ;;
  us2)
    section_us2
    ;;
  final)
    section_final
    ;;
  us3)
    section_us3
    ;;
  full)
    section_preflight
    section_us1
    section_us2
    section_us3
    section_final
    echo ""
    echo "=== ALL SECTIONS PASSED ==="
    ;;
  ci)
    section_ci
    ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage
    exit 1
    ;;
esac
