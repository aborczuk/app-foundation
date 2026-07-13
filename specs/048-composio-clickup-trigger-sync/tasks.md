---

description: "Task list for Composio ClickUp trigger sync"
---

# Tasks: composio clickup trigger sync

**Input**: Design documents from `/specs/048-composio-clickup-trigger-sync/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: Include focused unit/integration coverage because this feature changes sync, trigger, and closeout control paths.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/`, `scripts/`, and `docs/` at repository root

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new Composio transport and trigger surfaces without changing runtime behavior yet.

**Independent Test**: Import the scaffold modules, run the trigger CLI in scaffold mode, and verify the current ClickUp runtime path remains unchanged.

- [X] T001 Create the Composio transport and trigger scaffolds in src/mcp_clickup/composio_adapter.py and scripts/speckit_clickup_trigger.py
- [ ] T002 [P] Create the initial unit-test scaffolds in tests/unit/mcp_clickup/test_composio_adapter.py and tests/unit/test_speckit_clickup_trigger.py

**Checkpoint**: The new adapter and trigger modules exist and the test layout is ready for implementation.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the shared projection, mapping, and orchestration seams that every story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

**Independent Test**: Parse stabilized feature artifacts into the shared model, persist mapping state, and confirm sync and implement orchestration can consume the new seams without the direct-transport dependency.

- [ ] T003 Extend the ClickUp projection data model in src/mcp_clickup/__init__.py and src/mcp_clickup/artifact_parser.py to carry acceptance criteria, story labels, parallel markers, estimates, and artifact links
- [ ] T004 Persist stable repo-to-ClickUp mapping state in src/mcp_clickup/manifest.py and tests/unit/mcp_clickup/test_manifest.py for richer feature/task projections
- [ ] T005 Refactor sync orchestration to depend on a transport adapter instead of the direct ClickUp client in src/mcp_clickup/sync_engine.py and src/mcp_clickup/__main__.py
- [ ] T006 Expose explicit mapped-task start eligibility helpers in scripts/speckit_implement_step.py and scripts/task_ledger.py for ClickUp-triggered work

**Checkpoint**: Projection, mapping, and orchestration seams are in place for sync, trigger, and closeout work.

---

## Phase 3: User Story 1 - Sync stabilized feature work to ClickUp (Priority: P1) 🎯 MVP

**Goal**: Publish stabilized repo features and executable tasks to ClickUp through Composio with durable mapping continuity.

**Independent Test**: Stabilize one feature with multiple executable tasks and verify that one ClickUp list and the expected mapped task set appear with the required metadata.

### Acceptance Criteria

- Sync creates or updates exactly one ClickUp list per stabilized feature with feature identity plus spec, plan, and slice context.
- Sync creates or updates one mapped ClickUp task per stabilized executable repo task with title, acceptance criteria, story relationship, parallel indicator, estimate, and canonical repo links.
- Re-running sync after stabilized task metadata changes updates existing mapped ClickUp items in place instead of duplicating them.

### Tests for User Story 1

- [ ] T007 [P] [US1] Add projection parsing regression coverage in tests/unit/mcp_clickup/test_artifact_parser.py and tests/unit/mcp_clickup/test_manifest.py
- [ ] T008 [P] [US1] Add idempotent sync orchestration coverage in tests/unit/mcp_clickup/test_sync_engine.py and tests/unit/mcp_clickup/test_composio_adapter.py

### Implementation for User Story 1

- [ ] T009 [US1] Implement canonical feature/task projection extraction in src/mcp_clickup/artifact_parser.py and src/mcp_clickup/__init__.py from stabilized spec, plan, tasks, and mapping artifacts
- [ ] T010 [US1] Implement stable mapping updates for feature lists and mapped tasks in src/mcp_clickup/manifest.py and src/mcp_clickup/sync_engine.py
- [ ] T011 [US1] Implement the Composio-backed create/update/read transport in src/mcp_clickup/composio_adapter.py and src/mcp_clickup/sync_engine.py
- [ ] T012 [US1] Wire post-stabilization ClickUp sync into the solution/tasking finalize path in scripts/speckit_solution_step.py and src/mcp_clickup/__main__.py

