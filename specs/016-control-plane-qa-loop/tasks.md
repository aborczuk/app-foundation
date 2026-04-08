# Tasks: ClickUp + n8n Operational Control Plane — Phase 2: QA Verification & Rework Loop

**Input**: Design documents from `/specs/016-control-plane-qa-loop/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/, quickstart.md
**Skills**: Reuse existing `src/clickup_control_plane` layering and operator-safe outcome patterns before introducing new QA-specific modules.

**Tests**: Tests are mandatory for this feature per constitution; include contract, unit, and integration coverage before implementation tasks.

**Organization**: Tasks are grouped by user story to enable independent implementation and validation.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish QA-loop scaffolding and explicit ingress/runtime readiness gate handling.

- [X] T000 Validate and resolve External Ingress + Runtime Readiness Gate failures from `specs/016-control-plane-qa-loop/plan.md` (including `/control-plane/health` route correctness evidence) before implementation tasks proceed
- [X] T001 Add QA loop status/failure-threshold configuration fields and parsing in `src/clickup_control_plane/config.py`
- [X] T002 [P] Add QA loop config examples and operator env docs in `config/control_plane_dispatch.example.yaml` and `specs/016-control-plane-qa-loop/quickstart.md`
- [X] T003 [P] Add QA loop module scaffold in `src/clickup_control_plane/qa_loop.py`
- [X] T004 [P] Add QA loop unit test scaffold in `tests/unit/clickup_control_plane/test_qa_loop.py`

**Checkpoint**: Ingress/runtime gate status is explicit, and QA-loop scaffolding/config surfaces are in place.

---

## Phase 1B: Executor Completion Lane (Blocking Prerequisites)

**Purpose**: Ensure routed automation performs real coding work and emits terminal completion back to ClickUp (not only dispatch acceptance).

**⚠️ CRITICAL**: No additional QA-loop implementation should proceed until this lane is wired end-to-end.

- [X] T005 Add workflow completion callback request/response contracts in `src/clickup_control_plane/schemas.py`
- [X] T006 Add completion-callback token config parsing and endpoint auth checks in `src/clickup_control_plane/config.py` and `src/clickup_control_plane/app.py`
- [X] T007 Implement completion callback handling (ClickUp outcome write + active-lock release) in `src/clickup_control_plane/app.py`
- [X] T008 [P] Add host Codex executor runner script for webhook-driven non-interactive runs in `scripts/codex_webhook_runner.py`
- [X] T009 [P] Add completion callback contract coverage (accepted + invalid token) in `tests/contract/test_clickup_control_plane_contract.py`
- [X] T010 Add integration regression for callback-driven lock release and follow-up dispatch in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T011 [P] Document completion token and host-runner callback path in `.env.control-plane.example` and `specs/016-control-plane-qa-loop/quickstart.md`
- [X] T012 Configure external n8n webhook handlers (`build_spec`, `qa_loop`) to dispatch GitHub Actions executor workflow and capture verification evidence in `specs/016-control-plane-qa-loop/quickstart.md` (completed 2026-04-03; run ids: `23963801429`, `23963836184`, `23964277014`)

**Checkpoint**: Executor invocation and completion callback are implemented in repo, and external n8n webhook handler wiring is verified end-to-end.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core QA loop contracts, routing primitives, and guardrails required before user-story implementation.

**⚠️ CRITICAL**: No user story implementation starts before this phase is complete.

- [X] T013 Extend QA-loop request/response models and failure-report schema in `src/clickup_control_plane/schemas.py`
- [X] T014 Extend QA workflow route mapping and payload builder in `src/clickup_control_plane/dispatcher.py`
- [X] T015 Implement QA outcome write helpers (pass, fail-to-build, blocked escalation) in `src/clickup_control_plane/clickup_client.py`
- [X] T016 Implement QA policy gates for missing criteria and blocked-state redispatch prevention in `src/clickup_control_plane/policy.py`
- [X] T017 Implement QA failure-streak and escalation coordination primitives in `src/clickup_control_plane/qa_loop.py`
- [X] T018 [P] Add running-loop lifecycle regression coverage for QA dispatch path in `tests/unit/clickup_control_plane/test_dispatcher.py`
- [X] T019 [P] Add state-safety regression for blocked-state/no-redispatch invariant in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`

**Checkpoint**: QA-loop foundations are available and safety guards are validated.

---

## Phase 3: User Story 1 - QA Verification with Automatic Pass/Fail Routing (Priority: P1) 🎯 MVP

**Goal**: Trigger QA from `Ready for QA`, advance on pass, route to build with structured report on fail, and escalate to human-required blocked state after 3 consecutive failures.

**Independent Test**: Execute build->QA pass/fail cycles and verify pass advance, fail backflow, third-fail block, and manual-unblock reset behavior from ClickUp-visible outcomes.

### Tests for User Story 1 (write first, ensure failing before implementation)

