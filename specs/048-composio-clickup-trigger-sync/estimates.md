# Effort Estimate: Composio ClickUp Trigger Sync

**Date**: 2026-07-12 | **Total Points**: 75 | **T-shirt Size**: L
**Estimated by**: AI (speckit.estimate) — calibrate against actuals after implementation

---

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T001 | 1 | Create the Composio transport and trigger scaffolds | New-file scaffolding only, no live behavior yet |
| T002 | 1 | Create the initial unit-test scaffolds | Test-file scaffolding only |
| T003 | 3 | Extend the ClickUp projection data model | Moderate parser/model extension across two existing files |
| T004 | 3 | Persist stable repo-to-ClickUp mapping state | Moderate manifest/schema adjustment with existing pattern reuse |
| T005 | 5 | Refactor sync orchestration to depend on a transport adapter | Multi-file orchestration refactor across runtime and engine seams |
| T006 | 3 | Expose explicit mapped-task start eligibility helpers | Moderate change inside existing implement/ledger flow |
| T007 | 2 | Add projection parsing regression coverage | Straightforward tests against known parser seams |
| T008 | 3 | Add idempotent sync orchestration coverage | Multi-file test coverage for orchestration and adapter behavior |
| T009 | 3 | Implement canonical feature/task projection extraction | Moderate logic in known parser/model seams |
| T010 | 3 | Implement stable mapping updates | Moderate mapping/reconciliation logic in existing files |
| T011 | 5 | Implement the Composio-backed create/update/read transport | New adapter with external integration uncertainty |
| T012 | 5 | Wire post-stabilization ClickUp sync into solution/tasking finalize | Crosses workflow and sync runtime boundaries |
| T013 | 3 | Add trigger eligibility coverage | Multi-case tests across implement and trigger seams |
| T014 | 3 | Implement mapped-task resolution and ready-for-implement handling | Moderate trigger orchestration with mapping lookups |
| T015 | 5 | Reuse ledger-gated task-start selection for explicit feature/task requests | High-risk change in start-selection behavior across scripts |
| T016 | 3 | Write blocked or ambiguous rejection reasons back through Composio | Moderate trigger-to-transport behavior with known patterns |
| T017 | 2 | Add closeout reflection coverage | Focused tests on existing closeout path |
| T018 | 3 | Update closeout to mark mapped ClickUp tasks done | Moderate closeout integration using existing script flow |
| T019 | 2 | Surface post-closeout sync failures without rollback | Small but important error-path adjustment |
| T020 | 2 | Add drift and reconciliation regression coverage | Focused regression tests on known sync/trigger seams |
| T021 | 3 | Detect and report mapping drift | Moderate reconciliation logic in existing orchestration files |
| T022 | 3 | Reconcile removed or changed repo tasks | Moderate manifest and sync-engine reconciliation behavior |
| T023 | 5 | Retire direct ClickUp transport runtime paths and update the operator doc | Multi-file cleanup with behavior-preservation risk |
| T024 | 2 | Run focused sync, trigger, and closeout validation | Straightforward validation pass across known tests |
| T025 | 2 | Update operator/runtime documentation | Limited-scope doc update across known architecture docs |

---

### T003 — Solution Sketch

**Modify**: `src/mcp_clickup/__init__.py`, `src/mcp_clickup/artifact_parser.py` — extend task/spec models and parsing outputs for richer task metadata
**Create**: none
**Reuse**: existing `Task`, `TaskGroup`, and `SpecArtifact` parsing pattern
**Composition**: parser emits richer projections that later sync and trigger steps can consume
**Failing test assertion**: parsed task projections include acceptance criteria, story labels, estimate, and artifact-link fields
**Domains touched**: `02_data_modeling_schemas.md`, `17_code_patterns.md`

### T004 — Solution Sketch

**Modify**: `src/mcp_clickup/manifest.py`, `tests/unit/mcp_clickup/test_manifest.py` — evolve mapping persistence without breaking canonical keys
**Create**: none
**Reuse**: existing atomic manifest load/save helpers
**Composition**: richer mapping state remains the single repo-owned authority for external IDs
**Failing test assertion**: manifest round-trips richer mapping fields and preserves stable identifiers
**Domains touched**: `02_data_modeling_schemas.md`, `11_resilience_continuity.md`

### T005 — Solution Sketch

**Modify**: `src/mcp_clickup/sync_engine.py`, `src/mcp_clickup/__main__.py` — invert orchestration away from the direct ClickUp client
**Create**: none
**Reuse**: existing sync-engine reconciliation and runtime entrypoint structure
**Composition**: sync orchestration talks to an adapter protocol, not the direct API client
**Failing test assertion**: sync orchestration can run against the adapter seam without direct-client-only assumptions
**Domains touched**: `01_api_integration.md`, `11_resilience_continuity.md`, `17_code_patterns.md`

