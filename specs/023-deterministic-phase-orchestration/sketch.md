# Sketch Blueprint — Deterministic Phase Orchestration

_Date: 2026-04-20_
_Feature ID: 023_
_Feature Name: Deterministic Phase Orchestration_

---

## Feature Solution Frame

### Core Capability

Move phase execution into a deterministic driver contract where route selection, runtime envelope validation, and pipeline event append behavior are machine-enforced instead of doc-driven.

### Current → Target Transition

Current state mixes legacy command-doc orchestration with partial driver routing and sequence validation. Target state keeps command docs producer-oriented while `pipeline_driver.py` + `pipeline_driver_state.py` + `pipeline_ledger.py` own execution routing, state authority, and validate-before-emit guarantees.

### Dominant Execution Model

Deterministic orchestrator model: `orchestrate -> extract -> scaffold -> LLM Action -> validate -> emit/handoff`, with explicit approval and structured exit semantics.

### Main Design Pressures

- Preserve existing Speckit command surfaces while tightening deterministic enforcement.
- Keep pipeline ledger as source-of-truth without introducing conflicting local mirrors.
- Maintain backward compatibility for legacy transitions while enforcing new sequence rules.

---

## Solution Narrative

This sketch keeps the approved plan thesis intact: the driver is the execution authority, command docs remain production contracts, and event emission is downstream of deterministic validation. Implementation centers on strengthening existing scripts rather than introducing a new framework. The design slices split work across routing/state logic, transition validation, contract normalization, and regression verification so tasking can proceed without inventing architecture.

---

## Construction Strategy

1. Stabilize the routing contract from manifest to driver mode resolution (`legacy` vs `generative` vs deterministic envelope expectations).
2. Reinforce state authority and sequencing invariants (`resolve_phase_state`, `validate_sequence`, append rules).
3. Tighten success-event append behavior so event emission occurs only on validated success paths.
4. Align command docs and manifest language with producer-only contracts and driver-owned orchestration.
5. Lock behavior with integration/unit coverage over approval, sequencing, and migration-path regressions.

### Construction Notes

- Prioritize state/routing correctness before doc wording polish.
- Keep contract and manifest edits in the same slice to avoid drift windows.
- Treat codegraph relationship sparsity as a discovery constraint and avoid speculative dependency claims.

---

## Acceptance Traceability

| Story / Requirement / Constraint | Design Element(s) That Satisfy It | Reuse / Modify / Create | Verification / Migration Note |
|----------------------------------|-----------------------------------|-------------------------|-------------------------------|
| FR-001 / FR-007 / FR-008 / FR-009 | `run_step`, `append_pipeline_success_event`, `validate_sequence` | Modify | Add regression checks for validate-before-emit, no completion append on validation failure, and success append behavior. |
| FR-002 / FR-012 | `resolve_phase_state` ledger-derived phase resolution | Modify | Unit tests must prove ledger-authoritative phase derivation and drift flags. |
| FR-003 / FR-004 / FR-005 | Approval breakpoint path in driver execution flow | Modify | Integration tests must cover deny path and invalid token path with zero side effects. |
| FR-006 | Producer-only command contract wording + manifest event contracts | Modify | Doc-shape and manifest-contract tests enforce ownership boundaries. |
| FR-010 / FR-011 | Handoff and idempotent retries in driver runtime envelope | Modify | Verify no duplicate terminal event outcomes across retries/replays. |
| FR-013 / FR-014 | `cmd_append` validation + driver entrypoint as canonical orchestrator | Reuse + Modify | Validate partial-write rejection and transition correctness in ledger tests. |

---

## Work-Type Classification

- **Work profile**: software + workflow + governance-doc alignment
- **Primary implementation surface**: `scripts/` orchestration and ledger modules
- **Secondary surfaces**: `.claude/commands/`, `command-manifest.yaml`, tests
- **Human boundary impact**: moderate (approval gate and operator-visible status lines)

---

## Current-System Inventory

