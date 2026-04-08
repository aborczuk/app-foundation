# Tasks: ClickUp + n8n Operational Control Plane — Phase 3: Human-in-the-Loop & Lifecycle Auditability

**Input**: Design documents from `/specs/017-control-plane-hitl-audit/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/hitl-lifecycle-contract.md`, `quickstart.md`  
**Skills**: Reuse existing `src/clickup_control_plane` service/state/dispatcher patterns before introducing new abstractions.

**Tests**: Mandatory by constitution and spec scope; write/expand tests before implementation changes where feasible.

**Organization**: Tasks are grouped by user story so each story is independently implementable and testable.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm ingress/runtime readiness and baseline config contracts before story implementation.

- [x] T000 Validate External Ingress + Runtime Readiness Gate and record pass evidence in /Users/andreborczuk/ib-trading/specs/017-control-plane-hitl-audit/tasks.md
- [x] T001 [P] Verify and document HITL runtime env keys in /Users/andreborczuk/ib-trading/src/clickup_control_plane/config.py
- [x] T002 [P] Validate completion callback and HITL contract shape against design docs in /Users/andreborczuk/ib-trading/specs/017-control-plane-hitl-audit/contracts/hitl-lifecycle-contract.md

**T000 Gate Evidence (2026-04-04)**:
| Check | Status | Evidence |
|-------|--------|---------|
| Ingress strategy selected and owner documented | ✅ Pass | Production ingress: `https://67.205.175.182.nip.io/control-plane/*`; local fallback `http://localhost:8090/control-plane/*` |
| Endpoint contract path and auth defined | ✅ Pass | `POST /control-plane/clickup/webhook` (ClickUp HMAC-SHA256) + `POST /control-plane/workflow/completion` (X-Completion-Token) |
| Runtime entrypoint readiness probe | ✅ Pass | `curl -s https://67.205.175.182.nip.io/control-plane/health` → `200 {"status":"ok"}` |
| Secret lifecycle defined | ✅ Pass | `CLICKUP_WEBHOOK_SECRET`, `CLICKUP_API_TOKEN`, `CONTROL_PLANE_COMPLETION_TOKEN` loaded from env only; no code/commit exposure |
| External dependency readiness | ✅ Pass | ClickUp webhook → `/control-plane/clickup/webhook`; n8n routes active: `/build-spec`, `/qa-loop`, `/cancel-run` |
| Evidence links recorded | ✅ Pass | Full runbook in `specs/016-control-plane-qa-loop/quickstart.md`; validated during 017 implementation phase |

**Checkpoint**: Ingress/runtime gate is explicit and completion/HITL runtime contracts are unambiguous.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core async/state/transaction safeguards that block all user stories until complete.

**CRITICAL**: No user story work starts until this phase is complete.

- [x] T003 Implement paused-run persistence schema and APIs in /Users/andreborczuk/ib-trading/src/clickup_control_plane/state_store.py
- [x] T004 [P] Implement idempotent processed-event insert/update helpers for non-dispatch paths in /Users/andreborczuk/ib-trading/src/clickup_control_plane/state_store.py
- [x] T005 Implement resume and cancel transport paths in /Users/andreborczuk/ib-trading/src/clickup_control_plane/dispatcher.py
- [x] T006 [P] Implement operator-safe lifecycle outcome rendering for resumed/cancelled/timeout decisions in /Users/andreborczuk/ib-trading/src/clickup_control_plane/clickup_client.py
- [x] T007 Implement source-of-truth reconciliation ordering between ClickUp lifecycle and local advisory state in /Users/andreborczuk/ib-trading/src/clickup_control_plane/service.py
- [x] T008 Implement explicit transaction-boundary safeguards (commit/rollback, no partial writes) for paused-run and processed-event flows in /Users/andreborczuk/ib-trading/src/clickup_control_plane/state_store.py
- [x] T009 [P] Add foundational rollback/idempotency regression coverage for state-store mutation paths in /Users/andreborczuk/ib-trading/tests/unit/clickup_control_plane/test_state_store.py

**Checkpoint**: Async/state/transaction guardrails are in place and validated before story-specific behavior.

---

