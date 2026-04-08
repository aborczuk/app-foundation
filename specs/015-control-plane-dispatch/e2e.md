# E2E Testing Pipeline: ClickUp + n8n Operational Control Plane — Phase 1

This pipeline validates end-to-end dispatch behavior for Phase 1: webhook intake, signature/policy enforcement, idempotent dedupe, single-active-run guard, stale-event and action-scope rejection, and operator-visible outcome updates.

---

## Prerequisites

- Python 3.12 environment with dependencies installed (`uv sync --group dev`).
- E2E env config file (KEY=VALUE) that sets required runtime env vars (default path used by script: `specs/015-control-plane-dispatch/e2e.env`).
- Required env vars (names only, no secret values):
  - `CLICKUP_API_TOKEN`
  - `CLICKUP_WEBHOOK_SECRET`
  - `CONTROL_PLANE_ALLOWLIST`
  - `N8N_DISPATCH_BASE_URL`
  - Optional: `CONTROL_PLANE_HOST`, `CONTROL_PLANE_PORT`, `CONTROL_PLANE_DB_PATH`
- Adopted dependency availability:
  - ClickUp API reachable and token valid.
  - n8n dispatch base URL reachable.

---

## Recommended Pipeline (Run This)

Use the pipeline script instead of manual commands:

```bash
# Full E2E flow
scripts/e2e_015_control_plane_dispatch.sh full specs/015-control-plane-dispatch/e2e.env

# Preflight only (dry-run + dependency checks)
scripts/e2e_015_control_plane_dispatch.sh preflight specs/015-control-plane-dispatch/e2e.env

# Run interactive user-story section(s)
scripts/e2e_015_control_plane_dispatch.sh run specs/015-control-plane-dispatch/e2e.env

# Print verification commands and run lightweight checks
scripts/e2e_015_control_plane_dispatch.sh verify specs/015-control-plane-dispatch/e2e.env

# CI-safe non-interactive checks only
scripts/e2e_015_control_plane_dispatch.sh ci specs/015-control-plane-dispatch/e2e.env
```

---

## Section 1: Preflight (Dry-Run Smoke Test)

**Purpose**: Validate toolchain, env wiring, and adopted dependency reachability before story execution.
**External deps**: ClickUp API + n8n endpoint reachability checks only.

1. Validate required tools and env file.
   - Verify: `uv`/`python`, `pytest`, `curl`, and env file are available.
2. Load temp env (no live config mutation) with temp DB path.
   - Verify: temp env + temp DB path are printed.
3. Validate ClickUp dependency.
   - Verify: `GET /api/v2/user` returns `200` with provided token.
4. Validate n8n dependency.
   - Verify: endpoint host is reachable (HTTP status not `000`).
5. Collect control-plane tests.
   - Verify: `pytest --collect-only` for contract/unit/integration paths exits `0`.

**Pass criteria**: All preflight checks pass.

---

## Section 2: User Story 1 - Trigger Agent Workflow from Task Status Change (Priority: P1)

**Purpose**: Validate dispatch behavior and guards for signature, scope, metadata, duplicate, active-run, stale-event, schema mismatch, and action-scope outcomes.
**External deps**: ClickUp API, n8n endpoint.

**User asks before starting**:
- [ ] ClickUp workspace has an allowlisted task ready for status-trigger testing.
- [ ] n8n workflow route for the configured `workflow_type` is active.
- [ ] Control-plane env vars in the selected env file are correct.

**Steps**:
1. Run automated contract + unit + integration tests for the control plane.
   - Verify: test command exits `0`.
2. Enforce lifecycle/process safety gates.
   - Verify: no loop/lifecycle error patterns in run output; no new orphan control-plane processes remain after section cleanup.
3. Enforce state-safety and transaction-integrity gates.
   - Verify: deterministic SQLite assertions pass (no duplicate processed events, no orphan active runs, no impossible local lifecycle transitions, no partial-write signatures).
4. Timestamp-gated evidence check.
   - Verify: test artifact and DB file updates occurred after section start timestamp.
5. Live operator verification (required).
   - **Human verify (required)**: move a ClickUp task to trigger status, observe exactly one n8n dispatch, and confirm a visible operator-safe outcome update on the same task.
   - Reason manual is required: production ClickUp UI state transitions and n8n workflow execution visibility are external-system behaviors that cannot be asserted deterministically in this script without environment-specific fixtures.

**Pass criteria**: All automated gates pass and required human verification is confirmed.

---

## Section Final: Full Feature E2E

**Purpose**: Validate full Phase 1 behavior in one end-to-end run with both automated and live external checks.
**Runs**: After US1 section is passing and before merge/release.

**User asks before starting**:
- [ ] Section 1 (Preflight) has passed.
- [ ] Section 2 (US1) automated checks have passed at least once.
- [ ] ClickUp + n8n dependencies are currently healthy.

**Steps**:
1. Run preflight.
2. Run US1 automated checks.
3. Run cross-section lightweight verification checks.
   - Verify: no orphan control-plane process drift, env/dependency checks still pass, DB invariants remain valid.
4. Perform final external-system verification.
   - **Human verify (required)**: confirm final outcome visibility in ClickUp and expected n8n run behavior for the tested trigger.
   - Reason manual is required: final acceptance depends on external UI/workflow evidence beyond deterministic local test oracles.

**Pass criteria**: All automated gates pass and required human verification passes.

---

## Verification Commands

```bash
# Script-level verification
scripts/e2e_015_control_plane_dispatch.sh verify specs/015-control-plane-dispatch/e2e.env

# Core test suites
uv run pytest tests/contract/test_clickup_control_plane_contract.py -q
uv run pytest tests/unit/clickup_control_plane -q
uv run pytest tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q

# Optional local DB inspection
sqlite3 .speckit/control-plane.db ".tables"
sqlite3 .speckit/control-plane.db "select count(*) from processed_events;"
sqlite3 .speckit/control-plane.db "select count(*) from active_task_runs where state='running';"

# Service run helper
uv run uvicorn clickup_control_plane.app:app --port 8090
```

---

## Common Blockers

- **Invalid ClickUp token**: Symptom: preflight ClickUp check returns `401`. Fix: update `CLICKUP_API_TOKEN`.
- **n8n endpoint unreachable**: Symptom: `curl` returns status `000`. Fix: correct `N8N_DISPATCH_BASE_URL`, DNS, or network route.
- **Missing env vars**: Symptom: preflight fails required-var checks. Fix: add all required keys to env file.
- **No allowlisted task metadata**: Symptom: dispatch rejected as out-of-scope/missing metadata. Fix: set allowlisted scope and required routing fields.
- **Lifecycle errors in async paths**: Symptom: output includes loop/pending-task warnings. Fix: resolve async shutdown/cancel ownership before rerun.
- **State drift/transaction failures**: Symptom: DB invariant checks fail (active orphan runs, duplicate/partial records). Fix: repair reconciliation/transaction handling before rerun.

<!-- E2E Run: PASS | 2026-04-03 | run (US1 section) | Automated gates passed and manual verification confirmed -->