- `scripts/pipeline_driver.py` already has deterministic step envelope and runtime failure sidecar handling.
- `scripts/pipeline_driver_state.py` already derives phase from ledger events and detects drift.
- `scripts/pipeline_ledger.py` already validates event shape and transition sequence.
- `scripts/pipeline_driver_contracts.py` already normalizes manifest driver routes and emit contracts.
- `specs/023-deterministic-phase-orchestration/plan.md` already locks architecture decisions this sketch must preserve.

---

## Command / Script Surface Map

| Surface | Role in Solution | Change Type | Notes |
|---------|------------------|-------------|-------|
| `scripts/pipeline_driver.py` | Driver execution, runtime envelope, success event append | Modify | Center of phase orchestration hardening. |
| `scripts/pipeline_driver_state.py` | Phase-state authority and drift detection | Modify | Must remain ledger-authoritative. |
| `scripts/pipeline_ledger.py` | Sequence validation and append guardrails | Modify | Enforces transition state machine. |
| `scripts/pipeline_driver_contracts.py` | Manifest route/contract normalization | Modify | Prevents contract drift between docs and runtime. |
| `command-manifest.yaml` | Canonical command artifacts/events/mode declarations | Modify | Must stay source-of-truth for emit contracts. |
| `.claude/commands/speckit.solution.md` | Producer-oriented phase contract text | Modify | Keep orchestration ownership out of command-doc logic. |

---

## CodeGraphContext Findings

### Seed Symbols

- `scripts/pipeline_driver.py:run_step`
- `scripts/pipeline_driver_state.py:resolve_phase_state`
- `scripts/pipeline_ledger.py:validate_sequence`
- `scripts/pipeline_driver_contracts.py:load_driver_routes`
- `scripts/pipeline_driver.py:resolve_step_mapping`
- `scripts/pipeline_driver_contracts.py:parse_step_result`

### Primary Implementation Surfaces

- `scripts/pipeline_driver.py`
- `scripts/pipeline_driver_state.py`
- `scripts/pipeline_ledger.py`
- `scripts/pipeline_driver_contracts.py`

### Secondary Affected Surfaces

- `command-manifest.yaml`
- `.claude/commands/speckit.solution.md`
- `scripts/speckit_gate_status.py`
- `tests/unit/test_pipeline_driver.py`
- `tests/integration/test_pipeline_driver_feature_flow.py`
- `tests/unit/test_pipeline_ledger_sequence.py`
- `tests/contract/test_pipeline_driver_contract.py`
- `tests/unit/test_validate_command_script_coverage.py`
- `tests/unit/test_validate_markdown_doc_shapes.py`

### Caller / Callee / Dependency Notes

- CodeGraph caller/callee checks were re-run in default per-repo context (no manual `--context` override).
- `cgc analyze callers run_step --file scripts/pipeline_driver.py` resolves to `main`; `calls run_step` resolves `_execute_command`, `handle_runtime_failure`, and `parse_step_result`.
- `cgc analyze callers load_driver_routes --file scripts/pipeline_driver_contracts.py` resolves `resolve_step_mapping`, `append_pipeline_success_event`, and `validate_command_coverage`.
- `cgc analyze callers/calls validate_sequence` and `read_events` surface mixed call graphs due shared symbol names across `pipeline_ledger.py` and `task_ledger.py`; bounded reads are used to disambiguate ownership.
- `cgc analyze deps` returned no dependency graph entries for targeted script modules, so import/dependency claims are bounded-read anchored.

### Missing Seams or Contradictions

- CodeGraph dependency mode currently returns empty results for script modules in this feature seam.
- Shared symbol names (`validate_sequence`, `read_events`, `cmd_append`) across pipeline/task ledgers introduce cross-file ambiguity in global caller listings.
- No contradiction observed between plan decisions and currently visible runtime seams.

---

## Blast Radius

### Direct Implementation Surfaces

- `scripts/pipeline_driver.py:run_step`
- `scripts/pipeline_driver.py:append_pipeline_success_event`
- `scripts/pipeline_driver.py:resolve_step_mapping`
- `scripts/pipeline_driver_state.py:resolve_phase_state`
- `scripts/pipeline_ledger.py:validate_sequence`
- `scripts/pipeline_ledger.py:cmd_append`
- `scripts/pipeline_driver_contracts.py:load_driver_routes`
- `scripts/pipeline_driver_contracts.py:parse_step_result`