## Phase 3: User Story 1 - Human-in-the-Loop Pause and Resume (Priority: P1) 🎯 MVP

**Goal**: Workflow pauses for human input, resumes from valid operator response, and times out visibly to blocked state.

**Independent Test**: Trigger pause (`waiting_input`), submit `HITL_RESPONSE:` operator comment, verify resume dispatch uses paused run context; verify timeout marks task blocked and releases run lock.

### Tests for User Story 1

- [x] T010 [P] [US1] Add schema tests requiring structured `human_input_request` for `waiting_input` in /Users/andreborczuk/ib-trading/tests/unit/clickup_control_plane/test_schemas.py
- [x] T011 [P] [US1] Add completion callback contract acceptance/rejection tests for `waiting_input` payloads in /Users/andreborczuk/ib-trading/tests/contract/test_clickup_control_plane_contract.py
- [x] T012 [P] [US1] Add integration test for wait-to-resume flow using `HITL_RESPONSE:` convention in /Users/andreborczuk/ib-trading/tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py
- [x] T013 [US1] Add running-loop async lifecycle regression (resume path under active event loop) in /Users/andreborczuk/ib-trading/tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py
- [x] T014 [US1] Add timeout-to-blocked integration regression with subsequent re-dispatch eligibility in /Users/andreborczuk/ib-trading/tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py

### Implementation for User Story 1

- [x] T015 [US1] Implement `waiting_input` completion handling, waiting-status update, and paused-run upsert in /Users/andreborczuk/ib-trading/src/clickup_control_plane/app.py
- [x] T016 [US1] Implement operator-response extraction and paused-run resume dispatch orchestration in /Users/andreborczuk/ib-trading/src/clickup_control_plane/service.py
- [x] T017 [US1] Implement timeout handling that sets blocked status and clears advisory state in /Users/andreborczuk/ib-trading/src/clickup_control_plane/app.py
- [x] T018 [US1] Validate no orphan paused-run/active-run records remain after terminal callbacks in /Users/andreborczuk/ib-trading/tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py

**Checkpoint**: US1 is independently functional and testable end-to-end.
<!-- Checkpoint validated: PASS | 2026-04-05 | All 5 claims verified: waiting_input pause+upsert, HITL_RESPONSE resume dispatch, timeout→blocked+re-dispatch, active-loop async guard, no orphan state after terminal callbacks -->

---

## Phase 4: User Story 2 - Workflow Lifecycle Visibility and Auditability (Priority: P2)

**Goal**: Manual status changes cancel active runs, lifecycle outcomes remain visible/safe, and multi-run history remains traceable.

**Independent Test**: With active run in controlled status, move task to non-controlled status and verify cancel dispatch, local lock release, and visible cancellation outcome; verify lifecycle outcome records remain chronological across repeated runs.

### Tests for User Story 2

- [x] T019 [P] [US2] Add integration regression for manual status-change cancel signal handling in /Users/andreborczuk/ib-trading/tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py
- [x] T020 [P] [US2] Add dispatcher unit coverage for cancel-run payload semantics in /Users/andreborczuk/ib-trading/tests/unit/clickup_control_plane/test_dispatcher.py
- [x] T021 [P] [US2] Add outcome rendering unit tests for `input_resumed` and `cancelled_by_operator` decision text in /Users/andreborczuk/ib-trading/tests/unit/clickup_control_plane/test_clickup_client.py
- [x] T022 [US2] Add stale/orphan reconciliation regression proving manual cancel clears active local state even on cancel endpoint failure in /Users/andreborczuk/ib-trading/tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py

### Implementation for User Story 2

- [x] T023 [US2] Implement manual cancel signal detection from controlled-to-uncontrolled status transitions in /Users/andreborczuk/ib-trading/src/clickup_control_plane/service.py
- [x] T024 [US2] Implement cancel dispatch, active-lock release, paused-run cleanup, and terminal decision persistence in /Users/andreborczuk/ib-trading/src/clickup_control_plane/service.py
- [x] T025 [US2] Implement operator-safe lifecycle completion summaries (failed/timed_out/cancelled) in /Users/andreborczuk/ib-trading/src/clickup_control_plane/app.py

