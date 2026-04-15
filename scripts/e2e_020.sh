#!/usr/bin/env bash
# E2E Testing Pipeline: Extract App Foundation Template (Feature 020)
# Validates: Repository extraction, dependency resolution, service boot, zero trading imports,
# governance pipeline dry-run, and contract test suite pass.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="${1:-.env.control-plane.example}"
TEMP_DIR=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Cleanup trap
cleanup() {
  if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
  fi
  # Kill any lingering background processes
  jobs -p | xargs kill 2>/dev/null || true
}
trap cleanup EXIT

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $*"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

# Validate prerequisites
validate_prerequisites() {
  log_info "Validating prerequisites..."

  command -v python3 >/dev/null 2>&1 || { log_fail "python3 not found"; exit 1; }
  command -v uv >/dev/null 2>&1 || { log_fail "uv package manager not found"; exit 1; }
  command -v git >/dev/null 2>&1 || { log_fail "git not found"; exit 1; }

  python3 --version | grep -q "3.1[2-9]" || { log_warn "Python 3.12+ recommended"; }

  log_pass "All prerequisites found"
}

# Section 1: Preflight (Dry-Run)
section_preflight() {
  log_info "=== Section 1: Preflight (Dry-Run) ==="

  cd "$REPO_ROOT"

  # Check repository structure
  log_info "Checking repository structure..."
  required_dirs=(
    "src/clickup_control_plane"
    "src/mcp_codebase"
    "src/mcp_trello"
    "src/mcp_clickup"
    "tests/contract"
    "tests/unit"
    "specs/014-clickup-n8n-control-plane"
    "specs/015-control-plane-dispatch"
    "specs/016-control-plane-qa-loop"
    "specs/017-control-plane-hitl-audit"
    ".claude/domains"
    ".claude/commands"
    ".speckit"
    "scripts"
  )

  for dir in "${required_dirs[@]}"; do
    [ -d "$dir" ] || { log_fail "Missing directory: $dir"; exit 1; }
  done
  log_pass "Repository structure valid"

  # Python syntax validation
  log_info "Validating Python syntax..."
  find src -name "*.py" -type f | while read -r py_file; do
    run_python -m py_compile "$py_file" 2>/dev/null || { log_fail "Syntax error in $py_file"; exit 1; }
  done
  log_pass "All Python files compile cleanly"

  # Trading reference sweep
  log_info "Sweeping for trading references..."
  trading_matches=$(grep -r "csp_trader\|ib_async\|ibkr\|gspread\|trading_state.db" \
    src/ tests/ --exclude-dir=.git --exclude-dir=__pycache__ 2>/dev/null | \
    grep -v "# origin:" | grep -v "# archived from" | wc -l)

  if [ "$trading_matches" -gt 0 ]; then
    log_fail "Found $trading_matches trading references"
    exit 1
  fi
  log_pass "Zero trading references found"

  # Dependency file validation
  log_info "Validating configuration files..."
  run_python -c "import tomllib; tomllib.loads(open('pyproject.toml').read())" 2>/dev/null || \
    { log_fail "Invalid pyproject.toml syntax"; exit 1; }
  run_python -c "import yaml; yaml.safe_load(open('catalog.yaml'))" 2>/dev/null || \
    { log_fail "Invalid catalog.yaml syntax"; exit 1; }
  log_pass "Configuration files valid"

  # File count verification
  log_info "Verifying file counts..."
  src_count=$(find src -name "*.py" -type f | wc -l)
  test_count=$(find tests -name "*.py" -type f | wc -l)

  if [ "$src_count" -lt 30 ] || [ "$src_count" -gt 36 ]; then
    log_warn "Source file count ($src_count) outside expected range (30-36)"
  else
    log_pass "Source file count acceptable ($src_count files)"
  fi

  if [ "$test_count" -lt 38 ] || [ "$test_count" -gt 42 ]; then
    log_warn "Test file count ($test_count) outside expected range (38-42)"
  else
    log_pass "Test file count acceptable ($test_count files)"
  fi

  log_pass "Section 1 (Preflight) complete"
}