### Indirect Affected Surfaces

- `command-manifest.yaml` route mode and emit contracts
- `.claude/commands/speckit.solution.md` producer-only guidance
- `scripts/speckit_gate_status.py:validate_command_coverage`
- Feature quickstart and sketch/tasking handoff docs
- Regression harnesses under `tests/unit/`, `tests/integration/`, and `tests/contract/` for driver/ledger/doc-shape stability

### Regression-Sensitive Neighbors

- `scripts/pipeline_driver.py:run_generative_handoff`
- `scripts/pipeline_driver.py:route_legacy_step`
- `scripts/pipeline_driver.py:validate_coverage_for_migration`
- `scripts/pipeline_driver_state.py:acquire_feature_lock`
- `scripts/pipeline_ledger.py:validate_event_shape`
- `scripts/pipeline_driver_contracts.py:validate_reason_codes`

### Rollout / Compatibility Impact

- Legacy transition compatibility must remain for pre-cutover timestamps while blocking invalid new-order events.
- Driver-managed and legacy-managed commands must continue coexisting until migration scope is complete.

### Operator / Runbook / Deployment Impact

- Operators continue using `pipeline_driver.py --dry-run --json` for deterministic phase visibility.
- Runtime failure sidecars under `.speckit/runtime-failures` remain the debug path for exit-code violations/timeouts.

---

## Reuse / Modify / Create Matrix

### Reuse Unchanged

- Existing pipeline ledger file format and append-only storage model.
- Existing manifest-driven command registry model.

### Modify / Extend Existing

- Driver step execution and success-event append path.
- Phase-state reconciliation and drift detection logic.
- Event transition validation and required-field enforcement.
- Command-doc wording for producer-only contracts.

### Compose from Existing Pieces

- Driver + state resolver + ledger validator + manifest route loader combined as one deterministic contract.

### Create Net-New

- None required for core architecture. Only feature artifact updates under `specs/023-...` as needed.

### Reuse Rationale

Reusing current scripts keeps behavior close to existing tested seams and avoids introducing a second orchestration framework with duplicate risk and governance overhead.

---

## Manifest Alignment Check

- Command involved: `speckit.sketch`
- Expected artifact path: `${FEATURE_DIR}/sketch.md`
- Expected event: `sketch_completed`

### Manifest Alignment Notes

- Manifest already declares `speckit.sketch` as generative driver mode with `sketch.md` scaffold artifact.
- No manifest mismatch found for the sketch phase contract.

---

## Architecture Flow Delta

### Delta Summary

- Clarifies that runtime failure sidecar generation is part of deterministic execution posture.
- Clarifies that success-event append is derived from manifest emit contracts, not hardcoded command assumptions.
- Clarifies that phase-state authority remains ledger-first even when feature-dir artifacts exist.

### Added / Refined Nodes, Edges, or Boundaries

- Refined node: `append_pipeline_success_event` as post-step success append boundary.
- Refined edge: `load_driver_routes -> emit_contracts -> ledger append command`.
- Refined boundary: runtime failure path writes deterministic debug sidecar instead of opaque failures.

---

## Component and Boundary Design

- **Driver runtime (`pipeline_driver.py`)**: Executes phase step, normalizes envelopes, handles runtime-failure debug persistence.
- **State authority (`pipeline_driver_state.py`)**: Resolves phase from ledger history and guards drift/lock behavior.
- **Ledger contract (`pipeline_ledger.py`)**: Validates event shape/order and enforces allowed transitions.
- **Route contract (`pipeline_driver_contracts.py`)**: Normalizes manifest route data into driver-usable contracts.

### Control Flow Notes

- Driver resolves route/mode from manifest before execution.
- Successful execution only appends a completion event through validated contract path.
- Invalid runtime envelopes route to deterministic failure payload + sidecar path.

### Data Flow Notes

- Manifest route metadata feeds driver route selection and emit event contract.
- Ledger event stream feeds phase-state resolution and transition validation.

---

## Interface, Symbol, and Contract Notes

### Public Interfaces and Contracts