**Checkpoint**: Stabilized feature work is visible in ClickUp through the new Composio sync path without duplicate mappings.

---

## Phase 4: User Story 2 - Start implement work from ClickUp without bypassing repo gates (Priority: P2)

**Goal**: Allow a mapped ClickUp task to request implementation via `ready-for-implement` while keeping ledger gating authoritative.

**Independent Test**: Issue one eligible and one ineligible ClickUp start request and verify that only the eligible task enters implement flow.

### Acceptance Criteria

- A mapped ClickUp task moved to `ready-for-implement` starts normal repo implement flow only when the mapped repo task is ledger-eligible.
- A mapped ClickUp task that is not ledger-eligible does not start work and receives a clear rejection reason back in ClickUp.
- A trigger request that cannot resolve to exactly one repo feature/task mapping is rejected without changing ledger state.

### Tests for User Story 2

- [ ] T013 [P] [US2] Add trigger eligibility coverage for eligible, blocked, and ambiguous mappings in tests/unit/test_speckit_implement_step.py and tests/unit/test_speckit_clickup_trigger.py

### Implementation for User Story 2

- [ ] T014 [US2] Implement mapped-task resolution and ready-for-implement status handling in scripts/speckit_clickup_trigger.py and src/mcp_clickup/manifest.py
- [ ] T015 [US2] Reuse ledger-gated task-start selection for explicit feature/task requests in scripts/speckit_implement_step.py and scripts/task_ledger.py
- [ ] T016 [US2] Write blocked or ambiguous start-request rejection reasons back through Composio in scripts/speckit_clickup_trigger.py and src/mcp_clickup/composio_adapter.py

**Checkpoint**: ClickUp can request work, but repo gating remains the only authority for whether work starts.

---

## Phase 5: User Story 3 - Reflect successful closeout back to ClickUp (Priority: P3)

**Goal**: Mark mapped ClickUp tasks done after successful repo closeout without weakening repo authority on completion.

**Independent Test**: Close out one synced repo task and verify that the mapped ClickUp task transitions to done while transport failures remain retryable.

### Acceptance Criteria

- Successful repo closeout updates the mapped ClickUp task to done through Composio.
- A ClickUp transport failure during closeout reflection does not roll back repo completion and is surfaced for retry.

### Tests for User Story 3

- [ ] T017 [P] [US3] Add closeout reflection coverage for success and retryable transport failure in tests/unit/test_speckit_closeout_task.py and tests/unit/test_speckit_implement_step.py

### Implementation for User Story 3

- [ ] T018 [US3] Update closeout to mark mapped ClickUp tasks done through Composio in scripts/speckit_closeout_task.py and src/mcp_clickup/composio_adapter.py
- [ ] T019 [US3] Surface post-closeout sync failures without rolling back repo completion in scripts/speckit_implement_step.py and scripts/speckit_closeout_task.py

**Checkpoint**: Repo closeout remains authoritative and ClickUp completion becomes a reliable post-closeout side effect.

---

## Phase 6: User Story 4 - Preserve repo authority when ClickUp and repo drift (Priority: P4)

**Goal**: Detect and report drift safely so external ClickUp edits do not become a second execution authority.

**Independent Test**: Force ClickUp state to conflict with repo ledger state and verify that sync or trigger evaluation reports drift instead of accepting invalid work.

### Acceptance Criteria

- When ClickUp marks a task ready or done while the repo ledger disagrees, sync or trigger evaluation reports the mismatch and repo state wins.
- When a previously synced task no longer exists in the stabilized repo task graph, sync reconciles the mapping without creating a second authoritative task source.

### Tests for User Story 4

- [ ] T020 [P] [US4] Add drift and reconciliation regression coverage for sync and trigger paths in tests/unit/mcp_clickup/test_sync_engine.py and tests/unit/test_speckit_clickup_trigger.py

