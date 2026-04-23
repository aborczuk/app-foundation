# Tasks: Deterministic Phase Orchestration

**Input**: Design documents from `/specs/023-deterministic-phase-orchestration/`
**Prerequisites**: `plan.md` (required), `spec.md` (required), `sketch.md` (required), `solutionreview.md` (required)

**One-Line Purpose**: Pipeline operators run phase work through a deterministic orchestrator that validates outputs before any ledger event is emitted.

## Format: `[ID] [P?] [Story] Description — file:symbol`

- `[P]`: Task can run in parallel (disjoint files, no incomplete dependency).
- `[H]`: Human-required external/manual action (mutually exclusive with `[P]`).
- `[USn]`: User story label required only in user-story phases.
- Every task includes concrete `file:symbol` ownership.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish deterministic test harness seams before behavior changes.

- [X] T001 Add shared feature-flow fixtures for deterministic ledger/manifest setup in `tests/integration/test_pipeline_driver_feature_flow.py` — `tests/integration/test_pipeline_driver_feature_flow.py:build_feature_workspace`
- [X] T002 Add shared unit helpers for transition assertions in `tests/unit/test_pipeline_ledger_sequence.py` — `tests/unit/test_pipeline_ledger_sequence.py:assert_transition_result`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Lock route/state/transition contracts before story-level behavior work.

- [X] T003 Harden route contract parsing and unknown-mode rejection in `scripts/pipeline_driver_contracts.py` — `scripts/pipeline_driver_contracts.py:load_driver_routes`
- [X] T004 Align step routing resolution to normalized route contracts in `scripts/pipeline_driver.py` — `scripts/pipeline_driver.py:resolve_step_mapping`
- [X] T005 Make phase resolution ledger-authoritative with deterministic drift reasons in `scripts/pipeline_driver_state.py` — `scripts/pipeline_driver_state.py:resolve_phase_state`

---

## Phase 3: User Story 1 - Deterministic Phase Completion (Priority: P1) 🎯 MVP

**Goal**: Completion events are emitted only after deterministic validation passes.

**Independent Test**: Run a phase where validation fails and confirm no completion event is emitted, then run with valid artifacts and confirm the event is emitted once.

| # | Given | When | Then |
|---|-------|------|------|
| 1 | valid phase context and valid produced artifacts | orchestrator executes phase flow | validation passes and the correct phase event is emitted |
| 2 | produced artifacts fail deterministic validation | orchestrator reaches validation step | no completion event is emitted and deterministic blocked result is returned |
| 3 | feature with no prior phase events | orchestration starts | first valid step resolves deterministically and completion is withheld until validation succeeds |

### Tests for User Story 1

- [X] T006 [P] [US1] Add unit tests for validate-before-emit and no-append-on-invalid-envelope behavior in `tests/unit/test_pipeline_driver.py` — `tests/unit/test_pipeline_driver.py:test_append_pipeline_success_event_requires_validated_success`
- [X] T007 [P] [US1] Add integration regression for blocked validation with zero completion append in `tests/integration/test_pipeline_driver_feature_flow.py` — `tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_blocked`
- [X] T008 [P] [US1] Add transition-map rejection coverage for invalid ordering before append in `tests/unit/test_pipeline_ledger_sequence.py` — `tests/unit/test_pipeline_ledger_sequence.py:test_new_solution_sequence_passes`

### Implementation for User Story 1

- [X] T009 [US1] Harden deterministic envelope handling for malformed or partial step outputs in `scripts/pipeline_driver.py` — `scripts/pipeline_driver.py:run_step`
- [X] T010 [US1] Enforce success append only after validated gate pass and idempotent terminal protection in `scripts/pipeline_driver.py` — `scripts/pipeline_driver.py:append_pipeline_success_event`
- [X] T011 [US1] Tighten transition validation and append-time guards for invalid predecessor events in `scripts/pipeline_ledger.py` — `scripts/pipeline_ledger.py:validate_sequence`

---

## Phase 4: User Story 2 - Permissioned Phase Start (Priority: P2)

**Goal**: Execution begins only after explicit approval and denied/invalid approvals create no side effects.

**Independent Test**: Resolve a step with interactive confirmation, reject once and confirm no phase execution occurs, then approve and confirm phase execution begins.

