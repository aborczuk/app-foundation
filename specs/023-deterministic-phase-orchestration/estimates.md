# Effort Estimate: Deterministic Phase Orchestration

**Date**: 2026-04-19 | **Total Points**: 66 | **T-shirt Size**: L
**Estimated by**: AI (`speckit.tasking` estimate loop)

---

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T001 | 2 | Shared integration fixture seam | Existing test file seam; low uncertainty. |
| T002 | 1 | Shared unit transition helper | Local helper-only change in one file. |
| T003 | 3 | Route contract parsing hardening | Multi-branch normalization and error-path assertions. |
| T004 | 2 | Step mapping alignment to normalized routes | Focused routing adaptation in one runtime seam. |
| T005 | 3 | Ledger-authoritative phase-state resolution | Crosses state derivation and deterministic drift signaling. |
| T006 | 2 | Unit validate-before-emit regression | Narrow assertions on existing driver unit harness. |
| T007 | 2 | Integration blocked-validation no-append regression | One feature-flow path extension, known pattern. |
| T008 | 2 | Transition-map rejection test coverage | Existing ledger sequence test pattern reuse. |
| T009 | 5 | Deterministic run-step envelope hardening | Core orchestration seam with multiple failure envelope branches. |
| T010 | 5 | Success-append idempotent gating | High-risk ledger mutation boundary across retry/success paths. |
| T011 | 3 | Transition/append guard tightening | Sequence and append validation constraints across unit seams. |
| T012 | 2 | Deny/invalid approval integration tests | Existing integration harness with additional cases. |
| T013 | 2 | Drift reconciliation unit tests | Deterministic reason assertions in known unit file. |
| T014 | 3 | Explicit approval enforcement in runtime path | Behavioral control-flow update in primary driver seam. |
| T015 | 3 | Drift reason strengthening in phase-state resolver | Logic + deterministic reason-shape constraints in state seam. |
| T016 | 2 | Lock/retry sequencing refinement | Focused control-path update with existing lock seam. |
| T017 | 3 | Contract schema and mode-normalization tests | Contract-level assertions spanning route + schema contracts. |
| T018 | 2 | Producer-only markdown shape regression | One test seam update with known pattern. |
| T019 | 2 | Manifest/doc coverage regression | Existing coverage guard extension. |
| T020 | 2 | Manifest `speckit.solution` contract normalization | YAML updates with bounded schema scope. |
| T021 | 2 | Producer-only command contract wording updates | Deterministic command-doc contract edits in one file. |
| T022 | 1 | Quickstart ownership clarification | Documentation-only refinement. |
| T023 | 3 | Parse-step fail-fast contract enforcement | Error-contract handling across route and result parse logic. |
| T024 | 3 | Mixed migration deterministic regression | Integration regression across legacy + driver-mode branches. |
| T025 | 2 | Duplicate terminal-event retry prevention tests | Additional unit coverage in established seam. |
| T026 | 1 | Human dry-run/runbook verification record | Manual operator verification task with doc update. |
| T027 | 2 | Command-doc token-footprint measurement regression | Direct coverage for SC-004 measurement requirement. |
| T028 | 3 | Rollback and no-partial-write regression coverage | Explicit FR-013 rollback / partial-write oracle. |
| T029 | 3 | Manifest-to-ledger validation routing | Manifest emits gain ledger-domain routing so validation can dispatch to the correct existing ledger validator. |

---

### T003 — Solution Sketch

**Modify**: `scripts/pipeline_driver_contracts.py:load_driver_routes` to reject unknown modes and normalize emit contracts deterministically.
**Create**: none.
**Reuse**: Existing route-normalization helpers and reason-code conventions.
**Composition**: parse manifest route blocks, validate required keys, emit normalized driver route map.
**Failing test assertion**: unknown route mode returns deterministic contract error instead of fallback success.
**Domains touched**: command contracts, deterministic runtime.

### T005 — Solution Sketch

**Modify**: `scripts/pipeline_driver_state.py:resolve_phase_state` to prefer ledger truth over hints and emit machine-readable drift reasons.
**Create**: none.
**Reuse**: Existing event-stream read + reconcile logic.
**Composition**: derive current phase from ledger events, compare hints, add deterministic drift reason payload.
**Failing test assertion**: stale hint cannot override ledger-derived phase resolution.
**Domains touched**: state authority, retry/idempotency.

### T009 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:run_step` envelope parsing branches.
**Create**: none.
**Reuse**: Existing runtime failure sidecar writer.
**Composition**: normalize subprocess result, map invalid envelope/missing fields to deterministic blocked/error outcomes.
**Failing test assertion**: malformed step output yields blocked/error envelope and no completion progression.
**Domains touched**: runtime envelope, deterministic failure handling.

### T010 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:append_pipeline_success_event`.
**Create**: none.
**Reuse**: Existing manifest-derived emit contract and ledger append wrapper.
**Composition**: require validated gate-pass precondition, guard duplicate terminal emission on retries, append only once.
**Failing test assertion**: retry after terminal success does not duplicate completion event.
**Domains touched**: ledger mutation safety, idempotency.

