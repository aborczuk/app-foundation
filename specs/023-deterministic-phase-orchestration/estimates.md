# Effort Estimate: Deterministic Phase Orchestration

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T001 | 1 | Create `specs/023-deterministic-phase-orchestration/contracts/phase-execution-contract.md` with the producer / validator / emitter / handoff boundaries | Repo-process documentation only; no code-path changes |
| T002 | 2 | Tighten routing and event-field notes in `command-manifest.yaml` and keep `.claude/commands/speckit.solution.md` aligned for the solution, solution-review, and tasking phases | Small cross-file contract alignment with an existing manifest shape |
| T003 | 3 | Implement ledger-authoritative current-step resolution so the driver does not trust stale mirrors over the pipeline ledger | State resolution touches the orchestration boundary and needs deterministic failure handling |
| T004 | 3 | Add validation-before-emit guard rails so phase completion events can only be appended after deterministic output validation passes | Introduces sequencing guarantees across driver and ledger surfaces |
| T005 | 3 | Add regression coverage proving failed validation emits no phase completion event | Failure-path contract coverage across orchestration and ledger boundaries |
| T006 | 3 | Add regression coverage proving a valid completion path emits exactly one phase event and returns a blocked result on validation failure | Similar boundary scope to T005, but with a separate success-path contract assertion |
| T007 | 3 | Wire the orchestration flow to validate outputs before calling the ledger append path and to return deterministic blocked state on failure | Core driver control flow change with a non-trivial ordering guarantee |
| T008 | 3 | Keep the ledger append path append-only from validated payloads and preserve idempotent retry behavior | Ledger sequencing and retry semantics are small in surface area but high risk |
| T009 | 3 | Add approval/rejection regression tests for permissioned phase start and zero-side-effect rejection | Explicit permission-gate matrix across the driver start path |
| T010 | 2 | Add a deterministic state-resolution test proving the current step comes from the ledger-authoritative source | Bounded unit coverage around a single state seam |
| T011 | 3 | Thread explicit approval handling through the driver start path so rejected confirmation cannot launch the phase | Touches interactive start flow and control transfer between resolver and driver |
| T012 | 2 | Keep state resolution and approval checks in the driver-state module so permissioned starts stay deterministic | Small follow-up change to the same state seam as T010 |
| T013 | 2 | Add markdown smoke coverage that the command docs still expose the compact/expanded headings and producer-only wording | Pure documentation smoke with an existing helper seam |
| T014 | 3 | Add contract coverage proving the manifest and command docs agree on the driver-owned solution/tasking handoff | Cross-file contract validation across docs and registry metadata |
| T015 | 2 | Keep `.claude/commands/speckit.solution.md` and related command docs producer-only and aligned to the driver-owned handoff model | Doc-only alignment work across a small set of command files |
| T016 | 2 | Keep the quickstart and manifest aligned with the solution-to-tasking contract so operators see the same flow the driver enforces | Documentation alignment across two artifact surfaces |
| T017 | 3 | Add separate analysis-path regression coverage so post-solution drift remains distinct from solution completion | Distinct event-path regression with orchestration and reporting implications |
| T018 | 2 | Update the phase contract validator so tasking and analyze handoffs continue to enforce the same boundary rules | Small validator update against an already-shaped contract seam |

---

### T001 — sketch: trivial

No detailed sketch required. This is a repo-process documentation update.

### T002 — sketch: trivial

No detailed sketch required. This is a small manifest / command-doc alignment change.

### T003 — Solution Sketch

**Modify**: `scripts/pipeline_driver_state.py:resolve_current_step` and related state helpers to prefer the ledger over any local mirror.
**Create**: none.
**Reuse**: the existing pipeline ledger read path and the current driver state resolution flow.
**Composition**: the driver asks the ledger for the authoritative last event, derives the current step from that event, and refuses to advance when the ledger and any cached mirror diverge.
**Failing test assertion**: the state-resolution test should fail until the resolver returns the ledger-derived step even when a stale cached step says otherwise.
**Domains touched**: `.claude/domains/03_data_storage_persistence.md`, `.claude/domains/07_compute_orchestration.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T004 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:run_phase` and `scripts/pipeline_ledger.py:append` to enforce validate-before-emit ordering.
**Create**: none.
**Reuse**: the existing validation and append commands, plus the ledger event schema already declared in `command-manifest.yaml`.
**Composition**: the driver produces artifacts, runs deterministic validation, and only then passes the validated payload into the ledger append path.
**Failing test assertion**: the regression should fail until a validation failure leaves the ledger unchanged and a success path appends exactly one completion event.
**Domains touched**: `.claude/domains/07_compute_orchestration.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T005 — Solution Sketch

**Modify**: the test suite under `tests/integration/test_pipeline_driver.py` to assert the blocked path does not emit a completion event.
**Create**: a regression test function for the validation-failure path.
**Reuse**: the current driver invocation fixture and the pipeline ledger assertion helpers.
**Composition**: the test drives a failing artifact scenario through the orchestrator, then inspects the ledger to ensure the completion event never appears.
**Failing test assertion**: the assertion should fail until a rejected validation leaves the ledger without the completion event.
**Domains touched**: `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`

### T006 — Solution Sketch

**Modify**: the same integration suite to add the success-path assertion for a single emitted completion event.
**Create**: a second regression test covering the valid-completion flow.
**Reuse**: the same driver fixture and event-count assertion helpers used by T005.
**Composition**: the test runs a valid phase context, confirms the validator passes, and then checks that the completion event appears once and only once.
**Failing test assertion**: the assertion should fail until the happy path emits exactly one event and the failure path still blocks cleanly.
**Domains touched**: `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`

### T007 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:run_phase` to order artifact generation, validation, and handoff deterministically.
**Create**: none.
**Reuse**: the existing command execution flow and the driver state resolver.
**Composition**: the driver gathers artifacts, validates them, and only then hands a validated payload to the ledger append path.
**Failing test assertion**: the new coverage should fail until the driver calls validation before the ledger append path and returns the blocked status on failure.
**Domains touched**: `.claude/domains/07_compute_orchestration.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`