| # | Given | When | Then |
|---|-------|------|------|
| 1 | resolved current step | confirmation answer is `no` | orchestrator exits without phase execution or event emission |
| 2 | resolved current step | confirmation answer is `yes` | orchestrator starts phase execution flow |
| 3 | unauthorized or invalid permission response | confirmation is evaluated | deterministic permission failure response is returned |

### Tests for User Story 2

- [X] T012 [P] [US2] Add integration coverage for deny/invalid approval with zero side effects in `tests/integration/test_pipeline_driver_feature_flow.py` — `tests/integration/test_pipeline_driver_feature_flow.py:test_approval_breakpoint_blocks_without_token`
- [X] T013 [P] [US2] Add unit drift-resolution coverage for ledger-vs-hint reconciliation paths in `tests/unit/test_pipeline_driver.py` — `tests/unit/test_pipeline_driver.py:test_resolve_phase_state_prefers_ledger_authority`

### Implementation for User Story 2

- [X] T014 [US2] Require explicit approval token before side-effectful phase execution in `scripts/pipeline_driver.py` — `scripts/pipeline_driver.py:run_step`
- [X] T015 [US2] Strengthen phase-state reconciliation and machine-readable drift reasons in `scripts/pipeline_driver_state.py` — `scripts/pipeline_driver_state.py:resolve_phase_state`
- [X] T016 [US2] Tighten lock/retry sequencing around approval-gated execution in `scripts/pipeline_driver_state.py` — `scripts/pipeline_driver_state.py:acquire_feature_lock`

---

## Phase 5: User Story 3 - Producer-Only Command Contracts (Priority: P3)

**Goal**: Command docs emit producer payload contracts only; orchestration/validation/emission remain driver-owned.

**Independent Test**: Execute a migrated command flow where command docs return completion payload only and verify validation and event emission are performed by orchestration components.

| # | Given | When | Then |
|---|-------|------|------|
| 1 | phase command execution | command-level output is produced | output contains artifact and completion payload data without direct ledger mutation responsibilities |
| 2 | phase orchestration after command completion | deterministic checks pass | orchestrator emits events and routes handoff |

### Tests for User Story 3

- [X] T017 [P] [US3] Add contract tests for route-mode normalization and emit-contract schema validity in `tests/contract/test_pipeline_driver_contract.py` — `tests/contract/test_pipeline_driver_contract.py:test_step_result_schema_blocked_requires_gate_and_reasons`
- [X] T018 [P] [US3] Add markdown/doc-shape regression for producer-only command contract wording in `tests/unit/test_validate_markdown_doc_shapes.py` — `tests/unit/test_validate_markdown_doc_shapes.py:test_validate_markdown_doc_shape_accepts_compact_expanded`
- [X] T019 [P] [US3] Add command-script coverage regression for manifest/doc alignment in `tests/unit/test_validate_command_script_coverage.py` — `tests/unit/test_validate_command_script_coverage.py:test_validate_command_script_coverage_passes_with_required_scripts`

### Implementation for User Story 3

- [X] T020 [US3] Normalize manifest route and emit contracts for `speckit.solution` driver ownership in `./command-manifest.yaml` — `command-manifest.yaml:commands.speckit.solution`
- [X] T021 [US3] Update producer-only contract language and remove implicit append ownership in `.claude/commands/speckit.solution.md` — `.claude/commands/speckit.solution.md:## Outline`
- [X] T022 [US3] Document producer-vs-driver ownership and migration-safe operator flow in `specs/023-deterministic-phase-orchestration/quickstart.md` — `specs/023-deterministic-phase-orchestration/quickstart.md:# Quickstart`
- [X] T023 [US3] Fail fast on unknown route modes and malformed step payload contracts in `scripts/pipeline_driver_contracts.py` — `scripts/pipeline_driver_contracts.py:parse_step_result`

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final deterministic regression lock and explicit operator runbook boundary.

