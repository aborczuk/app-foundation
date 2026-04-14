#!/usr/bin/env bash
# E2E Testing Pipeline: CodeGraph Reliability Hardening
# Automates the steps documented in e2e.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FEATURE_DIR="$REPO_ROOT/specs/022-codegraph-hardening"
FEATURE_NAME="CodeGraph Reliability Hardening"
FEATURE_SLUG="022_codegraph_hardening"
DEFAULT_CONFIG="$REPO_ROOT/.codegraphcontext/config.yaml"

CONFIG_FILE=""
E2E_MODE="full"

usage() {
    cat <<EOF
Usage: $0 <config-file> [mode]
   or: $0 <mode> [config-file]

Modes:
  full       - Run complete E2E pipeline (preflight + all stories + final)
  preflight  - Dry-run smoke test only (no external deps)
  run        - Run user story sections
  verify     - Print verification commands
  ci         - CI-safe non-interactive checks only

Examples:
  $0 .codegraphcontext/config.yaml full
  $0 full .codegraphcontext/config.yaml
  $0 preflight
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

append_summary() {
    local status="$1"
    local scope="$2"
    local details="$3"
    local stamp
    stamp="$(date -u +'%Y-%m-%d')"
    printf '\n<!-- E2E Run: %s | %s | %s | %s -->\n' "$status" "$stamp" "$scope" "$details" >> "$FEATURE_DIR/e2e.md"
}

cleanup() {
    rm -rf "$TMP_DIR"
    log "Cleanup complete"
}

TMP_DIR="$(mktemp -d)"
trap cleanup EXIT

run_pytest() {
    uv run pytest "$@" -q
}

run_ledger_validate() {
    uv run python scripts/task_ledger.py validate --file .speckit/task-ledger.jsonl
}

run_tasks_validate() {
    uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file "$FEATURE_DIR/tasks.md" --json
}

run_doctor_healthy_check() {
    local out_file="$TMP_DIR/doctor.json"
    scripts/cgc_doctor.sh --json --project-root "$REPO_ROOT" >"$out_file"
    uv run python -c 'import json, pathlib, sys; data = json.loads(pathlib.Path(sys.argv[1]).read_text()); assert data["status"] == "healthy", data' "$out_file"
}

run_safe_index_refresh() {
    scripts/cgc_safe_index.sh src/mcp_codebase
    scripts/cgc_safe_index.sh scripts
    scripts/cgc_safe_index.sh tests
}

run_preflight() {
    log "Running preflight (dry-run smoke test)..."
    test -f "$CONFIG_FILE" || fail "Config file not found: $CONFIG_FILE"
    run_pytest tests/unit/test_health.py tests/integration/test_codegraph_health.py
    log "Preflight passed"
}

run_story_1() {
    log "Running User Story 1: Graph Health Check for Developers..."
    run_pytest tests/unit/test_health.py tests/integration/test_codegraph_health.py
    log "User Story 1 passed"
}

run_story_2() {
    log "Running User Story 2: Agent-Facing Recovery on Lock/Query Failure..."
    run_pytest tests/integration/test_codegraph_recovery.py::test_lock_and_query_failure_modes tests/unit/test_query_tools.py
    log "User Story 2 passed"
}

run_story_3() {
    log "Running User Story 3: Safe Refresh and Rebuild..."
    run_pytest tests/integration/test_codegraph_recovery.py::test_local_edit_invalidates_then_refresh_restores_health
    log "User Story 3 passed"
}

run_final() {
    log "Running final full-feature E2E..."
    run_preflight
    run_story_1
    run_story_2
    run_story_3
    run_safe_index_refresh
    run_doctor_healthy_check
    run_pytest \
        tests/unit/test_health.py \
        tests/unit/test_query_tools.py \
        tests/integration/test_codegraph_health.py \
        tests/integration/test_codegraph_recovery.py \
        .speckit/acceptance-tests/story-1.py \
        .speckit/acceptance-tests/story-2.py \
        .speckit/acceptance-tests/story-3.py
    run_ledger_validate
    run_tasks_validate
    log "Final E2E passed"
}

run_verify() {
    log "Verification commands:"
    echo "  scripts/cgc_doctor.sh --json --project-root \"$REPO_ROOT\""
    echo "  uv run pytest tests/unit/test_health.py tests/unit/test_query_tools.py tests/integration/test_codegraph_health.py tests/integration/test_codegraph_recovery.py -q"
    echo "  uv run python scripts/task_ledger.py validate --file .speckit/task-ledger.jsonl"
    echo "  uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file specs/022-codegraph-hardening/tasks.md --json"
}

parse_args() {
    local first="${1:-}"
    local second="${2:-}"

    if [[ -z "$first" ]]; then
        usage
    fi

    case "$first" in
        preflight|run|verify|ci|full|US1|US2|US3|Section|section|1|2|3)
            E2E_MODE="$first"
            if [[ "$first" == "Section" || "$first" == "section" ]]; then
                E2E_MODE="Section ${second:-}"
                CONFIG_FILE="${3:-$DEFAULT_CONFIG}"
            else
                CONFIG_FILE="${second:-$DEFAULT_CONFIG}"
            fi
            ;;
        *)
            CONFIG_FILE="$first"
            E2E_MODE="${second:-full}"
            ;;
    esac
}

main() {
    parse_args "${1:-}" "${2:-}"

    if [[ ! -f "$CONFIG_FILE" ]]; then
        fail "Config file not found: $CONFIG_FILE"
    fi

    case "$E2E_MODE" in
        preflight)
            run_preflight
            append_summary "PASS" "preflight" "dry-run smoke checks passed"
            ;;
        US1|1|Section\ 1|section\ 1)
            run_story_1
            append_summary "PASS" "US1" "graph health checks passed"
            ;;
        US2|2|Section\ 2|section\ 2)
            run_story_2
            append_summary "PASS" "US2" "recovery and query-failure checks passed"
            ;;
        US3|3|Section\ 3|section\ 3)
            run_story_3
            append_summary "PASS" "US3" "refresh/rebuild recovery checks passed"
            ;;
        run)
            run_story_1
            run_story_2
            run_story_3
            append_summary "PASS" "run" "all user story sections passed"
            ;;
        verify)
            run_verify
            append_summary "PASS" "verify" "verification commands printed"
            ;;
        ci)
            run_preflight
            run_story_1
            run_story_2
            run_story_3
            run_doctor_healthy_check
            run_ledger_validate
            run_tasks_validate
            append_summary "PASS" "ci" "automation-only checks passed"
            ;;
        full)
            run_final
            append_summary "PASS" "full" "preflight + story1 + story2 + story3 + final passed"
            ;;
        *)
            fail "Unknown mode: $E2E_MODE"
            ;;
    esac

    log "E2E pipeline complete (mode: $E2E_MODE)"
}

main "$@"