# Section 2: User Story 1 - Clone and Boot
section_us1_boot() {
  log_info "=== Section 2: User Story 1 - Clone Template and Boot Services ==="

  cd "$REPO_ROOT"

  # Dependency resolution
  log_info "Testing dependency resolution (uv sync --frozen)..."
  start_time=$(date +%s)
  if ! uv sync --frozen >/dev/null 2>&1; then
    log_fail "uv sync failed"
    exit 1
  fi
  end_time=$(date +%s)
  sync_time=$((end_time - start_time))

  if [ "$sync_time" -gt 30 ]; then
    log_warn "uv sync took ${sync_time}s (expected < 30s)"
  else
    log_pass "uv sync completed in ${sync_time}s (SC-002)"
  fi

  # Control plane boot
  log_info "Testing control plane boot..."
  start_time=$(date +%s%N)
  timeout 15 uvicorn clickup_control_plane.app:app --port 8000 \
    >/tmp/control_plane.log 2>&1 &
  cp_pid=$!
  sleep 2

  http_code=$(curl -s http://localhost:8000/webhook -X GET -w "%{http_code}" -o /dev/null 2>/dev/null || echo "000")
  kill "$cp_pid" 2>/dev/null || true
  wait "$cp_pid" 2>/dev/null || true

  end_time=$(date +%s%N)
  boot_time=$(( (end_time - start_time) / 1000000 ))

  if [ "$http_code" != "405" ]; then
    log_fail "Control plane did not respond correctly (got $http_code, expected 405)"
    exit 1
  fi
  log_pass "Control plane booted and responded correctly (SC-001)"

  # Zero trading imports check
  log_info "Checking for zero trading imports..."
  trading_imports=$(grep -r "from csp_trader\|from ib_async\|import csp_trader\|import ibkr\|gspread" \
    src/ tests/ --exclude-dir=.git --exclude-dir=__pycache__ 2>/dev/null | wc -l)

  if [ "$trading_imports" -gt 0 ]; then
    log_fail "Found trading imports"
    exit 1
  fi
  log_pass "Zero trading imports confirmed (SC-004, SC-006)"

  log_pass "Section 2 (US1 - Boot) complete"
}

# Section 3: User Story 2 - Domain Adaptation
section_us2_domain() {
  log_info "=== Section 3: User Story 2 - Adapt Template for New Domain ==="

  cd "$REPO_ROOT"

  # CLAUDE.md domain-agnostic check
  log_info "Checking CLAUDE.md for trading language..."
  claude_matches=$(grep -i "ib-trading\|options trading\|csp\|ibkr" CLAUDE.md 2>/dev/null | wc -l)
  if [ "$claude_matches" -gt 0 ]; then
    log_fail "Found trading references in CLAUDE.md"
    exit 1
  fi
  log_pass "CLAUDE.md is domain-agnostic"

  # constitution.md check
  log_info "Checking constitution.md title..."
  if ! head -1 constitution.md | grep -q "app-foundation"; then
    log_warn "constitution.md title not updated to app-foundation"
  else
    log_pass "constitution.md title updated"
  fi

  # catalog.yaml check
  log_info "Checking catalog.yaml for trading components..."
  catalog_trading=$(grep -E "csp_trader|sqlite-trading|ibkr-gateway|google-sheets" catalog.yaml 2>/dev/null | wc -l)
  if [ "$catalog_trading" -gt 0 ]; then
    log_fail "Found trading components in catalog.yaml"
    exit 1
  fi
  log_pass "catalog.yaml has no trading components"

  # Human verification gate
  log_info ""
  log_warn "=== HUMAN VERIFICATION REQUIRED ==="
  log_info "Run: /speckit.specify \"Test feature: domain verification\""
  log_info "Then verify the generated spec contains zero trading references."
  read -r -p "Has human verification been completed? (yes/no): " human_verify

  if [ "$human_verify" != "yes" ]; then
    log_warn "Human verification skipped; marking section as BLOCKED"
    return 1
  fi

  log_pass "Section 3 (US2 - Domain) complete"
}

# Section 4: User Story 3 - Control Plane Tests
section_us3_control_plane() {
  log_info "=== Section 4: User Story 3 - Verify Control Plane Operates ==="

  cd "$REPO_ROOT"

  # Contract tests
  log_info "Running control plane contract tests (SC-003)..."
  if ! pytest tests/contract/test_clickup_control_plane_contract.py -v --tb=short; then
    log_fail "Contract tests failed"
    exit 1
  fi
  log_pass "Control plane contract tests passed (SC-003)"

  # Unit tests
  log_info "Running control plane unit tests..."
  if ! pytest tests/unit/clickup_control_plane/ -v --tb=short; then
    log_fail "Unit tests failed"
    exit 1
  fi
  log_pass "Control plane unit tests passed"

  # Audit dispatch logic
  log_info "Auditing dispatch logic for trading code..."
  dispatch_trading=$(grep -i "trading\|csp\|options\|ibkr" src/clickup_control_plane/routes.py 2>/dev/null | wc -l)
  if [ "$dispatch_trading" -gt 0 ]; then
    log_fail "Found trading references in dispatch logic"
    exit 1
  fi
  log_pass "Dispatch logic contains zero trading-specific code"

  # Verify routes
  log_info "Verifying dispatch routes..."
  if ! grep -q "/control-plane/build-spec" src/clickup_control_plane/routes.py; then
    log_fail "Route /control-plane/build-spec not found"
    exit 1
  fi
  if ! grep -q "/control-plane/qa-loop" src/clickup_control_plane/routes.py; then
    log_fail "Route /control-plane/qa-loop not found"
    exit 1
  fi
  log_pass "All dispatch routes unchanged"

  log_pass "Section 4 (US3 - Control Plane) complete"
}

# Section 5: User Story 4 - Speckit Pipeline
section_us4_governance() {
  log_info "=== Section 5: User Story 4 - Speckit Pipeline Runs Dry ==="

  cd "$REPO_ROOT"

  # Check governance scripts exist
  log_info "Checking governance scripts..."
  [ -f "scripts/task_ledger.py" ] || { log_fail "task_ledger.py not found"; exit 1; }
  [ -f "scripts/pipeline_ledger.py" ] || { log_fail "pipeline_ledger.py not found"; exit 1; }
  [ -f "scripts/cgc_safe_index.sh" ] || { log_fail "cgc_safe_index.sh not found"; exit 1; }
  log_pass "Governance scripts present"

  # Verify domains are domain-agnostic
  log_info "Checking .claude/domains for trading language..."
  domains_trading=$(grep -ri "trading\|csp\|options\|ibkr" .claude/domains/ \
    --exclude-dir=.git 2>/dev/null | grep -v "# origin:" | grep -v "# archived" | wc -l)
  if [ "$domains_trading" -gt 0 ]; then
    log_fail "Found trading references in governance domains"
    exit 1
  fi
  log_pass "Governance domains are domain-agnostic"

  # Check task ledger bootstrap
  log_info "Checking task ledger bootstrap..."
  if ! [ -f ".speckit/task-ledger.jsonl" ]; then
    log_fail "task-ledger.jsonl not found"
    exit 1
  fi
  log_pass "Task ledger exists"

  # Human verification gate
  log_info ""
  log_warn "=== HUMAN VERIFICATION REQUIRED ==="
  log_info "Run: /speckit.specify \"Test feature: governance dry-run\""
  log_info "Verify generated spec in specs/021-test-feature/ has zero trading references"
  read -r -p "Has human verification been completed? (yes/no): " human_verify_us4

  if [ "$human_verify_us4" != "yes" ]; then
    log_warn "Human verification skipped; marking section as BLOCKED"
    return 1
  fi

  log_pass "Section 5 (US4 - Governance) complete"
}

# Section Final: Full Feature E2E
section_final_full() {
  log_info "=== Section Final: Full Feature E2E ==="

  cd "$REPO_ROOT"

  log_info "Running preflight..."
  section_preflight || { log_fail "Preflight failed"; exit 1; }

  log_info "Running all user story sections..."
  section_us1_boot || { log_fail "US1 failed"; exit 1; }
  section_us2_domain || { log_fail "US2 failed (check human verification)"; }
  section_us3_control_plane || { log_fail "US3 failed"; exit 1; }
  section_us4_governance || { log_fail "US4 failed (check human verification)"; }

  log_pass "=== Full Feature E2E Complete ==="
}

# Non-interactive CI mode
section_ci() {
  log_info "=== CI Mode: Automated Checks Only ==="

  section_preflight || { log_fail "Preflight failed"; exit 1; }
  section_us1_boot || { log_fail "US1 failed"; exit 1; }
  section_us3_control_plane || { log_fail "US3 failed"; exit 1; }

  log_pass "=== CI Mode Complete ==="
}

# Usage
usage() {
  cat <<EOF
Usage: $0 <subcommand> [config]

Subcommands:
  preflight   Run dry-run smoke test (no external deps)
  run         Run all user story sections (interactive, with human gates)
  full        Run complete E2E pipeline (all sections + human gates)
  ci          Run CI-safe automated checks only (no human gates)
  verify      Print verification commands and run lightweight checks

Config: Path to .env file (optional, defaults to .env.control-plane.example)

Examples:
  $0 preflight
  $0 run .env
  $0 full
  $0 ci

EOF
  exit 1
}

# Main entry point
if [ $# -lt 1 ]; then
  usage
fi

subcommand="$1"

case "$subcommand" in
  preflight)
    validate_prerequisites
    section_preflight
    ;;
  run)
    validate_prerequisites
    section_preflight
    section_us1_boot
    section_us2_domain || log_warn "US2 human verification incomplete"
    section_us3_control_plane
    section_us4_governance || log_warn "US4 human verification incomplete"
    log_pass "=== All Sections Complete ==="
    ;;
  full)
    validate_prerequisites
    section_final_full
    ;;
  ci)
    validate_prerequisites
    section_ci
    ;;
  verify)
    log_info "=== Verification Commands ==="
    log_info "Check Python syntax:"
    echo "  uv run python -m py_compile src/clickup_control_plane/*.py"
    log_info "List imports:"
    echo "  grep -r '^import\|^from' src/ | sort -u | head -20"
    log_info "Count source files:"
    echo "  find src -name '*.py' | wc -l"
    log_info "Check YAML syntax:"
    echo "  uv run python -c \"import yaml; yaml.safe_load(open('catalog.yaml'))\""
    log_info "Run contract tests:"
    echo "  pytest tests/contract/test_clickup_control_plane_contract.py -v"
    log_info "Check for trading code:"
    echo "  grep -r 'csp_trader\|ib_async\|ibkr' src/ tests/"
    ;;
  *)
    log_fail "Unknown subcommand: $subcommand"
    usage
    ;;
esac
