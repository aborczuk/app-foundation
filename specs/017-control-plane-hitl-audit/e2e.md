# E2E Testing Pipeline: ClickUp + n8n Operational Control Plane — Phase 3 HITL + Lifecycle Auditability

This pipeline validates Phase 3 end-to-end behavior: pause for human input, resume via operator response convention, timeout to blocked state, manual operator cancel handling, and chronological lifecycle visibility across multiple runs.

---

## Prerequisites

- Python 3.12 environment with dependencies installed (`uv sync --group dev`).
- E2E env config file (KEY=VALUE) for this feature (script default: `specs/017-control-plane-hitl-audit/e2e.env`).
- Required env vars (names only, no secret values):
  - `CLICKUP_API_TOKEN`
  - `CLICKUP_WEBHOOK_SECRET`
  - `CONTROL_PLANE_ALLOWLIST`
  - `N8N_DISPATCH_BASE_URL`
  - `CONTROL_PLANE_COMPLETION_TOKEN`
  - Optional: `CONTROL_PLANE_HOST`, `CONTROL_PLANE_PORT`, `CONTROL_PLANE_DB_PATH`
  - Optional status overrides: `CONTROL_PLANE_HITL_WAITING_STATUS`, `CONTROL_PLANE_HITL_BLOCKED_STATUS`
- Adopted dependency availability:
  - ClickUp API reachable and token valid.
  - n8n dispatch base URL reachable and workflow routes active (`/control-plane/build-spec`, `/control-plane/qa-loop`, `/control-plane/cancel-run`).

---

## Recommended Pipeline (Run This)

Use the pipeline script instead of manual commands:

```bash
# Full E2E flow
scripts/e2e_017_control_plane_hitl_audit.sh full specs/017-control-plane-hitl-audit/e2e.env

# Preflight only (dry-run, non-destructive checks)
scripts/e2e_017_control_plane_hitl_audit.sh preflight specs/017-control-plane-hitl-audit/e2e.env

# Run user-story sections (interactive/manual gates where required)
scripts/e2e_017_control_plane_hitl_audit.sh run specs/017-control-plane-hitl-audit/e2e.env

# Print verification commands and run lightweight checks
scripts/e2e_017_control_plane_hitl_audit.sh verify specs/017-control-plane-hitl-audit/e2e.env

# CI-safe non-interactive checks only (no manual gates)
scripts/e2e_017_control_plane_hitl_audit.sh ci specs/017-control-plane-hitl-audit/e2e.env
```

---

## Section 1: Preflight (Dry-Run Smoke Test)

**Purpose**: Validate toolchain, config/env, and adopted dependency reachability before any story flow.
**External deps**: ClickUp + n8n reachability checks only.

1. Validate required tools and env file.
   - Verify: `uv`/`python`, `pytest`, `curl`, and env file are available.
2. Load temp env workspace and temp DB path (no live config mutation).
   - Verify: temp DB path is printed and under temp workspace.
3. Validate required runtime env vars are present and non-placeholder.
   - Verify: required key checks pass.
4. Validate adopted dependency availability.
   - Verify: ClickUp API user endpoint returns `200`; n8n base endpoint is reachable (HTTP status not `000`).
5. Collect E2E-relevant pytest targets.
   - Verify: collection exits `0`.

**Pass criteria**: All checks pass.

---

## Section 2: User Story 1 - Human-in-the-Loop Pause and Resume (Priority: P1)

**Purpose**: Validate wait-for-input, operator response resume, timeout-to-blocked, and cleanup invariants.
**External deps**: ClickUp API, n8n endpoint.

**User asks before starting**:
- [ ] ClickUp has a test task in an allowlisted scope with workflow metadata.
- [ ] n8n routes for build/qa are active and reachable.
- [ ] Completion callback token in env matches runner setup.

**Steps**:
1. Run automated US1 tests (contract/unit/integration).
   - Verify: test command exits `0`.
2. Enforce async lifecycle gates.
   - Verify: no loop/lifecycle error strings in output (`event loop is already running`, pending-task destruction warnings).
3. Enforce deterministic state-safety and transaction-integrity assertions.
   - Verify: no orphan active runs; no duplicate processed events; no partial/impossible lifecycle state residue.
4. Timestamp-gated evidence checks.
   - Verify: section artifacts (logs/DB) were written after section start timestamp.
5. Manual external-system gate.
   - **Human verify (required)**: run one live wait/resume cycle in ClickUp (`HITL_RESPONSE:` comment) and confirm operator-visible outcome + resumed dispatch.
   - Reason manual is required: live ClickUp UI interaction and external n8n execution trace are environment-specific and not deterministically assertable from this local script.