- `pipeline_driver.py` CLI entrypoint and step result envelope.
- `pipeline_ledger.py append|validate|assert-phase-complete` CLI contracts.
- `pipeline_driver_contracts.load_driver_routes` route contract for command IDs.

### New or Changed Public Symbols

- No net-new public symbol is required by this sketch.
- Existing symbols expected to change behavior/coverage:
  - `scripts/pipeline_driver.py:run_step`
  - `scripts/pipeline_driver.py:append_pipeline_success_event`
  - `scripts/pipeline_driver_state.py:resolve_phase_state`
  - `scripts/pipeline_ledger.py:validate_sequence`

### Ownership Boundaries

- Driver owns orchestration execution and exit-envelope interpretation.
- Ledger owns event sequence validation and append acceptance.
- Command docs own artifact-production guidance only, not event append mechanics.

---

## State / Lifecycle / Failure Model

### State Authority

- Pipeline ledger is source-of-truth for last event and approval state.
- Feature-dir artifacts are consistency signals, not phase authority.
- Drift flags are raised when hints/artifacts disagree with ledger sequence.

### Lifecycle / State Transitions

- Plan-approved state is prerequisite for sketch/solution progression.
- Sketch completion is an explicit event state, not implicit file presence.
- Solution progression must preserve sequence constraints (including estimation/tasking gates).

### Retry / Replay / Ordering / Cancellation

- Event append path remains append-only with sequence validation.
- Invalid/duplicate ordering is rejected by ledger sequence checks.
- Runtime step retries must preserve deterministic envelopes and avoid duplicate terminal outcomes.

### Degraded Modes / Fallbacks / Recovery

- Runtime command failures produce sidecar diagnostics under `.speckit/runtime-failures`.
- Missing/invalid output envelopes map to deterministic failure reason codes.
- Legacy transition compatibility remains bounded by cutover timestamp rules.

---

## Non-Functional Design Implications

- **Security**: no new secrets path; runtime diagnostics must avoid secret leakage.
- **Reliability**: deterministic exit-code and envelope checks reduce ambiguous failures.
- **Observability**: sidecar diagnostics and structured status lines remain the operator debug channel.
- **Performance**: no major runtime cost increase expected; route normalization is lightweight.
- **Maintainability**: manifest-driven contracts reduce drift between docs and runtime behavior.

---

## Migration / Rollback Notes

### Migration / Cutover Requirements

- Preserve legacy route handling while migrating command IDs incrementally.
- Keep transition compatibility rules until all pre-cutover patterns are retired.

### Rollback Triggers

- Any regression where denied approval causes side effects.
- Any regression where completion events append without validation pass.

### Rollback Constraints

- Ledger events are append-only; rollback is forward-fix via new events/code.
- Command-manifest and driver-contract changes must stay synchronized to rollback safely.

---

## Human-Task and Operator Boundaries

- Human approval token remains explicit before side-effectful phase execution.
- Operators may run dry-run first to inspect phase state before live execution.
- Runtime failure investigation remains manual via generated sidecar diagnostics.

---

## Verification Strategy

### Unit-Testable Seams

- `resolve_phase_state` reconciliation and drift flagging.
- `validate_sequence` transition and shape enforcement.
- `load_driver_routes` mode normalization and emit-contract parsing.

### Contract Verification Needs

- Manifest emit contracts and driver append behavior stay aligned.
- Command-doc shape tests confirm producer-only contract wording.

### Integration / Reality-Check Paths

- End-to-end driver feature-flow tests for allowed/blocked/error envelopes.
- Approval deny path must show no side effects and deterministic reason codes.

### Lifecycle / Retry / Duplicate Coverage Needs

- Validate-before-emit ordering under failure and retry scenarios.
- Duplicate/invalid transition attempts must remain blocked.

### Deterministic Oracles (if known)

- Exit envelope schema (`ok`, `exit_code`, `gate/reasons`, `next_phase`, `error_code/debug_path`).
- Ledger append acceptance/rejection based on strict transition map.

### Regression-Sensitive Areas

- Driver route fallback between generative and legacy command modes.
- Sequence transitions around sketch/solution/tasking/analysis phases.

---

## Domain Guardrails