### T006 — Solution Sketch

**Modify**: `scripts/speckit_implement_step.py`, `scripts/task_ledger.py` — expose explicit eligibility checks for mapped task requests
**Create**: none
**Reuse**: current `_select_next_registered_task` and ledger evaluation rules
**Composition**: trigger flow resolves feature/task explicitly, then reuses the existing ledger gate
**Failing test assertion**: explicit mapped-task requests follow the same eligibility outcomes as normal implement selection
**Domains touched**: `11_resilience_continuity.md`, `12_testing_quality_gates.md`, `17_code_patterns.md`

### T008 — Solution Sketch

**Modify**: `tests/unit/mcp_clickup/test_sync_engine.py`, `tests/unit/mcp_clickup/test_composio_adapter.py` — cover idempotent sync and adapter behavior
**Create**: `tests/unit/mcp_clickup/test_composio_adapter.py`
**Reuse**: existing sync-engine unit-test style
**Composition**: tests pin the new adapter/orchestration contract before implementation expands
**Failing test assertion**: repeated sync updates existing mappings rather than duplicating lists/tasks
**Domains touched**: `01_api_integration.md`, `12_testing_quality_gates.md`

### T009 — Solution Sketch

**Modify**: `src/mcp_clickup/artifact_parser.py`, `src/mcp_clickup/__init__.py` — emit canonical projections from stabilized repo artifacts
**Create**: none
**Reuse**: existing artifact discovery and grouped task parsing flow
**Composition**: richer parser output feeds sync, trigger, and closeout mapping behavior
**Failing test assertion**: a stabilized feature yields canonical task projections with the required metadata
**Domains touched**: `02_data_modeling_schemas.md`, `17_code_patterns.md`

### T010 — Solution Sketch

**Modify**: `src/mcp_clickup/manifest.py`, `src/mcp_clickup/sync_engine.py` — update mapping records in place during re-sync
**Create**: none
**Reuse**: current manifest-key generation and sync-engine reconciliation path
**Composition**: list/task mapping updates remain idempotent while richer projections are introduced
**Failing test assertion**: metadata changes update the existing mapped objects instead of creating duplicates
**Domains touched**: `01_api_integration.md`, `11_resilience_continuity.md`

### T011 — Solution Sketch

**Modify**: `src/mcp_clickup/composio_adapter.py`, `src/mcp_clickup/sync_engine.py` — implement managed transport operations for create/update/read
**Create**: `src/mcp_clickup/composio_adapter.py`
**Reuse**: sync-engine client protocol boundary and existing error-surfacing pattern
**Composition**: Composio transport satisfies the engine protocol while keeping transport concerns isolated
**Failing test assertion**: adapter operations return the normalized task/list payloads the sync engine expects
**Domains touched**: `01_api_integration.md`, `11_resilience_continuity.md`, `14_security_controls.md`

### T012 — Solution Sketch

**Modify**: `scripts/speckit_solution_step.py`, `src/mcp_clickup/__main__.py` — trigger ClickUp publication only after stabilization and registration
**Create**: none
**Reuse**: current solution finalize path and runtime sync entrypoint
**Composition**: finalized task graphs call the sync hook as a deterministic post-stabilization side effect
**Failing test assertion**: ClickUp publication does not run before the task graph is settled and registered
**Domains touched**: `01_api_integration.md`, `16_ops_governance.md`, `17_code_patterns.md`

### T013 — Solution Sketch

**Modify**: `tests/unit/test_speckit_implement_step.py`, `tests/unit/test_speckit_clickup_trigger.py` — cover eligible, blocked, and ambiguous requests
**Create**: `tests/unit/test_speckit_clickup_trigger.py`
**Reuse**: existing implement-step test patterns
**Composition**: tests pin the start-routing behavior before trigger integration lands
**Failing test assertion**: only eligible mapped tasks enter implement flow; blocked and ambiguous requests do not mutate ledger state
**Domains touched**: `12_testing_quality_gates.md`, `17_code_patterns.md`

### T014 — Solution Sketch

**Modify**: `scripts/speckit_clickup_trigger.py`, `src/mcp_clickup/manifest.py` — resolve mapped tasks and handle ready-for-implement status transitions
**Create**: `scripts/speckit_clickup_trigger.py`
**Reuse**: manifest mapping records and existing script-owned workflow style
**Composition**: trigger flow resolves the external task, then delegates eligibility and reporting
**Failing test assertion**: ready-for-implement requests resolve to the correct repo feature/task pair or fail explicitly
**Domains touched**: `01_api_integration.md`, `14_security_controls.md`, `17_code_patterns.md`

