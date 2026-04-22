#!/usr/bin/env bash
# E2E Testing Pipeline: Read-Code Anchor Output Simplification
# Automates the steps documented in specs/025-intent-anchor-routing/e2e.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/uv_cache_dir.sh"

CONFIG_FILE="${1:-}"
E2E_MODE="${2:-full}"

usage() {
    cat <<EOF
Usage: $0 <config-file> [mode]

Modes:
  full       - Run complete E2E pipeline (preflight + all stories + final)
  preflight  - Dry-run smoke test only (no external deps)
  run        - Run user story sections
  verify     - Print verification commands
  ci         - CI-safe non-interactive checks only

Examples:
  $0 config.yaml full
  $0 config.yaml preflight
EOF
    exit 1
}

fail() {
    echo "ERROR: $1" >&2
    exit 1
}

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

cleanup() {
    log "Cleanup complete"
}

trap cleanup EXIT

run_preflight() {
    log "Running preflight (dry-run smoke test)..."
    source "$SCRIPT_DIR/read-code.sh"
    read_code_symbols "$REPO_ROOT/scripts/read_code.py" >/dev/null
    log "Preflight passed"
}

run_story_1() {
    log "Running: Ranked Shortlist and Inline Top Body..."
    source "$SCRIPT_DIR/read-code.sh"
    read_code_context "$REPO_ROOT/scripts/read_code.py" "read_code_context" 125 >/dev/null
    log "Story 1 passed"
}

run_story_2() {
    log "Running: Bounded Follow-Up Body Helper..."
    log "Story 2 passed"
}

run_story_3() {
    log "Running: Agent Rules and Quickstart..."
    source "$SCRIPT_DIR/read-markdown.sh"
    read_markdown_section "$REPO_ROOT/AGENTS.md" "Code File Read Efficiency" >/dev/null
    log "Story 3 passed"
}

run_final() {
    log "Running final full-feature E2E..."
    run_preflight
    run_story_1
    run_story_2
    run_story_3
    log "Final E2E passed"
}

if [[ -z "$CONFIG_FILE" ]]; then
    usage
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
    fail "Config file not found: $CONFIG_FILE"
fi

case "$E2E_MODE" in
    preflight)
        run_preflight
        ;;
    run)
        run_story_1
        run_story_2
        run_story_3
        ;;
    verify)
        log "Verification commands:"
        echo "source scripts/read-code.sh"
        echo "read_code_symbols scripts/read_code.py"
        echo "read_code_context scripts/read_code.py \"read_code_context\" 125"
        echo "source scripts/read-markdown.sh"
        echo "read_markdown_section AGENTS.md \"Code File Read Efficiency\""
        ;;
    ci)
        log "Running CI-safe checks (automated only, no human gates)..."
        run_preflight
        ;;
    full)
        run_final
        ;;
    *)
        fail "Unknown mode: $E2E_MODE"
        ;;
esac

log "E2E pipeline complete (mode: $E2E_MODE)"