- [X] T024 Add mixed legacy/driver migration-path deterministic regression coverage in `tests/integration/test_pipeline_driver_feature_flow.py` — `tests/integration/test_pipeline_driver_feature_flow.py:test_mixed_migration_mode`
- [X] T025 Add duplicate terminal-event retry prevention coverage across driver and ledger seams in `tests/unit/test_pipeline_driver.py` — `tests/unit/test_pipeline_driver.py:test_idempotent_terminal_event_retry`
- [ ] T026 [H] Execute and record operator dry-run/runbook verification for approval and failure-sidecar workflows in `specs/023-deterministic-phase-orchestration/quickstart.md` — `specs/023-deterministic-phase-orchestration/quickstart.md:## Validation Procedure`
- [X] T027 Add command-doc token-footprint measurement regression for `SC-004` in `tests/unit/test_validate_markdown_doc_shapes.py` — `tests/unit/test_validate_markdown_doc_shapes.py:test_command_doc_token_footprint_reduction`
- [X] T028 Add rollback and no-partial-write regression coverage for `FR-013` in `tests/unit/test_pipeline_ledger_sequence.py` — `tests/unit/test_pipeline_ledger_sequence.py:test_append_rejects_partial_write_and_preserves_state`
- [X] T029 Add manifest-to-ledger validation routing so task-domain emits dispatch to the task ledger while pipeline emits stay pipeline-owned in `scripts/pipeline_ledger.py` — `scripts/pipeline_ledger.py:cmd_validate_manifest`

---

## Delta: Sketch-Generated Additions

**Purpose**: Append the regenerated sketch-derived work as an additive delta without disturbing the original 29-task graph.

### Delta Phase 1: Setup

- [X] T030 [P] Establish shared feature-flow fixtures for route/ledger setup and deterministic envelope assertions — `tests/integration/test_pipeline_driver_feature_flow.py:build_feature_workspace`
- [ ] T031 [P] Add shared runner-adapter request/response helpers used by contract and integration tests — `tests/contract/test_pipeline_driver_contract.py:test_step_result_schema_blocked_requires_gate_and_reasons`

### Delta Phase 2: Foundational

- [ ] T032 Harden runtime execution envelope semantics for success/blocked/error and debug sidecar behavior (SK-01) — `scripts/pipeline_driver.py:run_step`
- [ ] T033 Make phase resolution ledger-authoritative with deterministic drift reasons and lock behavior (SK-02) — `scripts/pipeline_driver_state.py:resolve_phase_state`
- [ ] T034 Enforce transition/append contract guards so only validated transitions mutate ledger state (SK-03) — `scripts/pipeline_ledger.py:validate_sequence`
- [ ] T035 Normalize manifest-driven route + emit contract parsing (including canonical trigger metadata) and reject unknown modes deterministically (SK-04) — `scripts/pipeline_driver_contracts.py:load_driver_routes`

### Delta Phase 3: User Story 1 - Deterministic Phase Completion

**Goal**: Completion events are emitted only after deterministic validation passes.

**Independent Test**: Run a phase where validation fails and confirm no completion event is emitted, then run with valid artifacts and confirm the event is emitted once.

- [ ] T036 [P] Add unit coverage for validate-before-emit and no-append-on-invalid-envelope behavior — `tests/unit/test_pipeline_driver.py:test_append_pipeline_success_event_requires_validated_success`
- [ ] T037 [P] Add integration coverage for blocked validation with zero completion append and deterministic reason codes — `tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_blocked`
- [ ] T038 Wire deterministic success append to validated route/emit contracts only, including parse-failure no-append behavior — `scripts/pipeline_driver.py:append_pipeline_success_event`

### Delta Phase 4: User Story 2 - Permissioned Phase Start

**Goal**: Phase execution starts only after explicit approval and rejects invalid/denied tokens with zero side effects.

**Independent Test**: Resolve a step with interactive confirmation, reject once and confirm no phase execution occurs, then approve and confirm phase execution begins.

- [ ] T039 [P] Add integration coverage for approval-denied and invalid-token branches with no ledger/artifact mutations — `tests/integration/test_pipeline_driver_feature_flow.py:test_approval_breakpoint_blocks_without_token`
- [ ] T040 Enforce deterministic approval gate and no-side-effect rejection path in driver execution flow — `scripts/pipeline_driver.py:require_confirmation`

### Delta Phase 5: User Story 3 - Producer-Only Command Contracts

**Goal**: Command docs emit producer payload contracts only; orchestration, gate checks, and ledger append remain driver-owned.

**Independent Test**: Run migrated command docs and confirm driver-owned orchestration/gating emits events while docs do not contain executable gate/ledger append procedures.