### T011 — Solution Sketch

**Modify**: `scripts/pipeline_ledger.py:validate_sequence` and append guard call sites.
**Create**: none.
**Reuse**: Current transition maps and event-shape validators.
**Composition**: enforce predecessor requirements before append and preserve append-only guarantees.
**Failing test assertion**: invalid predecessor transition is rejected before ledger mutation.
**Domains touched**: governance state machine, append safety.

### T014 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:run_step` approval branch.
**Create**: none.
**Reuse**: Existing permission token checks and gate reason codes.
**Composition**: enforce explicit affirmative approval before command execution begins; denied/invalid exits are side-effect free.
**Failing test assertion**: non-yes approval never executes phase command and emits no completion event.
**Domains touched**: human approval gate, deterministic side-effect boundary.

### T015 — Solution Sketch

**Modify**: `scripts/pipeline_driver_state.py:resolve_phase_state`.
**Create**: none.
**Reuse**: drift flag structure used by feature-flow tests.
**Composition**: classify drift causes deterministically and expose machine-readable reason values for downstream handling.
**Failing test assertion**: unresolved reconciliation path yields explicit deterministic drift reason code.
**Domains touched**: state reconciliation, observability.

### T017 — Solution Sketch

**Modify**: `tests/contract/test_pipeline_driver_contract.py` assertions on route mode + step-result schema.
**Create**: none.
**Reuse**: existing contract fixture loader.
**Composition**: assert blocked schema requires gate/reasons and route mode normalization rejects invalid modes.
**Failing test assertion**: contract parse accepts invalid blocked payload without reasons (expected fail before fix).
**Domains touched**: contract verification, schema governance.

### T023 — Solution Sketch

**Modify**: `scripts/pipeline_driver_contracts.py:parse_step_result`.
**Create**: none.
**Reuse**: existing deterministic reason code constants.
**Composition**: strict parse/validate blocked/success envelopes; fail fast with deterministic reason codes.
**Failing test assertion**: malformed payload cannot be treated as successful step result.
**Domains touched**: command-result contract parsing, deterministic reasoning.

### T024 — Solution Sketch

**Modify**: `tests/integration/test_pipeline_driver_feature_flow.py:test_mixed_migration_mode`.
**Create**: none.
**Reuse**: existing migration-mode fixtures.
**Composition**: exercise mixed legacy and driver routes across deterministic success/blocked paths.
**Failing test assertion**: mixed migration path emits non-deterministic route behavior across repeated runs.
**Domains touched**: migration compatibility, regression safety.

### T027 — sketch: trivial

Token-footprint measurement is a focused test/additional assertion in an existing markdown-doc-shape seam.

### T028 — Solution Sketch

**Modify**: `tests/unit/test_pipeline_ledger_sequence.py:test_append_rejects_partial_write_and_preserves_state` to assert partial writes do not persist or advance the phase state.
**Create**: none.
**Reuse**: Existing sequence validator and append guard behavior.
**Composition**: simulate append failure or partial-write condition, then assert ledger state remains unchanged and no rollback ambiguity exists.
**Failing test assertion**: append failure still mutates state or advances the feature sequence.
**Domains touched**: storage integrity, governance state machine, testing.

### T029 — Solution Sketch

**Modify**: `scripts/pipeline_ledger.py:cmd_validate_manifest` to classify manifest emits by ledger domain and dispatch task events to the task-ledger validator path.
**Create**: none.
**Reuse**: Existing pipeline and task ledger validation rules plus manifest emit declarations.
**Composition**: tag manifest emits with ledger ownership, validate pipeline emits against pipeline transitions, and validate task emits against task transitions without collapsing the two ledgers.
**Failing test assertion**: task-domain manifest emits are rejected by the pipeline validator even though the task ledger already accepts them.
**Domains touched**: governance routing, manifest validation, audit-trail separation.

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 3 | 2 | 0 |
| Phase 2: Foundational | 8 | 3 | 0 |
| Phase 3: User Story 1 | 19 | 6 | 3 |
| Phase 4: User Story 2 | 12 | 5 | 2 |
| Phase 5: User Story 3 | 15 | 7 | 3 |
| Phase 6: Polish | 14 | 6 | 4 |
| **Total** | **71** | **29** | **12** |

---

## Warnings

- No tasks are scored 8 or 13; no breakdown required in this estimate loop.
- Phases with no parallel opportunities: Phase 1, Phase 2 (expected due shared setup/foundational sequencing).
- Higher-risk seams to monitor during implementation: T009, T010, T014 (primary driver/append control flow boundaries).
- Higher-risk seams to monitor during implementation: T029 (manifest routing and ledger-domain dispatch boundary).
- No uncovered async lifecycle guard, state-safety, or transaction-integrity gaps were identified from current task scope.
