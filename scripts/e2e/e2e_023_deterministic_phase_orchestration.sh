#!/usr/bin/env bash
# E2E Testing Pipeline: Deterministic Phase Orchestration
# Automates the checks documented in specs/023-deterministic-phase-orchestration/e2e.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FEATURE_DIR="$REPO_ROOT/specs/023-deterministic-phase-orchestration"
LEDGER_FILE="$REPO_ROOT/.speckit/pipeline-ledger.jsonl"

MODE="full"
CONFIG_FILE=""

if [[ $# -gt 0 ]]; then
    case "$1" in
        preflight|run|verify|ci|full)
            MODE="$1"
            CONFIG_FILE="${2:-}"
            ;;
        *)
            CONFIG_FILE="$1"
            MODE="${2:-full}"
            ;;
    esac
fi

usage() {
    cat <<EOF
Usage: $(basename "$0") [config-file] [mode]
   or: $(basename "$0") [mode]

Modes:
  full       Run preflight + all story sections + final validation
  preflight  Dry-run smoke test only
  run        Run the user-story sections only
  verify     Print verification commands and run lightweight checks
  ci         Non-interactive checks only
EOF
    exit 1
}

fail() {
    echo "ERROR: $1" >&2
    exit 1
}

log() {
    printf '[%s] %s\n' "$(date +'%Y-%m-%d %H:%M:%S')" "$1"
}

require_tools() {
    command -v uv >/dev/null 2>&1 || fail "uv is required"
    command -v python3 >/dev/null 2>&1 || fail "python3 is required"
}

ledger_line_count() {
    python3 - "$LEDGER_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    print(0)
    raise SystemExit(0)

count = 0
with path.open(encoding="utf-8") as fh:
    for line in fh:
        if line.strip():
            count += 1
print(count)
PY
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    if [[ "$haystack" != *"$needle"* ]]; then
        fail "expected output to contain: $needle"
    fi
}

assert_dry_run_no_mutation() {
    local before after output json_line
    before="$(ledger_line_count)"
    output="$(uv run python "$REPO_ROOT/scripts/pipeline_driver.py" --feature-id 023 --dry-run --json)"
    after="$(ledger_line_count)"

    [[ "$before" == "$after" ]] || fail "dry-run mutated the pipeline ledger"
    json_line="$(printf '%s\n' "$output" | tail -n 1)"
    assert_contains "$json_line" '"dry_run_mode": true'
    assert_contains "$json_line" '"ok": true'
    assert_contains "$json_line" '"next_phase": "implement"'
}

assert_invalid_approval_blocks() {
    local before after output status json_line
    before="$(ledger_line_count)"
    set +e
    output="$(uv run python "$REPO_ROOT/scripts/pipeline_driver.py" --feature-id 023 --approval-token invalid --json 2>&1)"
    status=$?
    set -e
    after="$(ledger_line_count)"

    [[ "$before" == "$after" ]] || fail "invalid approval mutated the pipeline ledger"
    [[ "$status" -ne 0 ]] || fail "invalid approval unexpectedly succeeded"
    json_line="$(printf '%s\n' "$output" | tail -n 1)"
    assert_contains "$output" "approval"
    assert_contains "$json_line" '"ok": false'
}

run_preflight() {
    log "Running preflight checks"
    uv run python "$REPO_ROOT/scripts/pipeline_ledger.py" validate
    uv run python "$REPO_ROOT/scripts/speckit_tasks_gate.py" validate-format \
        --tasks-file "$FEATURE_DIR/tasks.md" --json
    uv run python "$REPO_ROOT/scripts/validate_command_script_coverage.py" \
        --canonical-manifest "$REPO_ROOT/command-manifest.yaml" \
        --scaffold-script "$REPO_ROOT/.specify/scripts/pipeline-scaffold.py" \
        --bash-scripts-dir "$REPO_ROOT/.specify/scripts/bash" \
        --json
    assert_dry_run_no_mutation
    log "Preflight passed"
}

