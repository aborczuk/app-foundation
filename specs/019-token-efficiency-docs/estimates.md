# Effort Estimate: Deterministic Pipeline Driver with LLM Handoff

**Date**: 2026-04-11 | **Total Points**: 117 | **T-shirt Size**: L
**Estimated by**: AI (speckit.estimate) — calibrate against actuals after implementation
**Revision note**: Incorporates solutionreview DRY/reuse decisions (shared status contract primitives + shared integration harness).

---

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T000 | 1 | Record External Ingress + Runtime Readiness Gate as N/A (CLI-only feature) in specs/019-token-efficiency-docs/tasks.md | Bounded single-scope change using existing patterns. |
| T001 | 3 | Build initial command-to-script coverage inventory from command-manifest.yaml and .specify/command-manifest.yaml into docs/governance/command-script-coverage.md:coverage_matrix | Touches orchestration boundaries and deterministic control-flow contracts. |
| T002 | 3 | Create orchestrator module skeletons in scripts/pipeline_driver.py:main, scripts/pipeline_driver_state.py:resolve_phase_state, scripts/pipeline_driver_contracts.py:parse_step_result | Touches orchestration boundaries and deterministic control-flow contracts. |
| T003 | 2 | Create test module skeletons in tests/unit/test_pipeline_driver.py, tests/integration/test_pipeline_driver_feature_flow.py, tests/contract/test_pipeline_driver_contract.py | Deterministic regression coverage for route and contract behavior. |
| T004 | 3 | Implement manifest route loader and mode normalization in scripts/pipeline_driver_contracts.py:load_driver_routes | Touches orchestration boundaries and deterministic control-flow contracts. |
| T005 | 3 | Implement feature lock acquire/release/stale-owner handling in scripts/pipeline_driver_state.py:acquire_feature_lock | Touches orchestration boundaries and deterministic control-flow contracts. |
| T006 | 3 | Implement ledger-authoritative phase resolver and drift detection in scripts/pipeline_driver_state.py:resolve_phase_state | Touches orchestration boundaries and deterministic control-flow contracts. |
| T007 | 5 | Implement deterministic step executor with timeout/cancel and exit-code routing in scripts/pipeline_driver.py:run_step | Touches orchestration boundaries and deterministic control-flow contracts. |
| T008 | 3 | Implement mandatory `exit_code=2` verbose rerun + sidecar persistence in scripts/pipeline_driver.py:handle_runtime_failure | Touches orchestration boundaries and deterministic control-flow contracts. |
| T009 | 2 | Create shared status contract constants + renderer in scripts/pipeline_driver_contracts.py (`STATUS_KEYS`, `STATUS_PREFIXES`, `render_status_lines`) as the only source for human status output | Bounded single-scope change using existing patterns. |
| T010 | 2 | Implement run-scoped correlation ID propagation helper in scripts/pipeline_driver.py:build_correlation_id | Bounded single-scope change using existing patterns. |
| T011 | 3 | Implement command coverage validator in scripts/validate_command_script_coverage.py:main | Touches orchestration boundaries and deterministic control-flow contracts. |
| T012 | 2 | Wire coverage validator into governance checks in scripts/validate_doc_graph.sh:run_validators and scripts/validate_constitution_sync.sh:run_checks | Bounded single-scope change using existing patterns. |
| T013 | 3 | Build shared integration flow harness in tests/integration/conftest.py:driver_flow_harness and add drift/idempotency coverage in tests/integration/test_pipeline_driver_feature_flow.py:test_reconcile_and_retry_guards using that harness | Deterministic regression coverage for route and contract behavior. |
| T014 | 3 | Add mapped-success routing integration test in tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_success using shared harness fixture (no duplicated setup) | Deterministic regression coverage for route and contract behavior. |
| T015 | 3 | Add mapped-blocked routing integration test with gate/reasons assertions in tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_blocked using shared harness fixture (no duplicated setup) | Deterministic regression coverage for route and contract behavior. |
| T016 | 2 | Add generative-step handoff contract unit test in tests/unit/test_pipeline_driver.py:test_handoff_contract | Deterministic regression coverage for route and contract behavior. |
| T017 | 3 | Implement command-to-script allowlist dispatch from command-manifest.yaml in scripts/pipeline_driver.py:resolve_step_mapping | Touches orchestration boundaries and deterministic control-flow contracts. |
| T018 | 3 | Implement legacy fallback for non-driver-managed phases in scripts/pipeline_driver.py:route_legacy_step | Touches orchestration boundaries and deterministic control-flow contracts. |
| T019 | 3 | Implement post-LLM artifact validation before success event append in scripts/pipeline_driver.py:validate_generated_artifact | Touches orchestration boundaries and deterministic control-flow contracts. |
| T020 | 3 | Update routing metadata and driver-managed flags in command-manifest.yaml:commands and .specify/command-manifest.yaml:commands | Touches orchestration boundaries and deterministic control-flow contracts. |
| T021 | 3 | Add contract tests for canonical result envelope (`exit_code` 0/1/2) in tests/contract/test_pipeline_driver_contract.py:test_step_result_schema | Deterministic regression coverage for route and contract behavior. |
| T022 | 3 | Add runtime-failure verbose-rerun integration test in tests/integration/test_pipeline_driver_feature_flow.py:test_runtime_failure_verbose_rerun using shared harness fixture and sidecar assertions | Deterministic regression coverage for route and contract behavior. |
| T023 | 3 | Implement canonical envelope parsing + schema-version compatibility in scripts/pipeline_driver_contracts.py:parse_step_result and define shared route/error contract constants consumed by deterministic handlers | Touches orchestration boundaries and deterministic control-flow contracts. |
| T024 | 3 | Implement default stdout suppression and three-line status emission in scripts/pipeline_driver.py:emit_human_status by consuming shared status contract constants from scripts/pipeline_driver_contracts.py | Touches orchestration boundaries and deterministic control-flow contracts. |
| T025 | 3 | Implement explicit diagnostics drill-down command in scripts/pipeline_driver.py:drill_down_failure | Touches orchestration boundaries and deterministic control-flow contracts. |
| T026 | 2 | Align contract docs and operator runbook in specs/019-token-efficiency-docs/contracts/orchestrator-step-result.schema.json and specs/019-token-efficiency-docs/quickstart.md | Bounded single-scope change using existing patterns. |
| T027 | 3 | Add mixed-migration integration regression in tests/integration/test_pipeline_driver_feature_flow.py:test_mixed_migration_mode using shared harness fixture to avoid duplicate route/bootstrap logic | Deterministic regression coverage for route and contract behavior. |
| T028 | 2 | Add manifest-governance regression for version/timestamp coupling in tests/unit/test_pipeline_driver.py:test_manifest_governance_guard | Deterministic regression coverage for route and contract behavior. |
| T029 | 3 | Implement deterministic command coverage report (missing scripts/modes) in scripts/validate_command_script_coverage.py:build_coverage_report | Touches orchestration boundaries and deterministic control-flow contracts. |
| T030 | 3 | Add solution/tasking gate check for uncovered command mappings in scripts/speckit_gate_status.py:validate_command_coverage | Touches orchestration boundaries and deterministic control-flow contracts. |
| T031 | 3 | Extend manifest validation invariants for coverage enforcement in scripts/pipeline_ledger.py:cmd_validate_manifest | Touches orchestration boundaries and deterministic control-flow contracts. |
| T032 | 2 | Document migration/rollback and coverage ownership policy in docs/governance/command-script-coverage.md and specs/019-token-efficiency-docs/research.md | Bounded single-scope change using existing patterns. |
| T033 | 1 | Run task-format and plan gates on finalized artifacts via scripts/speckit_tasks_gate.py and scripts/speckit_gate_status.py | Bounded single-scope change using existing patterns. |
| T034 | 2 | Run dry-run orchestration scenario and capture evidence in scripts/e2e_020.sh and specs/019-token-efficiency-docs/quickstart.md | Bounded single-scope change using existing patterns. |
| T035 | 1 | Run lint/type checks for touched workflow files in scripts/pipeline_driver.py, scripts/pipeline_driver_contracts.py, scripts/validate_command_script_coverage.py | Bounded single-scope change using existing patterns. |
| T045 | 5 | Wire generative handoff execution adapter in scripts/pipeline_driver.py:main to call an LLM handoff runner and capture generated artifact output metadata | Crosses orchestrator-to-generation boundary and introduces execution/contract plumbing in the main dispatch path. |
| T046 | 3 | Invoke post-generation artifact validation in scripts/pipeline_driver.py:main via validate_generated_artifact before returning success for generative routes | Medium integration change that reuses validator primitive but must route blocked/success outcomes deterministically. |
| T047 | 3 | Append success event and phase advancement for validated generative outputs in scripts/pipeline_driver.py:main using scripts/pipeline_ledger.py event contracts | Medium orchestration change touching ledger/state transition invariants with existing event contract reuse. |
| T048 | 3 | Add preflight branch-sync stale-contract guard in scripts/speckit_implement_gate.py:_task_preflight (with reason-code mapping in docs/governance/gate-reason-codes.yaml) so `.implement` blocks when target task exists on `main` but not current feature branch | Medium governance/flow guard touching git-state preflight logic plus deterministic reason-code routing and regression checks. |
| T049 | 2 | Wire add-to-backlog pipeline event emission by updating .claude/commands/speckit.addtobacklog.md and .specify/command-manifest.yaml so `/speckit.addtobacklog` emits `backlog_registered` via scripts/pipeline_ledger.py | Small contract-alignment update across command workflow and manifest metadata with deterministic event reuse. |
| T050 | 3 | Route add-to-backlog triage outcomes to the appropriate downstream phase by estimate/scope in .claude/commands/speckit.addtobacklog.md (specify/plan/solution/implement handoff guidance) | Medium workflow-contract update that changes command routing semantics and must preserve deterministic phase handoff behavior. |
| T051 | 3 | Project and emit prerequisite pipeline events from /speckit.addtobacklog so ledger readiness matches selected `NEXT_COMMAND` in .claude/commands/speckit.addtobacklog.md and .specify/command-manifest.yaml | Medium cross-phase contract update that must preserve deterministic event order and required event payload fields across multiple pipeline stages. |