### Implementation for User Story 4

- [ ] T021 [US4] Detect and report mapping drift when ClickUp state disagrees with repo state in src/mcp_clickup/sync_engine.py and scripts/speckit_clickup_trigger.py
- [ ] T022 [US4] Reconcile removed or changed repo tasks without creating a second authority in src/mcp_clickup/manifest.py and src/mcp_clickup/sync_engine.py
- [ ] T023 [US4] Retire direct ClickUp transport runtime paths and update the operator doc in src/mcp_clickup/clickup_client.py, src/mcp_clickup/__main__.py, and docs/architecture/mcp-clickup.md

**Checkpoint**: Drift is surfaced deterministically and the repo remains authoritative when ClickUp state diverges.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Run focused validation and update the operator-facing architecture docs for the new flow.

**Independent Test**: Run the focused regression suite and confirm the operator docs describe the shipped Composio sync, trigger, and closeout flow without stale direct-transport guidance.

- [ ] T024 [P] Run focused sync, trigger, and closeout validation in tests/unit/mcp_clickup/test_artifact_parser.py, tests/unit/mcp_clickup/test_manifest.py, tests/unit/mcp_clickup/test_sync_engine.py, tests/unit/test_speckit_clickup_trigger.py, and tests/unit/test_speckit_closeout_task.py
- [ ] T025 Update operator/runtime documentation for Composio-owned ClickUp sync, trigger, and closeout behavior in docs/architecture/mcp-clickup.md and docs/architecture/workflow-overview.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in priority order (P1 → P2 → P3 → P4)
  - Limited parallelism is possible only where tasks are marked `[P]`
- **Polish (Phase 7)**: Depends on the desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Must land first because it establishes projection, mapping, and Composio sync publication
- **User Story 2 (P2)**: Depends on US1 mappings and the foundational start-eligibility helpers
- **User Story 3 (P3)**: Depends on US1 mappings and the existing repo closeout path
- **User Story 4 (P4)**: Depends on US1/US2 sync and trigger behavior so drift can be evaluated against real mappings

### Within Each User Story

- Tests should fail before the corresponding implementation tasks are completed
- Projection and mapping changes should land before transport orchestration changes
- Trigger path changes should reuse existing ledger gating rather than bypass it
- Closeout reflection should run only after repo closeout semantics are preserved
- Legacy direct-transport removal should happen only after Composio parity coverage exists

### Parallel Opportunities

- T002 can run in parallel with T001 after the file scaffolds are chosen
- T007 and T008 can run in parallel within US1
- T013, T017, and T020 are independent story-test tasks once foundational seams are ready
- T024 can run in parallel across the listed validation files once implementation is complete

---

## Parallel Example: User Story 1

```bash
# Launch US1 tests together:
Task: "T007 Add projection parsing regression coverage in tests/unit/mcp_clickup/test_artifact_parser.py and tests/unit/mcp_clickup/test_manifest.py"
Task: "T008 Add idempotent sync orchestration coverage in tests/unit/mcp_clickup/test_sync_engine.py and tests/unit/mcp_clickup/test_composio_adapter.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Validate that stabilized features sync to ClickUp without duplicate mappings

### Incremental Delivery

1. Land US1 sync publication
2. Add US2 ready-for-implement trigger routing
3. Add US3 closeout reflection
4. Add US4 drift handling and legacy transport retirement
5. Finish with cross-cutting validation and docs

### Parallel Team Strategy

1. Pair on Phase 2 foundational seams
2. Split after foundational work:
   - Engineer A: US1 sync publication
   - Engineer B: US2 trigger gating
   - Engineer C: US3 closeout reflection and US4 drift handling
3. Rejoin for legacy cleanup and validation

---

## Notes

- `[P]` tasks = different files, no dependencies
- `[USn]` label maps task to a specific user story for traceability
- Each user story should remain independently testable
- Task descriptions intentionally name exact file paths but do not precompute code seams
- The repo ledger remains authoritative for task ordering, start eligibility, and closeout
