# Tasks: Deterministic Pipeline Driver with LLM Handoff

**Input**: Design documents from `/specs/019-token-efficiency-docs/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/
**Skills**: `speckit-workflow`

**Tests**: Story-level integration and contract tests are required because this feature changes orchestration control flow and ledger invariants.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (no unresolved dependency in same phase)
- **[Story]**: User story label (`[US1]`, `[US2]`, `[US3]`) for story phases only
- Every task includes concrete file paths and primary symbol scope

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize deterministic command coverage and baseline files.

- [ ] T000 Record External Ingress + Runtime Readiness Gate as N/A (CLI-only feature) in specs/019-token-efficiency-docs/tasks.md
- [ ] T001 Build initial command-to-script coverage inventory from command-manifest.yaml and .specify/command-manifest.yaml into docs/governance/command-script-coverage.md:coverage_matrix
- [ ] T002 Create orchestrator module skeletons in scripts/pipeline_driver.py:main, scripts/pipeline_driver_state.py:resolve_phase_state, scripts/pipeline_driver_contracts.py:parse_step_result
- [ ] T003 [P] Create test module skeletons in tests/unit/test_pipeline_driver.py, tests/integration/test_pipeline_driver_feature_flow.py, tests/contract/test_pipeline_driver_contract.py

**Checkpoint**: Coverage inventory exists and orchestrator/test skeleton files are in place.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement deterministic routing core and enforcement gates before story work.

**CRITICAL**: No user story tasks begin until this phase is complete.

- [ ] T004 Implement manifest route loader and mode normalization in scripts/pipeline_driver_contracts.py:load_driver_routes
- [ ] T005 [P] Implement feature lock acquire/release/stale-owner handling in scripts/pipeline_driver_state.py:acquire_feature_lock
- [ ] T006 [P] Implement ledger-authoritative phase resolver and drift detection in scripts/pipeline_driver_state.py:resolve_phase_state
- [ ] T007 Implement deterministic step executor with timeout/cancel and exit-code routing in scripts/pipeline_driver.py:run_step
- [ ] T008 Implement mandatory `exit_code=2` verbose rerun + sidecar persistence in scripts/pipeline_driver.py:handle_runtime_failure
- [ ] T009 [P] Create shared status contract constants + renderer in scripts/pipeline_driver_contracts.py (`STATUS_KEYS`, `STATUS_PREFIXES`, `render_status_lines`) and make them the only allowed source for human step status output
- [ ] T010 [P] Implement run-scoped correlation ID propagation helper in scripts/pipeline_driver.py:build_correlation_id
- [ ] T011 Implement command coverage validator in scripts/validate_command_script_coverage.py:main
- [ ] T012 Wire coverage validator into governance checks in scripts/validate_doc_graph.sh:run_validators and scripts/validate_constitution_sync.sh:run_checks
- [ ] T013 [P] Build shared integration flow harness in tests/integration/conftest.py:driver_flow_harness (feature fixture setup, ledger seed, route invocation, teardown) and add drift/idempotency coverage in tests/integration/test_pipeline_driver_feature_flow.py:test_reconcile_and_retry_guards using that harness

**Checkpoint**: Deterministic core execution, lock/drift safeguards, and coverage validator are operational.

---

## Phase 3: User Story 1 - Deterministic Step Routing (Priority: P1) 🎯 MVP

**Goal**: Resolve phase state deterministically, dispatch mapped scripts, and return explicit LLM handoff only when generation is required.

**Independent Test**: Run orchestrator against fixture states for mapped-success, mapped-blocked, and generative-handoff paths and verify deterministic routing outcome.

### Tests for User Story 1

- [ ] T014 [P] [US1] Add mapped-success routing integration test in tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_success using shared harness fixture (no duplicated setup)
- [ ] T015 [P] [US1] Add mapped-blocked routing integration test with gate/reasons assertions in tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_blocked using shared harness fixture (no duplicated setup)
- [ ] T016 [P] [US1] Add generative-step handoff contract unit test in tests/unit/test_pipeline_driver.py:test_handoff_contract

### Implementation for User Story 1

- [ ] T017 [US1] Implement command-to-script allowlist dispatch from command-manifest.yaml in scripts/pipeline_driver.py:resolve_step_mapping
- [ ] T018 [US1] Implement legacy fallback for non-driver-managed phases in scripts/pipeline_driver.py:route_legacy_step
- [ ] T019 [US1] Implement post-LLM artifact validation before success event append in scripts/pipeline_driver.py:validate_generated_artifact
- [ ] T020 [US1] Update routing metadata and driver-managed flags in command-manifest.yaml:commands and .specify/command-manifest.yaml:commands

**Checkpoint**: Deterministic and generative routes are both enforced with explicit mapping rules.

---

## Phase 4: User Story 2 - Compact Parsing Contract (Priority: P2)

**Goal**: Enforce canonical step-result envelopes and minimal human output while preserving structured diagnostics for drill-down.

**Independent Test**: Execute success/gate-failure/runtime-failure fixtures and verify exit-code-first routing plus strict `Done/Next/Blocked` output contract.

### Tests for User Story 2

- [ ] T021 [P] [US2] Add contract tests for canonical result envelope (`exit_code` 0/1/2) in tests/contract/test_pipeline_driver_contract.py:test_step_result_schema
- [ ] T022 [P] [US2] Add runtime-failure verbose-rerun integration test in tests/integration/test_pipeline_driver_feature_flow.py:test_runtime_failure_verbose_rerun using shared harness fixture and sidecar assertions
- [ ] T023 [P] [US2] Add dry-run no-mutation integration test in tests/integration/test_pipeline_driver_feature_flow.py:test_dry_run_does_not_mutate_ledgers_or_artifacts
- [ ] T024 [P] [US2] Add human-approval-breakpoint routing test in tests/unit/test_pipeline_driver.py:test_approval_breakpoint_blocks_without_token and tests/integration/test_pipeline_driver_feature_flow.py:test_approval_breakpoint_resume_flow

### Implementation for User Story 2

- [ ] T025 [US2] Implement canonical envelope parsing + schema-version compatibility in scripts/pipeline_driver_contracts.py:parse_step_result and define shared route/error contract constants consumed by all deterministic route handlers
- [ ] T026 [US2] Implement default stdout suppression and three-line status emission in scripts/pipeline_driver.py:emit_human_status by consuming shared status contract constants from scripts/pipeline_driver_contracts.py (no inline status strings)
- [ ] T027 [US2] Implement explicit diagnostics drill-down command in scripts/pipeline_driver.py:drill_down_failure
- [ ] T028 [US2] Align contract docs and operator runbook in specs/019-token-efficiency-docs/contracts/orchestrator-step-result.schema.json and specs/019-token-efficiency-docs/quickstart.md
- [ ] T029 [US2] Implement `--dry-run` planning path in scripts/pipeline_driver.py:main and scripts/pipeline_driver_state.py:resolve_phase_state so no artifacts or ledgers are mutated
- [ ] T030 [US2] Implement configurable approval breakpoints in scripts/pipeline_driver.py:enforce_approval_breakpoint with deterministic block/resume semantics for irreversible/security-sensitive steps
- [ ] T031 [US2] Create deterministic reason-code registry in docs/governance/gate-reason-codes.yaml and wire loader/validator in scripts/pipeline_driver_contracts.py:validate_reason_codes
- [ ] T032 [US2] Enforce reason-code compatibility in scripts/pipeline_driver_contracts.py:parse_step_result and scripts/pipeline_driver.py:drill_down_failure (invalid/unknown reason codes fail contract)

**Checkpoint**: Compact parsing contract is deterministic and diagnostics are available only on explicit drill-down.

---

## Phase 5: User Story 3 - Governance and Migration Safety (Priority: P3)

**Goal**: Support incremental migration while ensuring uncovered commands/scripts are deterministically detected and blocked.

**Independent Test**: Enable mixed migration mode and verify ledger/event invariants remain valid while uncovered command mappings fail deterministic coverage checks.

### Tests for User Story 3

- [ ] T033 [P] [US3] Add mixed-migration integration regression in tests/integration/test_pipeline_driver_feature_flow.py:test_mixed_migration_mode using shared harness fixture to avoid duplicate route/bootstrap logic
- [ ] T034 [P] [US3] Add manifest-governance regression for version/timestamp coupling in tests/unit/test_pipeline_driver.py:test_manifest_governance_guard

### Implementation for User Story 3

- [ ] T035 [US3] Implement deterministic command coverage report (missing scripts/modes) in scripts/validate_command_script_coverage.py:build_coverage_report
- [ ] T036 [US3] Add solution/tasking gate check for uncovered command mappings in scripts/speckit_gate_status.py:validate_command_coverage
- [ ] T037 [US3] Extend manifest validation invariants for coverage enforcement in scripts/pipeline_ledger.py:cmd_validate_manifest
- [ ] T038 [US3] Document migration/rollback and coverage ownership policy in docs/governance/command-script-coverage.md and specs/019-token-efficiency-docs/research.md
- [ ] T039 [US3] Add explicit scaffold invocation for solution review in .claude/commands/speckit.solutionreview.md (`pipeline-scaffold.py speckit.solutionreview`) and update docs/governance/command-script-coverage.md
- [ ] T040 [US3] Remove root mirror manifest command-manifest.yaml and repoint all repository references to .specify/command-manifest.yaml as canonical
- [ ] T041 [P] [US3] Add anti-regression guard in scripts/validate_doc_graph.sh:run_validators (or dedicated script) to fail when command-manifest.yaml mirror is reintroduced or referenced

**Checkpoint**: Mixed-mode migration is supported and uncovered command mappings cannot pass gates silently.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate format, run static checks, and confirm quickstart flow.

- [ ] T042 [P] Run task-format and plan gates on finalized artifacts via scripts/speckit_tasks_gate.py and scripts/speckit_gate_status.py
- [ ] T043 Run dry-run orchestration scenario and capture evidence in scripts/e2e_020.sh and specs/019-token-efficiency-docs/quickstart.md
- [ ] T044 [P] Run lint/type checks for touched workflow files in scripts/pipeline_driver.py, scripts/pipeline_driver_contracts.py, scripts/validate_command_script_coverage.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Starts immediately
- **Phase 2 (Foundational)**: Depends on Phase 1, blocks all user stories
- **Phase 3-5 (User Stories)**: Depend on Phase 2; execute in priority order for MVP (`US1` -> `US2` -> `US3`) or parallel by staffing after dependencies
- **Phase 6 (Polish)**: Depends on completion of desired user stories

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories; must land first for MVP
- **US2 (P2)**: Depends on deterministic routing core from US1 plus foundational shared status contract primitives from T009
- **US3 (P3)**: Depends on US1/US2 contracts to enforce migration coverage rules

### Within Each User Story

- Tests are authored before implementation and used as deterministic acceptance gates
- Integration tests MUST use `tests/integration/conftest.py:driver_flow_harness` instead of duplicated per-test setup
- Human-facing status lines MUST originate from `scripts/pipeline_driver_contracts.py` shared status constants/renderer (no inline literals in orchestrator routes)
- Manifest/schema updates must be mirrored in both command-manifest files
- Coverage validation changes must run through deterministic gate scripts (no manual pass)

### Parallel Opportunities

- Tasks marked `[P]` in each phase can run concurrently
- Test tasks in the same story can run in parallel
- Governance doc updates can run in parallel with non-overlapping code updates

---

## Parallel Example: User Story 1

```bash
# Run US1 tests in parallel:
Task: "T014 [US1] mapped-success routing integration test"
Task: "T015 [US1] mapped-blocked routing integration test"
Task: "T016 [US1] generative-step handoff unit test"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Setup + Foundational
2. Complete US1 deterministic routing and handoff paths
3. Validate independent test criteria for US1
4. Demo deterministic dispatch and blocked-state behavior

### Incremental Delivery

1. Land US1 (routing)
2. Add US2 (contract + compact parsing)
3. Add US3 (migration safety + coverage enforcement)
4. Run polish gates and static checks

### Parallel Team Strategy

1. Pair on Phase 2 foundational core
2. Split after Phase 2:
   - Engineer A: US1 + US2 runtime contract path
   - Engineer B: US3 governance coverage validator + docs
3. Rejoin for polish and gate validation