### T008 — Solution Sketch

**Modify**: `scripts/pipeline_ledger.py:append` and any supporting validation helpers to keep append behavior idempotent.
**Create**: none.
**Reuse**: the existing append command and event-shape validation code.
**Composition**: validated payloads are appended once, duplicate retries are ignored or rejected deterministically, and the append path remains the only write seam.
**Failing test assertion**: the retry behavior test should fail until repeated valid submissions do not create duplicate terminal events.
**Domains touched**: `.claude/domains/03_data_storage_persistence.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`

### T009 — Solution Sketch

**Modify**: the integration tests around the phase start path to exercise approval and rejection.
**Create**: regression tests for a rejected approval and an accepted approval.
**Reuse**: the current-step resolver and the interactive permission-gate flow.
**Composition**: the tests drive the resolver, simulate the human response, and assert zero side effects on rejection.
**Failing test assertion**: the suite should fail until a rejection prevents phase execution and an approval allows it to begin.
**Domains touched**: `.claude/domains/07_compute_orchestration.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/13_identity_access_control.md`

### T010 — sketch: trivial

No detailed sketch required. This is a focused unit test around the authoritative state source.

### T011 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:start_phase` and any start-flow adapters so explicit approval is required before execution begins.
**Create**: none.
**Reuse**: the state resolver and the existing driver entrypoint naming / phase progression contract.
**Composition**: the driver resolves the current step, prompts for explicit approval, and aborts without side effects when approval is denied.
**Failing test assertion**: the approval-flow test should fail until a rejected confirmation returns without starting the phase and an accepted confirmation proceeds.
**Domains touched**: `.claude/domains/07_compute_orchestration.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/13_identity_access_control.md`, `.claude/domains/16_ops_governance.md`

### T012 — sketch: trivial

No detailed sketch required. This is a small follow-up to the state-resolution and approval seams.

### T013 — sketch: trivial

No detailed sketch required. This is a markdown smoke test plus producer-only wording check.

### T014 — Solution Sketch

**Modify**: the validator and smoke-test coverage around `command-manifest.yaml` and `.claude/commands/speckit.solution.md`.
**Create**: contract coverage that reads the command docs and manifest together.
**Reuse**: the new markdown heading discovery flow and the compact / expanded command-doc shape already standardized in the repo.
**Composition**: the test asserts that the manifest and command docs still describe the same driver-owned handoff contract and do not drift apart.
**Failing test assertion**: the coverage should fail until the manifest and docs agree on the tasking handoff and producer-only wording.
**Domains touched**: `.claude/domains/10_observability.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`, `.claude/domains/17_code_patterns.md`

### T015 — sketch: trivial

No detailed sketch required. This is a command-doc wording alignment task.

### T016 — sketch: trivial

No detailed sketch required. This is a quickstart / manifest alignment update.

### T017 — Solution Sketch

**Modify**: the driver analysis path and the regression coverage that keeps analysis distinct from solution completion.
**Create**: a dedicated integration test for the post-solution analysis event path.
**Reuse**: the existing pipeline driver flow and the ledger append gate.
**Composition**: the analysis path stays separate from completion, emits its own event contract, and reports drift without collapsing it into solution success.
**Failing test assertion**: the test should fail until analysis is emitted through the separate path and no solution-completion event is reused for drift reporting.
**Domains touched**: `.claude/domains/07_compute_orchestration.md`, `.claude/domains/10_observability.md`, `.claude/domains/11_resilience_continuity.md`, `.claude/domains/12_testing_quality_gates.md`, `.claude/domains/16_ops_governance.md`

### T018 — sketch: trivial

No detailed sketch required. This is a focused validator update for the existing contract boundary.

## Phase Totals

| Phase | Tasks | Points |
|-------|-------|--------|
| Phase 1: Setup (Shared Infrastructure) | 2 | 3 |
| Phase 2: Foundational (Blocking Prerequisites) | 2 | 6 |
| Phase 3: User Story 1 - Deterministic Phase Completion | 4 | 12 |
| Phase 4: User Story 2 - Permissioned Phase Start | 4 | 10 |
| Phase 5: User Story 3 - Producer-Only Command Contracts | 4 | 9 |
| Phase 6: Polish & Cross-Cutting Concerns | 2 | 5 |
| Total | 18 | 45 |

## Warnings

- These estimates assume the current sketch stays stable and the driver-owned phase contract does not reopen major sequencing decisions.
- If the manifest or ledger sequence changes again, the story points for the orchestration tasks may move up.