---

### T000 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T001 — Solution Sketch

**Modify**: `n/a` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 16, Domain 13, Domain 14, Domain 17

### T002 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:main` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T003 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T004 — Solution Sketch

**Modify**: `scripts/pipeline_driver_contracts.py:load_driver_routes` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T005 — Solution Sketch

**Modify**: `scripts/pipeline_driver_state.py:acquire_feature_lock` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T006 — Solution Sketch

**Modify**: `scripts/pipeline_driver_state.py:resolve_phase_state` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T007 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:run_step` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T008 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:handle_runtime_failure` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T009 — sketch: focused

**Modify**: `scripts/pipeline_driver_contracts.py:render_status_lines`.
**Create**: shared status contract constants (`STATUS_KEYS`, `STATUS_PREFIXES`) in `scripts/pipeline_driver_contracts.py`.
**Reuse**: all orchestrator status emission paths consume these constants; no inline status literals permitted.

### T010 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T011 — Solution Sketch

**Modify**: `scripts/validate_command_script_coverage.py:main` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T012 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T013 — Solution Sketch

**Modify**: `tests/integration/test_pipeline_driver_feature_flow.py:test_reconcile_and_retry_guards` — add deterministic behavior required by task scope.
**Create**: `tests/integration/conftest.py:driver_flow_harness` fixture for feature sandbox setup, ledger seeding, invocation helper, and teardown.
**Reuse**: all integration route tests use `driver_flow_harness` to avoid duplicated setup and bootstrap logic.
**Composition**: harness owns common setup/cleanup; each test owns only scenario-specific assertions.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 12, Domain 13, Domain 14, Domain 17