**Checkpoint**: US2 is independently functional with visible and auditable cancellation/lifecycle behavior.
<!-- Checkpoint validated: PASS | 2026-04-05 | All claims verified: manual cancel signal detection, cancel dispatch+lock release+paused cleanup, cancel-failure state cleanup invariant, cancelled_by_operator/input_resumed outcome rendering, lifecycle summaries for failed/timed_out/cancelled. 89 tests green. -->

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, behavior-map sync, and cross-story regression confidence.

- [x] T026 [P] Run full control-plane contract/unit/integration verification suite in /Users/andreborczuk/ib-trading/tests/contract/test_clickup_control_plane_contract.py
- [x] T027 Run pyright checks for touched control-plane modules in /Users/andreborczuk/ib-trading/src/clickup_control_plane/service.py
- [x] T028 Update runtime behavior map entries for phase-3 lifecycle behavior in /Users/andreborczuk/ib-trading/specs/015-control-plane-dispatch/behavior-map.md
- [x] T029 [P] Update operator runbook and validation evidence for HITL/cancel flows in /Users/andreborczuk/ib-trading/specs/017-control-plane-hitl-audit/quickstart.md
- [x] T030 Run cross-story async cleanup validation (no orphan dispatch/cancel tasks after test execution) in /Users/andreborczuk/ib-trading/tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py
- [x] T031 Run cross-story transaction-integrity validation (no partial lifecycle writes persist after failures) in /Users/andreborczuk/ib-trading/tests/unit/clickup_control_plane/test_state_store.py
- [x] T032 Add multi-run chronological audit integration scenario (`build -> qa fail -> rework -> qa pass`) in /Users/andreborczuk/ib-trading/tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py
- [x] T033 Add full lifecycle phase assertions (`queued`, `running`, `waiting_input`, `passed`, `failed`, `blocked`) in /Users/andreborczuk/ib-trading/tests/contract/test_clickup_control_plane_contract.py

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 -> no dependencies.
- Phase 2 -> depends on Phase 1 completion and blocks all user stories.
- Phase 3 (US1) and Phase 4 (US2) -> depend on Phase 2; can proceed in parallel after foundational completion.
- Phase 5 -> depends on completion of selected user stories.

### User Story Dependencies

- US1 (P1) -> starts after Phase 2; no dependency on US2.
- US2 (P2) -> starts after Phase 2; can run independently, though it reuses US1 foundational lifecycle/state primitives.

### Within Each User Story

- Tests first (contract/unit/integration), then implementation.
- Async guard tasks complete before story checkpoint.
- Reconciliation/transaction guard regressions complete before story checkpoint.

### External Ingress Ordering Rule

- `T000` must complete before any external webhook/runtime registration or readiness-proof tasks.

---

## Parallel Opportunities

- Phase 1: `T001` and `T002` can run in parallel.
- Phase 2: `T004`, `T006`, and `T009` can run in parallel after `T003`.
- US1: `T010`, `T011`, and `T012` can run in parallel.
- US2: `T019`, `T020`, and `T021` can run in parallel.
- Polish: `T026` and `T029` can run in parallel.

## Parallel Example: User Story 1

```bash
# Parallel US1 test tasks
Task: T010 tests/unit/clickup_control_plane/test_schemas.py
Task: T011 tests/contract/test_clickup_control_plane_contract.py
Task: T012 tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py
```

## Implementation Strategy

### MVP First (US1)

1. Complete Phase 1.
2. Complete Phase 2.
3. Complete US1 (Phase 3) and validate independent test criteria.
4. Demo/deploy MVP if stable.

### Incremental Delivery

1. Foundation (Phases 1-2).
2. Deliver US1 (P1).
3. Deliver US2 (P2).
4. Run Phase 5 cross-cutting verification and behavior-map sync.

### Team Parallelization

1. One engineer finalizes foundational state/transaction tasks.
2. Another executes US1 tests + implementation.
3. Another executes US2 tests + implementation.
4. Converge for Phase 5 verification + docs.

## Notes

- `[P]` means independent files/no blocking dependency on unfinished sibling tasks.
- Story labels map directly to `spec.md` stories for traceability.
- Keep tasks atomic; split further if a task starts spanning multiple unrelated file groups.