run_story_1() {
    log "Running story 1: deterministic completion"
    assert_dry_run_no_mutation
    log "Story 1 passed"
}

run_story_2() {
    log "Running story 2: permissioned start"
    local before after output first_line second_line
    before="$(ledger_line_count)"
    output="$(uv run python - "$REPO_ROOT/scripts/pipeline_driver.py" <<'PY'
import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

module_path = Path(sys.argv[1])
sys.path.insert(0, str(module_path.parent))
spec = spec_from_file_location("pipeline_driver", module_path)
module = module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

configured = {
    "steps": {
        "solution": {
            "enabled": True,
            "required_scope": "approved",
        }
    }
}

blocked_with_token = module.enforce_approval_breakpoint(
    "solution",
    approval_token="invalid",
    breakpoint_config=configured,
    correlation_id="e2e:023:approval-token",
)
blocked_without_token = module.enforce_approval_breakpoint(
    "solution",
    approval_token=None,
    breakpoint_config=configured,
    correlation_id="e2e:023:approval-missing",
)
print(json.dumps(blocked_with_token, sort_keys=True))
print(json.dumps(blocked_without_token, sort_keys=True))
PY
    )"
    after="$(ledger_line_count)"

    [[ "$before" == "$after" ]] || fail "approval helper mutated the pipeline ledger"
    first_line="$(printf '%s\n' "$output" | sed -n '1p')"
    second_line="$(printf '%s\n' "$output" | sed -n '2p')"
    assert_contains "$first_line" '"ok": false'
    assert_contains "$first_line" '"gate": "approval_required"'
    assert_contains "$first_line" '"approval_token_scope_mismatch"'
    assert_contains "$second_line" '"ok": false'
    assert_contains "$second_line" '"breakpoint_scope:approved"'
    log "Story 2 passed"
}

run_story_3() {
    log "Running story 3: producer-only command contracts"
    uv run python "$REPO_ROOT/scripts/validate_markdown_doc_shapes.py" \
        --file "$REPO_ROOT/.claude/commands/speckit.solution.md" \
        --shape auto \
        --json
    uv run python "$REPO_ROOT/scripts/validate_command_script_coverage.py" \
        --canonical-manifest "$REPO_ROOT/command-manifest.yaml" \
        --scaffold-script "$REPO_ROOT/.specify/scripts/pipeline-scaffold.py" \
        --bash-scripts-dir "$REPO_ROOT/.specify/scripts/bash" \
        --json
    log "Story 3 passed"
}

run_final() {
    log "Running full feature E2E"
    run_preflight
    run_story_1
    run_story_2
    run_story_3
    uv run python "$REPO_ROOT/scripts/pipeline_ledger.py" validate
    log "Final E2E passed"
}

print_verification_commands() {
    cat <<EOF
uv run python scripts/pipeline_ledger.py validate
uv run python scripts/pipeline_ledger.py validate-manifest
uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file specs/023-deterministic-phase-orchestration/tasks.md --json
uv run python scripts/validate_command_script_coverage.py --canonical-manifest command-manifest.yaml --scaffold-script .specify/scripts/pipeline-scaffold.py --bash-scripts-dir .specify/scripts/bash --json
uv run python scripts/pipeline_driver.py --feature-id 023 --dry-run --json
EOF
}

if [[ -z "$CONFIG_FILE" ]]; then
    log "No config file supplied; using local-only E2E checks."
elif [[ ! -f "$CONFIG_FILE" ]]; then
    fail "Config file not found: $CONFIG_FILE"
fi

require_tools

case "$MODE" in
    preflight)
        run_preflight
        ;;
    run)
        run_story_1
        run_story_2
        run_story_3
        ;;
    verify)
        print_verification_commands
        run_preflight
        ;;
    ci)
        run_preflight
        run_story_1
        run_story_2
        run_story_3
        ;;
    full)
        run_final
        ;;
    *)
        usage
        ;;
esac

log "E2E pipeline complete (mode: $MODE)"