- [X] T020 [P] [US1] Add contract coverage for QA pass/fail/escalation envelopes in `tests/contract/test_clickup_control_plane_contract.py`
- [X] T021 [P] [US1] Add QA loop unit tests for failure streak increment/reset logic in `tests/unit/clickup_control_plane/test_qa_loop.py`
- [X] T022 [US1] Add integration test for QA pass path advancing task status in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T023 [US1] Add integration test for QA fail path returning task to build with structured report in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T024 [US1] Add integration test for third consecutive fail -> blocked escalation in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T025 [US1] Add integration test for manual unblock reset and re-entry to QA cycle in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`

### Implementation for User Story 1

- [X] T026 [US1] Implement QA attempt evaluation + consecutive-failure tracking service in `src/clickup_control_plane/qa_loop.py`
- [X] T027 [US1] Wire QA loop decision path into orchestration flow in `src/clickup_control_plane/service.py`
- [X] T028 [US1] Wire QA loop decisions into webhook endpoint response mapping in `src/clickup_control_plane/app.py`
- [X] T029 [US1] Implement missing-criteria short-circuit path with operator-visible outcome in `src/clickup_control_plane/service.py` and `src/clickup_control_plane/clickup_client.py`
- [X] T030 [US1] Implement fail-to-build status transition + structured failure report emission in `src/clickup_control_plane/clickup_client.py`
- [X] T031 [US1] Implement blocked-after-3-fails behavior and redispatch rejection in `src/clickup_control_plane/qa_loop.py` and `src/clickup_control_plane/policy.py`
- [X] T032 [US1] Implement manual-unblock reset flow and failure-streak reset handling in `src/clickup_control_plane/service.py` and `src/clickup_control_plane/qa_loop.py`
- [X] T033 [US1] Attach/propagate prior failure context and QA artifacts in `src/clickup_control_plane/dispatcher.py` and `src/clickup_control_plane/clickup_client.py`

**Checkpoint**: User Story 1 is independently functional and testable end-to-end.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Harden cross-scenario safety, documentation, and release-readiness evidence.

- [X] T034 [P] Add cross-scenario async cleanup/no-orphan-task validation for QA loop in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T035 [P] Add stale/out-of-order QA event regression to protect failure-streak integrity in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T036 Update Phase 2 troubleshooting and verification runbook in `specs/016-control-plane-qa-loop/quickstart.md`
- [X] T037 Add dependency-security recheck checkpoint notes for Phase 2 rollout in `specs/016-control-plane-qa-loop/quickstart.md`
- [X] T038 Run contract/unit/integration QA-loop suites and record verification notes in `specs/016-control-plane-qa-loop/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Starts immediately and must include T000 gate handling.
- **Phase 1B (Executor Completion Lane)**: Depends on Phase 1; blocks QA-loop story implementation until executor/completion path is wired.
- **Phase 2 (Foundational)**: Depends on Phase 1 and Phase 1B; blocks all user-story work.
- **Phase 3 (US1)**: Depends on Phase 2 completion.
- **Phase 4 (Polish)**: Depends on US1 completion.

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories; this is the MVP for Phase 2.

### Within User Story 1

- Tests (T020-T025) are written first and must fail before implementation.
- Async integration path must keep running-loop safety (T018) and orphan cleanup validation (T034).
- Live-vs-local state safety must enforce blocked-state no-redispatch and deterministic reset behavior (T019, T024, T031, T032).
- Local DB mutation guard tasks are N/A for new Phase 2 lifecycle ownership because authoritative QA state remains in ClickUp.

---

## Parallel Opportunities

- Setup tasks T002-T004 can run in parallel.
- Executor-lane tasks T008-T009 and T011 can run in parallel.
- Foundational safety tests T018-T019 can run in parallel once foundational scaffolds exist.
- US1 tests T020-T021 can run in parallel.
- Polish hardening tasks T034-T035 can run in parallel.

---

## Parallel Example: User Story 1

```bash
Task: "T020 [US1] Add contract coverage for QA pass/fail/escalation envelopes"
Task: "T021 [US1] Add QA loop unit tests for failure streak increment/reset logic"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1 setup and resolve T000 ingress/runtime gate.
2. Complete Phase 1B executor completion lane and resolve T012 external webhook-handler wiring.
3. Complete Phase 2 foundational guardrails.
4. Complete US1 tests + implementation.
5. Validate independent US1 acceptance criteria.

### Incremental Delivery

1. Deliver executor completion lane (callback endpoint + host runner + external handler wiring).
2. Deliver QA loop foundations (models/routing/policy guards).
3. Deliver pass/fail/escalation flow.
4. Deliver hardening and operational runbook evidence.

### Parallel Team Strategy

1. One engineer owns QA loop domain service + orchestration wiring.
2. One engineer owns contract/unit test authoring.
3. One engineer owns integration regressions and runbook evidence updates.

---

## Notes

- `[P]` tasks are scoped for independent parallel execution.
- `[US1]` labels provide story-level traceability.
- Every task includes explicit file paths for agent-executable implementation.