### T015 — Solution Sketch

**Modify**: `scripts/speckit_implement_step.py`, `scripts/task_ledger.py` — expose explicit task-start routing without weakening ledger rules
**Create**: none
**Reuse**: existing task-state parsing and `evaluate_start_task` semantics
**Composition**: implement orchestration accepts explicit mapped-task requests while preserving the same gating rules
**Failing test assertion**: explicit task-start requests honor dependency ordering, ownership, and resume rules exactly like the default implement path
**Domains touched**: `11_resilience_continuity.md`, `12_testing_quality_gates.md`, `17_code_patterns.md`

### T016 — Solution Sketch

**Modify**: `scripts/speckit_clickup_trigger.py`, `src/mcp_clickup/composio_adapter.py` — write rejection reasons back through the managed transport
**Create**: none
**Reuse**: adapter write/update patterns from sync behavior
**Composition**: blocked trigger requests surface actionable feedback to ClickUp without touching repo state
**Failing test assertion**: blocked or ambiguous requests produce a human-readable external rejection update
**Domains touched**: `01_api_integration.md`, `11_resilience_continuity.md`

### T018 — Solution Sketch

**Modify**: `scripts/speckit_closeout_task.py`, `src/mcp_clickup/composio_adapter.py` — add the mapped-task done update after successful closeout
**Create**: none
**Reuse**: existing structured closeout result and post-closeout orchestration
**Composition**: repo closeout stays first; external done reflection happens only after success
**Failing test assertion**: successful closeout emits the external done update without changing repo authority rules
**Domains touched**: `01_api_integration.md`, `11_resilience_continuity.md`, `17_code_patterns.md`

### T021 — Solution Sketch

**Modify**: `src/mcp_clickup/sync_engine.py`, `scripts/speckit_clickup_trigger.py` — detect and surface drift across sync and trigger entrypoints
**Create**: none
**Reuse**: existing reconciliation behavior and mapping state
**Composition**: both publication and trigger evaluation fail closed when external state disagrees with repo state
**Failing test assertion**: conflicting external ready/done state is reported and does not override repo state
**Domains touched**: `11_resilience_continuity.md`, `14_security_controls.md`

### T022 — Solution Sketch

**Modify**: `src/mcp_clickup/manifest.py`, `src/mcp_clickup/sync_engine.py` — reconcile removed or changed repo tasks against prior mappings
**Create**: none
**Reuse**: current manifest keying and discovery/rebuild logic
**Composition**: re-sync resolves stale mappings instead of spawning a second authority
**Failing test assertion**: removed or changed tasks reconcile cleanly without duplicate external ownership
**Domains touched**: `02_data_modeling_schemas.md`, `11_resilience_continuity.md`

### T023 — Solution Sketch

**Modify**: `src/mcp_clickup/clickup_client.py`, `src/mcp_clickup/__main__.py`, `docs/architecture/mcp-clickup.md` — retire direct-transport runtime use and document the new boundary
**Create**: none
**Reuse**: existing docs and runtime entrypoint structure
**Composition**: direct API runtime use becomes inactive once Composio parity is verified and documented
**Failing test assertion**: runtime sync/trigger behavior no longer depends on direct ClickUp token-based transport
**Domains touched**: `01_api_integration.md`, `16_ops_governance.md`, `17_code_patterns.md`

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 2 | 2 | 1 |
| Phase 2: Foundational | 14 | 4 | 0 |
| Phase 3: User Story 1 | 21 | 6 | 2 |
| Phase 4: User Story 2 | 14 | 4 | 1 |
| Phase 5: User Story 3 | 7 | 3 | 1 |
| Phase 6: User Story 4 | 13 | 4 | 1 |
| Phase 7: Polish | 4 | 2 | 1 |
| **Total** | **75** | **25** | **7** |

---

## Warnings

- No tasks are currently estimated at 8 or 13.
- Phase 2 has no parallel opportunities because projection, manifest, adapter refactor, and eligibility helpers are blocking seams.
- Highest-uncertainty tasks: T011, T012, T015, and T023 due to Composio transport behavior and runtime migration scope.
- Async lifecycle guard coverage: no additional async worker lifecycle tasks were identified for this feature.
- State-safety coverage: drift and reconciliation coverage is explicitly tracked in T020, T021, and T022.
- Transaction-integrity coverage: not applicable because this feature does not introduce new local DB mutation authority.