- **Security / identity boundaries**: no secrets in logs/artifacts; approval and actor attribution remain explicit.
- **Ops governance**: pipeline ledger remains append-only and validated.
- **Testing / resilience**: deterministic error envelopes and regression tests are mandatory before phase advancement.

---

## LLD Decision Log

- Keep driver as orchestration authority and avoid embedding ledger semantics in command docs.
- Treat codegraph relationship sparsity as a tooling limitation, not license to infer callers/callees.
- Prioritize modifications to existing scripts over introducing a new orchestration layer.

---

## Design Gaps and Repo Contradictions

### Missing Seams

- CodeGraph caller/callee edges are available in default per-repo context for seeded symbols.
- Scoped `--context scripts` lookups and module dependency (`cgc analyze deps`) remain sparse for this seam.

### Unsupported Assumptions

- Treat global caller listings for duplicated symbol names (`validate_sequence`, `read_events`, `cmd_append`) as ambiguous unless file-qualified and bounded-read anchored.

### Plan vs Repo Contradictions

- None identified in current bounded reads.

### Blocking Design Issues

- None.

---

## Out-of-Scope / Preserve-As-Is Boundaries

- Do not redesign Speckit command taxonomy or add new phase types.
- Preserve existing ledger file format and append-only semantics.
- Do not introduce new external services or runtime infrastructure for this feature.

---

## Design-to-Tasking Contract

Downstream `/speckit.tasking` must preserve:

- Driver-owned validate-before-emit and success-append boundaries.
- Ledger-authoritative phase-state resolution and transition enforcement.
- Producer-only command-doc contract language (no direct event append instructions).

Downstream `/speckit.tasking` may refine:

- Exact sequencing of test-first slices inside each user story.
- Fine-grained symbol ownership across `pipeline_driver*` and ledger contract modules.

### Additional Tasking Notes

- Include explicit tasks for contract/doc/manifest alignment in the same change slices.
- Include regression tasks for approval rejection side effects and duplicate event prevention.

---

## Decomposition-Ready Design Slices

### Slice SK-01: Driver execution envelope hardening

- **Objective**: Ensure phase execution produces deterministic envelopes for success/blocked/error outcomes.
- **Primary seam**: `scripts/pipeline_driver.py:run_step`
- **Touched files**:
  - `scripts/pipeline_driver.py`
  - `tests/unit/test_pipeline_driver.py`
  - `tests/integration/test_pipeline_driver_feature_flow.py`
- **Touched symbols**:
  - `scripts/pipeline_driver.py:run_step`
  - `scripts/pipeline_driver.py:handle_runtime_failure`
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_success`
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_runtime_failure_verbose_rerun`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Exit codes outside allowed set must map to deterministic error envelope.
  - Missing/invalid payload data must never advance phase.
- **Dependencies**: None.
- **Verification / regression concern**:
  - Ensure runtime failures always generate debug sidecar path.
  - Prevent false-success envelopes under malformed subprocess output.

### Slice SK-02: Ledger-authoritative phase resolution

- **Objective**: Keep phase state derived from ledger events with explicit drift reasons.
- **Primary seam**: `scripts/pipeline_driver_state.py:resolve_phase_state`
- **Touched files**:
  - `scripts/pipeline_driver_state.py`
  - `tests/unit/test_pipeline_driver.py`
  - `tests/integration/test_pipeline_driver_feature_flow.py`
- **Touched symbols**:
  - `scripts/pipeline_driver_state.py:resolve_phase_state`
  - `scripts/pipeline_driver_state.py:acquire_feature_lock`
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_resolve_phase_state_skeleton`
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_reconcile_and_retry_guards`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Ledger remains source-of-truth over hinted phase fields.
  - Drift reasons must be deterministic and machine-readable.
- **Dependencies**: SK-01.
- **Verification / regression concern**:
  - Reject state resolution paths that trust stale mirrors over ledger state.

### Slice SK-03: Transition and append contract enforcement

- **Objective**: Prevent invalid event ordering and append only validated transitions.
- **Primary seam**: `scripts/pipeline_ledger.py:validate_sequence`
- **Touched files**:
  - `scripts/pipeline_ledger.py`
  - `tests/unit/test_pipeline_ledger_sequence.py`
  - `tests/unit/test_pipeline_driver.py`
