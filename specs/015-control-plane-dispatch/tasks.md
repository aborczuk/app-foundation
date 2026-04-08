# Tasks: ClickUp + n8n Operational Control Plane — Phase 1: Event-Driven Workflow Dispatch

**Input**: Design documents from `/specs/015-control-plane-dispatch/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/, quickstart.md
**Skills**: Reuse client layering, typed error mapping, and redaction patterns from `src/mcp_trello/trello_client.py` and `src/mcp_trello/sync_engine.py`.

**Tests**: Tests are mandatory for this feature per constitution; include contract, unit, and integration coverage before implementation tasks.

**Organization**: Tasks are grouped by user story to enable independent implementation and validation.

## Approval Record

- Tasks reviewed and approved by author on 2026-04-02.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish module scaffolding, environment-key checkpoints, and adopted dependency configuration baselines.

- [X] T001 Create control-plane package scaffold in `src/clickup_control_plane/__init__.py`
- [X] T002 Implement runtime env-var configuration and required API key validation in `src/clickup_control_plane/config.py`
- [X] T003 [P] Add allowlist/workflow mapping example configuration in `config/control_plane_dispatch.example.yaml`
- [X] T004 [P] Add operator env template for control-plane secrets in `.env.control-plane.example`
- [X] T005 [P] Create control-plane test package scaffolding in `tests/unit/clickup_control_plane/__init__.py` and `tests/integration/clickup_control_plane/__init__.py`
- [X] T006 Add operator API-key placement checkpoint and verification section in `specs/015-control-plane-dispatch/quickstart.md`

**Checkpoint**: Control-plane module/test scaffolding exists and required secret inputs are explicitly documented.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement core trust-boundary validation, state safety, and transaction guarantees required before user-story work.

**⚠️ CRITICAL**: No user story implementation starts before this phase is complete.

- [X] T007 Implement normalized webhook event and dispatch decision schemas in `src/clickup_control_plane/schemas.py`
- [X] T008 Implement ClickUp webhook signature verification helpers in `src/clickup_control_plane/webhook_auth.py`
- [X] T009 Implement allowlist and routing-metadata policy evaluator in `src/clickup_control_plane/policy.py`
- [X] T010 Implement SQLite state store schema and atomic dedupe+active-run transaction boundaries in `src/clickup_control_plane/state_store.py`
- [X] T011 [P] Add rollback/no-partial-write transaction regression tests in `tests/unit/clickup_control_plane/test_state_store.py`
- [X] T012 Implement stale active-run reconciliation service against ClickUp source-of-truth in `src/clickup_control_plane/reconcile.py`
- [X] T013 [P] Add stale/orphan local-state reconciliation regression tests in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T014 Implement ClickUp outcome writer with redacted operator-safe messages in `src/clickup_control_plane/clickup_client.py`
- [X] T015 Implement n8n dispatch client with explicit timeout/cancel lifecycle handling in `src/clickup_control_plane/dispatcher.py`
- [X] T016 [P] Add running-loop async lifecycle regression tests (no nested-loop/runtime errors) in `tests/unit/clickup_control_plane/test_dispatcher.py`
- [X] T017 Implement FastAPI startup/shutdown dependency wiring and reconciliation bootstrap in `src/clickup_control_plane/app.py`

**Checkpoint**: Signature, policy, reconciliation, async lifecycle, and transaction guardrails are in place; user-story work can start.

---

## Phase 3: User Story 1 - Trigger Agent Workflow from Task Status Change (Priority: P1) 🎯 MVP

**Goal**: Dispatch the correct n8n workflow when an allowlisted ClickUp task enters a trigger status and write a visible outcome back to the task.

**Independent Test**: Move a valid allowlisted task into trigger status and verify one dispatch, one outcome update, and correct handling of invalid/duplicate/concurrent/scope-mismatch paths.

### Tests for User Story 1 (write first, ensure failing before implementation)

- [X] T018 [P] [US1] Add webhook contract coverage for accepted/error envelopes in `tests/contract/test_clickup_control_plane_contract.py`
- [X] T019 [P] [US1] Add signature acceptance/rejection unit tests in `tests/unit/clickup_control_plane/test_webhook_auth.py`
- [X] T020 [P] [US1] Add allowlist and missing-routing-metadata unit tests in `tests/unit/clickup_control_plane/test_policy.py`
- [X] T021 [US1] Add happy-path trigger-to-dispatch-to-outcome integration test in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T022 [US1] Add duplicate replay-burst idempotency integration test (100 identical events) in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T023 [US1] Add one-active-run guard integration test for concurrent trigger rejection in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T024 [US1] Add out-of-scope and missing-metadata operator-indicator integration tests in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T025 [US1] Add schema-mismatch blocked-indicator integration test in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`

### Implementation for User Story 1