**Pass criteria**: All automated gates pass and manual verification is confirmed.

---

## Section 3: User Story 2 - Lifecycle Visibility + Manual Cancel (Priority: P2)

**Purpose**: Validate operator manual cancel behavior, cancellation recording, and lifecycle visibility safeguards.
**External deps**: ClickUp API, n8n endpoint.

**User asks before starting**:
- [ ] A test task currently has an active control-plane run candidate.
- [ ] n8n cancel route (`/control-plane/cancel-run`) is active.
- [ ] ClickUp status set allows controlled -> non-controlled transition test.

**Steps**:
1. Run automated US2 tests (integration/unit).
   - Verify: test command exits `0`.
2. Enforce async lifecycle + cleanup gates.
   - Verify: no loop/lifecycle error strings and no orphan control-plane process drift after section.
3. Enforce deterministic state-safety and transaction-integrity assertions.
   - Verify: active run lock is released after cancel paths; no unresolved local active drift; no partial lifecycle persistence residues.
4. Manual external-system gate.
   - **Human verify (required)**: move task status from controlled to non-controlled while active and confirm cancel signal behavior and visible task outcome.
   - Reason manual is required: external status transition timing and UI-visible cancellation evidence cannot be fully asserted deterministically in this script.

**Pass criteria**: All automated gates pass and manual verification is confirmed.

---

## Section Final: Full Feature E2E

**Purpose**: Validate combined Phase 3 behavior across stories and cross-story lifecycle continuity.
**Runs**: After both user-story sections pass.

**User asks before starting**:
- [ ] Section 1 and Section 2 have passed at least once.
- [ ] External dependencies (ClickUp + n8n) are healthy.

**Steps**:
1. Run preflight.
2. Run US1 section (automated + manual gate).
3. Run US2 section (automated + manual gate).
4. Run cross-story deterministic checks.
   - Verify: no orphan active runs and no transaction/state safety violations in local advisory DB.
5. Final manual acceptance gate.
   - **Human verify (required)**: confirm lifecycle history remains readable and chronological on target task(s) after multiple runs.
   - Reason manual is required: final chronology acceptance is based on external ClickUp operator timeline rendering.

**Pass criteria**: All automated checks pass and all required manual gates pass.

---

## Verification Commands

```bash
# Script-level verification
scripts/e2e_017_control_plane_hitl_audit.sh verify specs/017-control-plane-hitl-audit/e2e.env

# Core test suites
uv run pytest tests/contract/test_clickup_control_plane_contract.py -q
uv run pytest tests/unit/clickup_control_plane -q
uv run pytest tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q

# Optional local DB inspection
sqlite3 .speckit/control-plane.db ".tables"
sqlite3 .speckit/control-plane.db "select count(*) from processed_events;"
sqlite3 .speckit/control-plane.db "select count(*) from active_task_runs where state='running';"
sqlite3 .speckit/control-plane.db "select count(*) from paused_task_runs;"
```

---

<!-- E2E Run: BLOCKED | 2026-04-05 | US1 | prerequisites missing: e2e.env, CLICKUP_API_TOKEN, CLICKUP_WEBHOOK_SECRET, CONTROL_PLANE_ALLOWLIST, N8N_DISPATCH_BASE_URL, CONTROL_PLANE_COMPLETION_TOKEN -->
<!-- E2E Run: BLOCKED | 2026-04-05 | US2 | same prerequisites missing: e2e.env and env vars not set; n8n not available; manual human gate required -->

## Common Blockers

- **Completion callback token mismatch**: Symptom: `401 invalid_completion_token`. Fix: align `CONTROL_PLANE_COMPLETION_TOKEN` across caller and service.
- **Malformed waiting_input payload**: Symptom: `400 invalid_payload`. Fix: include `run_id` and `human_input_request`.
- **Operator response not detected**: Symptom: resume not triggered. Fix: use `HITL_RESPONSE: <text>` exactly with non-empty body.
- **Manual cancel not triggered**: Symptom: task move ignored. Fix: ensure transition is controlled -> non-controlled in webhook history.
- **n8n unreachable**: Symptom: HTTP `000` or dispatch failures. Fix: verify `N8N_DISPATCH_BASE_URL`, route activation, network path.
- **State/transaction gate failure**: Symptom: orphan active runs or duplicate processed events. Fix: resolve reconciliation/transaction handling before rerun.