### T014 — Solution Sketch

**Modify**: `tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_success` — add deterministic behavior required by task scope.
**Create**: `none` (consumes shared `driver_flow_harness` from T013).
**Reuse**: shared harness for feature setup/teardown and deterministic route invocation.
**Composition**: test owns only mapped-success assertions while harness owns bootstrap logic.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 12, Domain 13, Domain 14, Domain 17

### T015 — Solution Sketch

**Modify**: `tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_blocked` — add deterministic behavior required by task scope.
**Create**: `none` (consumes shared `driver_flow_harness` from T013).
**Reuse**: shared harness for feature setup/teardown and deterministic route invocation.
**Composition**: test owns only blocked-path gate/reason assertions while harness owns bootstrap logic.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 12, Domain 13, Domain 14, Domain 17

### T016 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T017 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:resolve_step_mapping` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 16, Domain 07, Domain 13, Domain 14, Domain 17

### T018 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:route_legacy_step` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T019 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:validate_generated_artifact` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T020 — Solution Sketch

**Modify**: `command-manifest.yaml:commands and .specify/command-manifest.yaml:commands` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 16, Domain 13, Domain 14, Domain 17

### T021 — Solution Sketch

**Modify**: `tests/contract/test_pipeline_driver_contract.py:test_step_result_schema` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 12, Domain 13, Domain 14, Domain 17