- [X] T026 [US1] Implement webhook endpoint request validation and response contract in `src/clickup_control_plane/app.py`
- [X] T027 [US1] Implement dispatch orchestration service for policy→state→dispatch decisions in `src/clickup_control_plane/service.py`
- [X] T028 [US1] Wire endpoint orchestration across policy, state store, dispatcher, and ClickUp client in `src/clickup_control_plane/app.py`
- [X] T029 [US1] Implement workflow-type routing and n8n trigger payload builder in `src/clickup_control_plane/dispatcher.py`
- [X] T030 [US1] Implement one-active-run enforcement and dedupe decision persistence in `src/clickup_control_plane/state_store.py`
- [X] T031 [US1] Implement operator-visible outcome templates for all terminal decisions in `src/clickup_control_plane/clickup_client.py`
- [X] T032 [US1] Implement schema-mismatch detection and blocked-task outcome path in `src/clickup_control_plane/clickup_client.py`
- [X] T033 [US1] Enforce reconciliation checkpoint before dispatch lock acquisition in `src/clickup_control_plane/reconcile.py`
- [X] T034 [US1] Add no-unresolved-drift integration assertion after reconciliation in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`

**Checkpoint**: User Story 1 is independently functional and verifies success, duplicate, concurrent, scope, metadata, signature, and schema-mismatch paths.
<!-- Checkpoint validated: PASS | 2026-04-03 | contract+unit+integration control-plane suites passed (37 tests), no unresolved reconciliation drift assertions passing -->

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Harden cross-scenario safety, dependency operations, and release readiness.

- [X] T035 [P] Add cross-scenario orphan async-task cleanup validation in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T036 [P] Add impossible-state/no-partial-write validation coverage for failure paths in `tests/unit/clickup_control_plane/test_state_store.py`
- [X] T037 Update adopted dependency setup and failure-mode troubleshooting for ClickUp+n8n in `specs/015-control-plane-dispatch/quickstart.md`
- [X] T038 Add dependency-security recheck checkpoint for control-plane dependencies in `specs/015-control-plane-dispatch/quickstart.md`
- [X] T039 Run control-plane contract/unit/integration suites and record verification notes in `specs/015-control-plane-dispatch/quickstart.md`
- [X] T040 [P] Add signature+policy latency benchmark test asserting p95 < 300ms in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T041 [P] Add state-store dedupe/lock latency benchmark test asserting p95 < 50ms in `tests/unit/clickup_control_plane/test_state_store.py`
- [X] T042 Add replay-burst benchmark assertion report (100 identical events, zero duplicate dispatches) in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T043 Add stale out-of-order event regression test and `stale_event` assertion in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T044 Implement stale-event ordering decision handling in `src/clickup_control_plane/service.py` and `src/clickup_control_plane/state_store.py`
- [X] T045 Add action-scope violation regression test in `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`
- [X] T046 Implement action-scope guard enforcement in `src/clickup_control_plane/policy.py` and `src/clickup_control_plane/service.py`

---

## Ad-Hoc Tasks

**Purpose**: Close the local workflow gap by implementing a real offline QA process (not ledger-only signaling).

- [X] T047 Implement dedicated local offline QA runner with task handoff payload + explicit PASS/FIX_REQUIRED verdict output in `scripts/offline_qa.py`
- [X] T048 Wire offline QA runner usage into implementation workflow docs in `.claude/commands/speckit.implement.md` and `.speckit/README.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies; starts immediately.
- **Phase 2 (Foundational)**: Depends on Phase 1; blocks all user-story work.
- **Phase 3 (US1)**: Depends on Phase 2 completion.
- **Phase 4 (Polish)**: Depends on completion of US1 implementation and tests.

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories; this is the MVP and can ship once Phase 4 hardening completes.

### Within User Story 1

- Tests (T018-T025) are authored first and must fail before implementation.
- Contract and unit suites run before orchestration wiring.
- Async path must satisfy lifecycle guard + running-loop regression + orphan cleanup checks.
- Live-vs-local state must satisfy reconciliation invariant + stale/orphan regression + no-active-drift verification.
- Local DB mutation paths must satisfy explicit transaction boundaries + rollback regression + no-partial-write validation.

---

## Parallel Opportunities

- Setup tasks T003-T005 can run in parallel.
- Foundational regression tasks T011, T013, and T016 can run in parallel after corresponding implementation scaffolds exist.
- US1 contract/policy/auth tests T018-T020 can run in parallel.
- Polish safety checks T035-T036 can run in parallel.
- Performance and hardening tasks T040-T041 and T043-T045 can run in parallel where file ownership does not overlap.

---

## Parallel Example: User Story 1

```bash
Task: "T018 [US1] Add webhook contract coverage in tests/contract/test_clickup_control_plane_contract.py"
Task: "T019 [US1] Add signature unit tests in tests/unit/clickup_control_plane/test_webhook_auth.py"
Task: "T020 [US1] Add policy unit tests in tests/unit/clickup_control_plane/test_policy.py"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1 Setup.
2. Complete Phase 2 Foundational guardrails.
3. Complete Phase 3 US1 tests + implementation.
4. Validate independent test criteria for US1.

### Incremental Delivery

1. Deliver webhook trust/policy/state foundations.
2. Deliver US1 dispatch and outcome loop.
3. Deliver cross-cutting hardening and dependency operational checkpoints.

### Parallel Team Strategy

1. One engineer completes foundational persistence + reconciliation tasks.
2. One engineer handles contract/unit test authoring in parallel.
3. One engineer wires endpoint/dispatcher/client integration once foundational APIs stabilize.

---

## Notes

- `[P]` tasks are scoped for independent parallel execution.
- `[US1]` labels provide story-level traceability.
- Every task includes explicit file paths for agent-executable implementation.
- API key setup is explicitly tracked in Setup and Quickstart tasks.
