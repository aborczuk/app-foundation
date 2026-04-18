# Tasks: Deterministic Phase Orchestration

## Format: `[ID] [P?] [Story] Description — file:symbol`

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 [P] Create the shared phase execution contract artifact so producer, validator, emitter, and handoff boundaries are explicit — `specs/023-deterministic-phase-orchestration/contracts/phase-execution-contract.md`
- [ ] T002 [P] Tighten routing and event-field notes in `command-manifest.yaml` and keep `.claude/commands/speckit.solution.md` aligned for the solution, solution-review, and tasking phases so the driver-owned contract stays canonical — `command-manifest.yaml:speckit.solutionreview`

**Checkpoint**: The phase contract and registry expectations are explicit before implementation starts.

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T003 [P] Implement ledger-authoritative current-step resolution so the driver does not trust stale mirrors over the pipeline ledger — `scripts/pipeline_driver_state.py:resolve_current_step`
- [ ] T004 [P] Add deterministic gate dispatch so every command consults its phase gate before proceeding, then keep validate-before-emit guard rails so phase completion events can only be appended after deterministic output validation passes — `scripts/pipeline_driver.py:run_phase`

**Checkpoint**: The orchestration spine resolves state deterministically and cannot emit before validation.

## Phase 3: User Story 1 - Deterministic Phase Completion (Priority: P1)

**Goal**: An operator runs phase execution and gets deterministic progression where phase events are emitted only after validation passes.

**Independent Test**: Run a phase where validation fails and confirm no completion event is emitted, then run with valid artifacts and confirm the event is emitted once.

### Tests for User Story 1

- [ ] T005 [P] [US1] Add regression coverage proving failed validation emits no phase completion event — `tests/integration/test_pipeline_driver.py:test_validate_before_emit`
- [ ] T006 [P] [US1] Add regression coverage proving a valid completion path emits exactly one phase event and returns a blocked result on validation failure — `tests/integration/test_pipeline_driver.py:test_phase_completion_emits_once`

### Implementation for User Story 1

- [ ] T007 [US1] Wire the orchestration flow to validate outputs before calling the ledger append path and to return deterministic blocked state on failure — `scripts/pipeline_driver.py:run_phase`
- [ ] T008 [US1] Keep the ledger append path append-only from validated payloads and preserve idempotent retry behavior — `scripts/pipeline_ledger.py:append`

**Checkpoint**: Validation failure cannot produce a false-positive completion event.

## Phase 4: User Story 2 - Permissioned Phase Start (Priority: P2)

**Goal**: An operator or skill sees the resolved current step and must explicitly approve execution before orchestration starts the phase.

**Independent Test**: Resolve a step with interactive confirmation, reject once and confirm no phase execution occurs, then approve and confirm phase execution begins.

### Tests for User Story 2

- [ ] T009 [P] [US2] Add approval/rejection regression tests for permissioned phase start and zero-side-effect rejection — `tests/integration/test_pipeline_driver.py:test_permissioned_phase_start`
- [ ] T010 [P] [US2] Add a deterministic state-resolution test proving the current step comes from the ledger-authoritative source — `tests/unit/test_pipeline_driver_state.py:test_resolve_current_step_ledger_authoritative`

### Implementation for User Story 2

- [ ] T011 [US2] Thread explicit approval handling through the driver start path so rejected confirmation cannot launch the phase — `scripts/pipeline_driver.py:start_phase`
- [ ] T012 [US2] Keep state resolution and approval checks in the driver-state module so permissioned starts stay deterministic — `scripts/pipeline_driver_state.py:resolve_current_step`

**Checkpoint**: Rejected approval has zero side effects and approved execution starts cleanly.

## Phase 5: User Story 3 - Producer-Only Command Contracts (Priority: P3)

**Goal**: Command docs produce phase artifacts and completion payloads only, while orchestration, validation, and event emission are handled by the deterministic driver contract.

**Independent Test**: Execute a migrated command flow where command docs return completion payload only and verify validation and event emission are performed by orchestration components.

### Tests for User Story 3

- [ ] T013 [P] [US3] Add markdown smoke coverage that the command docs still expose the compact/expanded headings and producer-only wording — `tests/unit/test_speckit_solution_command_doc.py:test_compact_expanded_shape`
- [ ] T014 [P] [US3] Add contract coverage proving the manifest and command docs agree on the driver-owned solution/tasking handoff — `tests/unit/test_validate_markdown_doc_shapes.py:test_compact_expanded_shape`

### Implementation for User Story 3

- [ ] T015 [US3] Keep `.claude/commands/speckit.solution.md` and related command docs producer-only and aligned to the driver-owned handoff model — `.claude/commands/speckit.solution.md`
- [ ] T016 [US3] Keep the quickstart and manifest aligned with the solution-to-tasking contract so operators see the same flow the driver enforces — `specs/023-deterministic-phase-orchestration/quickstart.md`

**Checkpoint**: Command docs no longer imply direct ledger writes and the driver remains the source of truth.

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T017 [P] Add separate analysis-path regression coverage so post-solution drift remains distinct from solution completion — `tests/integration/test_pipeline_driver.py:test_post_solution_analysis`
- [ ] T018 Update the phase contract validator so tasking and analyze handoffs continue to enforce the same boundary rules — `scripts/pipeline_driver_contracts.py:validate_phase_contract`

**Checkpoint**: Drift analysis stays separate from solution completion and the contract boundary remains stable.

## Dependencies & Execution Order

### Phase Dependencies

1. Phase 1 establishes the contract and registry alignment.
2. Phase 2 establishes the deterministic state and validation spine.
3. Phase 3 depends on Phases 1-2 and proves deterministic completion.
4. Phase 4 depends on Phases 1-2 and proves permissioned start behavior.
5. Phase 5 depends on the command-doc and manifest contract staying aligned.
6. Phase 6 can run after the three user stories are stable.

### User Story Dependencies

1. US1 is the governance core and should land first.
2. US2 can land in parallel with US1 once the state resolver is stable.
3. US3 should land after the driver contract and command-doc shape are stable.

### Within Each User Story

1. Write the failing test first.
2. Implement the smallest deterministic change that makes the test pass.
3. Add or update smoke coverage for the affected command docs or contract file.

### Parallel Opportunities

1. T005 and T006 can run in parallel once the test seam is identified.
2. T009 and T010 can run in parallel after the state-resolution seam is stable.
3. T013 and T014 can run in parallel with the docs and validator update.

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Lock down validation-before-emit sequencing.
2. Prove no false-positive completion event can be emitted.
3. Confirm idempotent retry behavior stays deterministic.

### Incremental Delivery

1. Add permissioned phase-start behavior after the completion gate is stable.
2. Tighten command-doc contracts after the orchestration spine is deterministic.
3. Finish with quickstart and analyzer separation polish.

### Parallel Team Strategy

1. One thread can own driver/state behavior.
2. One thread can own command-doc and manifest alignment.
3. One thread can own regression and smoke-test coverage.