### T022 — Solution Sketch

**Modify**: `tests/integration/test_pipeline_driver_feature_flow.py:test_runtime_failure_verbose_rerun` — add deterministic behavior required by task scope.
**Create**: `none` (consumes shared `driver_flow_harness` from T013).
**Reuse**: shared harness plus deterministic sidecar assertion helpers.
**Composition**: runtime-failure scenario plugs into harness with `exit_code=2` and verbose-rerun expectations.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 12, Domain 13, Domain 14, Domain 17

### T023 — Solution Sketch

**Modify**: `scripts/pipeline_driver_contracts.py:parse_step_result` — add deterministic behavior required by task scope.
**Create**: shared route/error contract constants in `scripts/pipeline_driver_contracts.py` for gate/reason/error key names and status envelope composition.
**Reuse**: deterministic handlers in `pipeline_driver.py` consume shared constants to avoid duplicate contract strings.
**Composition**: parse + constant definitions are centralized; route handlers become thin consumers.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T024 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:emit_human_status` — add deterministic behavior required by task scope.
**Create**: `none` (consumes shared status constants/renderer from `pipeline_driver_contracts.py`).
**Reuse**: all success/blocked/tooling paths emit status via the shared renderer contract.
**Composition**: `emit_human_status` delegates to shared contract module; no duplicated prefix formatting.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T025 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:drill_down_failure` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T026 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T027 — Solution Sketch

**Modify**: `tests/integration/test_pipeline_driver_feature_flow.py:test_mixed_migration_mode` — add deterministic behavior required by task scope.
**Create**: `none` (reuse `driver_flow_harness` created by T013).
**Reuse**: shared fixture + helper assertions remove duplicate mixed-mode bootstrap logic.
**Composition**: mixed-migration scenario plugs into harness with mode overrides and invariant checks.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 12, Domain 13, Domain 14, Domain 17

### T028 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T029 — Solution Sketch

**Modify**: `scripts/validate_command_script_coverage.py:build_coverage_report` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T030 — Solution Sketch

**Modify**: `scripts/speckit_gate_status.py:validate_command_coverage` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T031 — Solution Sketch

