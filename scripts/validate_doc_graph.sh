#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(CDPATH="" cd "$SCRIPT_DIR/.." && pwd)"

failures=0
checks_run=0

fail() {
  echo "ERROR: $1" >&2
  failures=$((failures + 1))
}

pass() {
  echo "PASS: $1"
}

run_command_coverage_validator() {
  local output
  checks_run=$((checks_run + 1))
  if output="$(
    cd "$REPO_ROOT" && \
      env UV_CACHE_DIR="${SPECKIT_UV_CACHE_DIR:-/tmp/uv-cache}" \
      uv run python scripts/validate_command_script_coverage.py --json 2>&1
  )"; then
    pass "command/script coverage validator"
  else
    fail "command/script coverage validator failed"
    echo "$output"
  fi
}

run_forbidden_literal_check() {
  local label="$1"
  local literal="$2"
  shift 2
  local scope_paths=("$@")
  local output

  checks_run=$((checks_run + 1))
  output="$(cd "$REPO_ROOT" && rg -n --no-heading -S "$literal" "${scope_paths[@]}" || true)"
  if [[ -n "$output" ]]; then
    fail "$label"
    echo "$output"
  else
    pass "$label"
  fi
}

assert_exists() {
  local path="$1"
  checks_run=$((checks_run + 1))
  if [[ -f "$REPO_ROOT/$path" ]]; then
    pass "required file exists: $path"
  else
    fail "required file missing: $path"
  fi
}

assert_not_exists() {
  local path="$1"
  local reason="$2"
  checks_run=$((checks_run + 1))
  if [[ ! -f "$REPO_ROOT/$path" ]]; then
    pass "anti-regression: $reason"
  else
    fail "anti-regression VIOLATION: $reason (file exists at $path)"
  fi
}

main() {
  assert_exists "docs/governance/doc-graph.yaml"
  assert_exists "constitution.md"
  assert_exists "CLAUDE.md"
  assert_exists "catalog.yaml"
  run_command_coverage_validator

  # Phase 5 (T041): Anti-regression guard for mirror manifest removal
  assert_not_exists "command-manifest.yaml" \
    "root mirror manifest removed and not reintroduced (.specify/command-manifest.yaml is canonical)"

  # NOTE: Trading-specific check removed for app-foundation template
  # (no hardcoded behavior-map target for feature 001 in commands/templates)

  run_forbidden_literal_check \
    "no stale .specify/templates/commands/ references in propagation logic" \
    ".specify/templates/commands/" \
    ".claude/commands" ".specify/templates"

  checks_run=$((checks_run + 1))
  if [[ -f "$REPO_ROOT/CLAUDE.md" ]]; then
    manual_block="$(
      sed -n '/<!-- MANUAL ADDITIONS START -->/,/<!-- MANUAL ADDITIONS END -->/p' \
        "$REPO_ROOT/CLAUDE.md"
    )"
    principle_hits="$(printf "%s\n" "$manual_block" | rg -n '^### (Human-First Decisions|Security First|Reuse|Separation of Concerns \(SoC\)|Observability and Fail Gracefully|Local Database Transaction Integrity \(ACID\)|Test-Driven Development \(TDD\)|Documentation as a First-Class Standard|Parsimony|Reuse Over Invention|Composability and Modularity|Keep It Simple, Stupid \(KISS\) & YAGNI|The SOLID Principles|Don'"'"'t Repeat Yourself \(DRY\))' || true)"
    if [[ -n "$principle_hits" ]]; then
      fail "CLAUDE.md manual block duplicates principle headings owned by constitution"
      echo "$principle_hits"
    else
      pass "CLAUDE.md manual block avoids constitution principle-heading duplication"
    fi
  fi

  echo
  echo "Doc graph validation checks: $checks_run"
  if [[ "$failures" -gt 0 ]]; then
    echo "Doc graph validation FAILED: $failures issue(s)." >&2
    exit 1
  fi

  echo "Doc graph validation PASSED."
}

main "$@"
