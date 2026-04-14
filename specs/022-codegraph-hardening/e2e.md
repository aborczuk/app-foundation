# E2E Testing Pipeline: CodeGraph Reliability Hardening

Validates the local CodeGraph/Kuzu health and recovery surface end-to-end, including the doctor flow, recovery guidance, safe refresh/rebuild behavior, malformed-input handling, and timeout-budget checks.

---

## Prerequisites

- `config.yaml`: `.codegraphcontext/config.yaml`
- `uv` is installed and can run repo-local Python commands
- `scripts/cgc_doctor.sh` is executable
- `scripts/cgc_safe_index.sh` can run scoped indexing for `src/mcp_codebase`, `scripts`, and `tests`

---

## Recommended Pipeline (Run This)

Use the pipeline script instead of manual commands:

```bash
# Full E2E flow
scripts/e2e_022_codegraph_hardening.sh full .codegraphcontext/config.yaml

# Preflight only (dry-run, no external deps needed beyond the app)
scripts/e2e_022_codegraph_hardening.sh preflight .codegraphcontext/config.yaml

# Run specific user story section
scripts/e2e_022_codegraph_hardening.sh run .codegraphcontext/config.yaml

# Print verification commands
scripts/e2e_022_codegraph_hardening.sh verify .codegraphcontext/config.yaml

# CI-safe non-interactive checks only
scripts/e2e_022_codegraph_hardening.sh ci .codegraphcontext/config.yaml
```

---

## Section 1: Preflight (Dry-Run Smoke Test)

**Purpose**: Validate the repo can run the health harness and the current feature docs are internally consistent.
**External deps**: None.

1. Run the health contract tests against healthy fixtures.
   - Verify: `uv run pytest tests/unit/test_health.py tests/integration/test_codegraph_health.py -q`
   - Good looks like: healthy fixtures report `healthy` and the doctor contract matches the shared classifier.

**Pass criteria**: The health smoke checks pass without mutating the repository state.

---

## Section 2: User Story 1 - Graph Health Check for Developers (Priority: P1)

**Purpose**: Validate the developer-facing health command distinguishes healthy, stale, locked, and unreadable graph states.
**External deps**: None beyond repo-local Python.

**User asks before starting**:
- [ ] `.codegraphcontext/config.yaml` is present
- [ ] `uv` can run repo-local pytest

**Steps**:
1. Run the shared health classifier and doctor contract tests.
   - Verify: `uv run pytest tests/unit/test_health.py tests/integration/test_codegraph_health.py -q`
2. Confirm the doctor CLI returns a non-zero exit code for stale/unhealthy fixtures.
   - Verify: the integration tests assert the exit code and recovery hint id.

**Pass criteria**: Healthy and unhealthy states are distinct, and the doctor / MCP contract agree on the same recovery hint.

---

## Section 3: User Story 2 - Agent-Facing Recovery on Lock/Query Failure (Priority: P1)

**Purpose**: Validate the agent-facing recovery path distinguishes lock contention, unreadable state, malformed input, missing symbols, and real query failures.
**External deps**: None beyond repo-local Python.

**User asks before starting**:
- [ ] `.codegraphcontext/config.yaml` is present
- [ ] `uv` can run repo-local pytest

**Steps**:
1. Run the recovery matrix and query-tool validation tests.
   - Verify: `uv run pytest tests/integration/test_codegraph_recovery.py::test_lock_and_query_failure_modes tests/unit/test_query_tools.py -q`
2. Confirm malformed input returns validation errors while hover transport failure returns a dedicated query-failure code.
   - Verify: the unit tests assert `INVALID_ARGUMENT`, `SYMBOL_NOT_FOUND`, and `QUERY_FAILED` as distinct outcomes.

**Pass criteria**: Lock contention, unreadable graph state, malformed input, missing symbols, and real query failures all surface distinct guidance.

---

## Section 4: User Story 3 - Safe Refresh and Rebuild (Priority: P2)

**Purpose**: Validate that local edits invalidate the graph, refresh restores health, and the last known good snapshot remains usable.
**External deps**: None beyond repo-local Python.

**User asks before starting**:
- [ ] `.codegraphcontext/config.yaml` is present
- [ ] `uv` can run repo-local pytest

**Steps**:
1. Run the refresh/rebuild regression test.
   - Verify: `uv run pytest tests/integration/test_codegraph_recovery.py::test_local_edit_invalidates_then_refresh_restores_health -q`
2. Confirm the healthy → stale → healthy cycle is deterministic.
   - Verify: the test asserts stale detection after a local edit and healthy recovery after refresh.

**Pass criteria**: The graph fails gracefully after local edits, and a refresh returns it to a healthy state without losing the prior usable snapshot.

---

## Section Final: Full Feature E2E

**Purpose**: Validate all user stories work together end-to-end and the repo-level health gate remains usable after the full recovery matrix runs.
**Runs**: After all stories are implemented, and after every significant change.

**User asks before starting**:
- [ ] All per-story E2E sections have passed at least once
- [ ] `.codegraphcontext/config.yaml` is present

**Steps**:
1. Run preflight.
2. Run US1, US2, and US3 sections.
3. Refresh the touched codegraph scopes with the safe index wrapper.
4. Verify the live doctor command reports `healthy` on the repository root.
5. Run the full regression suite across health, recovery, query-tools, and story acceptance tests.
6. Validate the task ledger and task file format.

**Pass criteria**: All automated gates pass, the doctor command reports healthy after refresh, and the full regression suite completes without stale or ambiguous recovery signals.

---

## Verification Commands

```bash
scripts/cgc_doctor.sh --json --project-root ./
uv run pytest tests/unit/test_health.py tests/unit/test_query_tools.py tests/integration/test_codegraph_health.py tests/integration/test_codegraph_recovery.py -q
uv run python scripts/task_ledger.py validate --file .speckit/task-ledger.jsonl
uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file specs/022-codegraph-hardening/tasks.md --json
```

---

## Common Blockers

- **Config missing**: `.codegraphcontext/config.yaml` does not exist. Fix: create the repo-local config file or restore it from the checkout.
- **Doctor unhealthy after refresh**: Symptom: `scripts/cgc_doctor.sh --json --project-root .` reports stale/locked/unavailable. Fix: run `scripts/cgc_safe_index.sh src/mcp_codebase`, `scripts/cgc_safe_index.sh scripts`, and `scripts/cgc_safe_index.sh tests`, then rerun the doctor check.
- **Query failure collapse**: Symptom: malformed input or a transport failure gets reported as `SYMBOL_NOT_FOUND`. Fix: ensure the query-tool contract is returning `INVALID_ARGUMENT` and `QUERY_FAILED` distinctly.

<!-- E2E Run: PASS | 2026-04-14 | full | preflight + story1 + story2 + story3 + final passed -->