**Modify**: `scripts/pipeline_ledger.py:cmd_validate_manifest` — add deterministic behavior required by task scope.
**Create**: `none` unless task scope explicitly requires a new helper or module.
**Reuse**: in-repo manifest/ledger/gate primitives where applicable; net-new logic only for orchestration glue.
**Composition**: keep a single manifest-allowlisted route path with exit-code-first control flow.
**Failing test assertion**: invalid preconditions return deterministic blocked/tooling outcome with stable reason fields.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T032 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T033 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T034 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T035 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T045 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:main` — execute generative handoff via runner adapter and normalize generated output metadata.
**Create**: optional helper for adapter invocation/normalization in `scripts/pipeline_driver.py` if needed for separation of concerns.
**Reuse**: existing mapping/handoff payload from `resolve_step_mapping`; existing step-result envelope contract.
**Composition**: dispatch generative mapping to adapter, collect artifact location + metadata, and keep canonical status output behavior unchanged.
**Failing test assertion**: generative path without runnable adapter returns deterministic blocked/tooling outcome with stable reason code.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T046 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:main` — call `validate_generated_artifact` after adapter output resolution.
**Create**: none unless helper extraction is needed for testability.
**Reuse**: `validate_generated_artifact` blocked envelope semantics and `artifact_validation` reason-code contract.
**Composition**: gate generative success on validator pass; route validator failures through normal blocked output contract.
**Failing test assertion**: missing/invalid generated artifact returns `exit_code=1`, `gate=artifact_validation`, and stable reason list.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T047 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:main` — append success event for validated generative step and advance/recompute next phase.
**Create**: optional helper in `scripts/pipeline_driver.py` for event append payload assembly.
**Reuse**: `scripts/pipeline_ledger.py` event contract fields and existing phase-resolution helpers.
**Composition**: after validator pass, emit required success event, then resolve/report next phase deterministically.
**Failing test assertion**: generative success path without ledger append reports deterministic failure instead of silent advancement.
**Domains touched**: Domain 07, Domain 13, Domain 14, Domain 17

### T048 — Solution Sketch

**Modify**: `scripts/speckit_implement_gate.py:_task_preflight` and `scripts/speckit_implement_gate.py:main` dispatch wiring.
**Create**: targeted helper for branch-sync task-presence check against `main` task contract.
**Reuse**: existing preflight reason emission (`task_not_found_in_tasks_md`, `missing_hud`) and deterministic gate payload structure.
**Composition**: detect branch/task divergence early, emit stable stale-branch reason code, and block implement before task execution starts.
**Failing test assertion**: preflight returns blocked result with stale-branch reason when task exists on `main` but is absent on the current feature branch.
**Domains touched**: Domain 16, Domain 13, Domain 14, Domain 17

### T050 — Solution Sketch

**Modify**: `.claude/commands/speckit.addtobacklog.md` triage/routing steps.
**Create**: no new script required for initial routing contract patch.
**Reuse**: existing estimate outcomes and phase command boundaries (`specify`, `plan`, `solution`, `implement`).
**Composition**: map triage + estimate signals to a single explicit next command so add-to-backlog hands off to the correct phase.
**Failing test assertion**: ambiguous or large-scope triage must not suggest direct implement; it must route to earlier phase command.
**Domains touched**: Domain 16, Domain 13, Domain 14, Domain 17

### T051 — Solution Sketch

**Modify**: `.claude/commands/speckit.addtobacklog.md` event emission and handoff readiness steps; `.specify/command-manifest.yaml` declared addtobacklog emits.
**Create**: no new script required; reuse existing `scripts/pipeline_ledger.py append`.
**Reuse**: existing phase transition event chain + required event fields from command manifest contracts.
**Composition**: determine `NEXT_COMMAND`, then append missing prerequisite events in deterministic order so ledger is ready even when addtobacklog does not auto-run the next phase command.
**Failing test assertion**: addtobacklog must not leave ledger missing prerequisite events for the selected next command readiness marker.
**Domains touched**: Domain 16, Domain 13, Domain 14, Domain 17

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup (Shared Infrastructure) | 9 | 4 | 1 |
| Phase 2: Foundational (Blocking Prerequisites) | 29 | 10 | 5 |
| Phase 3: User Story 1 - Deterministic Step Routing (Priority: P1) 🎯 MVP | 31 | 10 | 3 |
| Phase 4: User Story 2 - Compact Parsing Contract (Priority: P2) | 17 | 6 | 2 |
| Phase 5: User Story 3 - Governance and Migration Safety (Priority: P3) | 16 | 6 | 2 |
| Phase 6: Polish & Cross-Cutting Concerns | 15 | 7 | 2 |
| **Total** | **117** | **43** | **15** |

---

## Warnings

- No 8/13-point tasks detected; `/speckit.breakdown` not required.
- Refresh scoped codegraph index before implementation for newly introduced symbols.
- Keep command-manifest and `.specify/command-manifest.yaml` mirrors synchronized.