- **Touched symbols**:
  - `scripts/pipeline_ledger.py:validate_sequence`
  - `scripts/pipeline_ledger.py:cmd_append`
  - `tests/unit/test_pipeline_ledger_sequence.py:test_new_solution_sequence_passes`
  - `tests/unit/test_pipeline_ledger_sequence.py:test_analysis_completed_requires_zero_critical_count`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Transition map is authoritative for allowed predecessor events.
  - `analysis_completed` emission requires `critical_count == 0`.
- **Dependencies**: SK-02.
- **Verification / regression concern**:
  - Ensure invalid transitions never mutate ledger state.

### Slice SK-04: Manifest route and emit-contract normalization

- **Objective**: Keep runtime route/emit behavior fully driven by manifest contracts.
- **Primary seam**: `scripts/pipeline_driver_contracts.py:load_driver_routes`
- **Touched files**:
  - `scripts/pipeline_driver_contracts.py`
  - `command-manifest.yaml`
  - `tests/contract/test_pipeline_driver_contract.py`
  - `tests/unit/test_validate_command_script_coverage.py`
- **Touched symbols**:
  - `scripts/pipeline_driver_contracts.py:load_driver_routes`
  - `scripts/pipeline_driver_contracts.py:normalize_driver_mode`
  - `scripts/pipeline_driver_contracts.py:parse_step_result`
  - `tests/unit/test_validate_command_script_coverage.py:test_validate_command_script_coverage_passes_with_required_scripts`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Unknown route modes must fail fast with deterministic error.
  - Emit contract fields must remain schema-valid and synchronized with manifest.
- **Dependencies**: SK-01.
- **Verification / regression concern**:
  - Guard against manifest/doc drift causing wrong route mode or event selection.

### Slice SK-05: Producer-only command contract alignment

- **Objective**: Keep command docs as producer contracts and remove implicit orchestration ownership.
- **Primary seam**: `.claude/commands/speckit.solution.md`
- **Touched files**:
  - `.claude/commands/speckit.solution.md`
  - `command-manifest.yaml`
  - `specs/023-deterministic-phase-orchestration/quickstart.md`
  - `tests/unit/test_validate_markdown_doc_shapes.py`
- **Touched symbols**:
  - `command-manifest.yaml:commands.speckit.solution`
  - `tests/unit/test_validate_markdown_doc_shapes.py:test_validate_markdown_doc_shape_accepts_compact_expanded`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Command docs do not directly append ledger events.
  - Driver ownership language remains explicit and consistent.
- **Dependencies**: SK-04.
- **Verification / regression concern**:
  - Markdown/doc-shape tests catch contract wording regressions.

### Slice SK-06: Regression and acceptance hardening

- **Objective**: Encode deterministic oracles for sequencing, approval, and idempotency.
- **Primary seam**: `tests/integration/test_pipeline_driver_feature_flow.py`
- **Touched files**:
  - `tests/integration/test_pipeline_driver_feature_flow.py`
  - `tests/unit/test_pipeline_driver.py`
  - `tests/unit/test_pipeline_ledger_sequence.py`
  - `tests/contract/test_pipeline_driver_contract.py`
  - `tests/unit/test_validate_markdown_doc_shapes.py`
- **Touched symbols**:
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_blocked`
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_approval_breakpoint_blocks_without_token`
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_mixed_migration_mode`
  - `tests/contract/test_pipeline_driver_contract.py:test_step_result_schema_blocked_requires_gate_and_reasons`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - No completion append on failed validation.
  - No side effects on denied approval.
- **Dependencies**: SK-01 through SK-05.
- **Verification / regression concern**:
  - Ensure migration path remains deterministic across legacy and driver-managed commands.

---

## Sketch Completion Summary

### Review Readiness

- [x] Solution narrative complete
- [x] Construction strategy complete
- [x] Command / Script surface map complete
- [x] Manifest alignment complete
- [x] Design slices decomposition-ready
- [x] No unresolved blocking design issue

If any item is unchecked, sketch is not ready for `/speckit.solutionreview`.

### Suggested Next Step

- Run `/speckit.solutionreview`