- [ ] T041 [P] Add doc-shape and manifest-contract coverage to reject command docs that embed executable gate/append procedures — `tests/unit/test_validate_markdown_doc_shapes.py:test_validate_markdown_doc_shape_accepts_compact_expanded`
- [ ] T042 Normalize `speckit.sketch` / `speckit.solution` / `speckit.implement` docs to compact producer-only contracts and align manifest route metadata (SK-05) — `.claude/commands/speckit.implement.md:Compact Contract (Load First)`

### Delta Phase 6: User Story 4 - Full-Pipeline Deterministic Entry

**Goal**: `/speckit.run` is the canonical progression trigger; direct phase reruns are allowed at/below latest allowed step, and only forward overreach is blocked/redirected.

**Independent Test**: Execute canonical trigger and direct phase invocations across states; confirm reruns at/below allowed step succeed deterministically while forward overreach is blocked/redirected with explicit reason codes.

- [ ] T043 [P] Add integration coverage for canonical trigger path and direct-rerun-vs-forward-overreach policy — `tests/integration/test_pipeline_driver_feature_flow.py:test_legacy_direct_phase_redirect_or_blocked`
- [ ] T044 [P] Add migration-path regression for mixed legacy/generative routing with deterministic contracts — `tests/integration/test_pipeline_driver_feature_flow.py:test_mixed_migration_mode`
- [ ] T045 Implement canonical trigger routing policy and deterministic direct invocation branch handling (SK-07) — `scripts/pipeline_driver.py:resolve_step_mapping`

### Delta Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Complete implement closeout orchestration, deterministic idempotency, and operator-facing governance.

- [ ] T046 Implement task-ledger-informed implement phase-close gates and once-only `implementation_completed` emission (SK-08) — `scripts/speckit_implement_gate.py:main`
- [ ] T047 [P] Add integration/unit regression coverage for implement close pass/fail/retry idempotency and duplicate terminal event prevention (SK-06 + SK-08) — `tests/integration/test_pipeline_driver_feature_flow.py:test_implement_completion_emits_once`
- [ ] T048 [P] Add runner-adapter stdin/stdout envelope contract coverage ensuring parse failures cannot emit completion events — `scripts/pipeline_driver_contracts.py:parse_step_result`
- [ ] T049 [H] Perform operator dry-run/live-run validation pass and capture deterministic rerun/forward-block reason-code evidence in quickstart notes — `specs/023-deterministic-phase-orchestration/quickstart.md:Deterministic Operator Runbook Notes`

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 (Setup): No dependencies.
- Phase 2 (Foundational): Depends on Phase 1.
- Phase 3 (US1): Depends on Phase 2. Delivers MVP deterministic validate-before-emit boundary.
- Phase 4 (US2): Depends on Phase 2 and leverages Phase 3 execution envelope hardening.
- Phase 5 (US3): Depends on Phase 2 and aligns manifest/doc ownership against stable runtime seams.
- Phase 6 (Polish): Depends on completion of Phases 3-5.
- Delta phases: appended after the original graph and intended as additive follow-on work.

### User Story Dependencies

- US1 (P1): No story dependency after foundational prerequisites.
- US2 (P2): Depends on US1 runtime envelope/transition guarantees.
- US3 (P3): Depends on US1 runtime behavior and US2 approval-state boundaries.

### Within Each User Story

- Tests should fail before implementation changes.
- Route/state contract updates precede dependent integration assertions.
- Manifest and command-doc contract tasks ship together to avoid drift windows.

### Parallel Opportunities

- T006, T007, and T008 can run in parallel after foundational prerequisites.
- T012 and T013 can run in parallel before US2 implementation tasks.
- T017, T018, and T019 can run in parallel before US3 implementation tasks.
- T024, T025, T027, and T028 can run in parallel after the story phases complete.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 and Phase 2.
2. Complete Phase 3 and validate deterministic no-emit-on-failed-validation behavior.
3. Run targeted regression tests before progressing to US2/US3.

### Incremental Delivery

1. Ship US1 deterministic completion boundary.
2. Add US2 permission gate and ledger-authoritative state safeguards.
3. Finish US3 producer-only contract normalization and cross-cutting regression lock.
4. Tackle the appended delta tasks once the original graph remains stable.

### Parallel Team Strategy

1. Engineer A: Driver/ledger runtime seams (T009-T016, T024-T025).
2. Engineer B: Manifest/contracts/docs + contract/doc-shape regressions (T017-T023).
3. Operator: Run human verification task T026 after automated regressions pass.
