# Sketch Blueprint — Deterministic Phase Orchestration

_Date: 2026-04-20_
_Feature ID: 023_
_Feature Name: Deterministic Phase Orchestration_

---

## Feature Solution Frame

### Core Capability

Move phase progression into one deterministic orchestration contract where `/speckit.run` (or direct driver CLI) is the canonical progression trigger, direct reruns are allowed, and event append behavior is machine-enforced instead of doc-driven.

### Current → Target Transition

Current state mixes legacy command-doc orchestration with partial driver routing and sequence validation. Target state keeps command docs producer-oriented while `pipeline_driver.py` + `pipeline_driver_state.py` + `pipeline_ledger.py` + `task_ledger.py` own execution routing, state authority, validate-before-emit, phase-close gating, and once-only terminal emission guarantees.

### Dominant Execution Model

Deterministic orchestrator model: `orchestrate -> extract -> scaffold -> LLM Action -> validate -> phase-close gates -> emit/handoff`, with explicit approval and structured exit semantics.

### Main Design Pressures

- Preserve existing Speckit command surfaces while tightening deterministic enforcement.
- Keep `pipeline-ledger.jsonl` and `task-ledger.jsonl` as source-of-truths for their scopes without conflicting local mirrors.
- Close out-of-order forward-progression bypass paths while allowing deterministic rerun behavior during migration.
- Migrate implement-phase completion to a deterministic phase-close + `implementation_completed` terminal event contract.

---

## Solution Narrative

This sketch keeps the approved plan thesis intact: `/speckit.run` dispatches deterministic orchestration through the driver, command docs remain producer contracts, and event emission is downstream of deterministic validation and phase-close checks. Implementation centers on strengthening existing scripts rather than introducing a new framework. The design slices split work across trigger/routing enforcement, state/transition logic, implement close semantics, contract normalization, and regression verification so tasking can proceed without inventing architecture.

---

## Construction Strategy

1. Enforce canonical trigger routing (`/speckit.run` -> driver) and deterministic redirect/block behavior for legacy direct phase invocations.
2. Stabilize the route contract from manifest to driver mode resolution (`legacy` vs `generative` vs deterministic envelope expectations).
3. Reinforce state authority and sequencing invariants (`resolve_phase_state`, `validate_sequence`, append rules) across pipeline and task ledgers.
4. Tighten validate-before-emit and phase-close behavior so terminal events (including `implementation_completed`) occur only on validated success paths.
5. Align command docs and manifest language with compact producer-only contracts and driver-owned orchestration.
6. Lock behavior with integration/unit coverage over approval, sequencing, migration-path regressions, and once-only terminal emission.

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
| FR-015 / FR-016 / SC-005 | Canonical `/speckit.run` dispatch + rerun-vs-progression gate branch | Modify | Integration coverage must prove reruns are allowed at/below latest allowed step and forward overreach is blocked/redirected. |
| FR-017 | Driver `--dry-run` deterministic gate/phase resolution mode | Reuse + Modify | Verify dry-run returns deterministic gate outcomes with zero artifact/ledger mutation. |
| FR-018 / SC-006 | Implement-phase preflight + per-task verification + phase-close gate + `implementation_completed` emission path | Modify | Add close-pass/close-fail/retry-idempotency tests to enforce once-only terminal emission. |
| FR-019 | Runner-adapter handoff contract (`stdin` JSON -> `stdout` JSON) | Modify | Validate adapter parse failures never emit completion events. |
| FR-020 | Explicit manifest driver route metadata fields and emit-contract normalization | Modify | Contract tests enforce mode/script/timeout/emit field presence and parseability. |
| FR-021 / SC-007 | Compact producer-only command doc normalization across speckit docs | Modify | Markdown/doc-shape coverage must flag executable gate/ledger procedures in command docs. |

---

## Work-Type Classification

- **Work profile**: software + workflow + governance-doc alignment
- **Primary implementation surface**: `scripts/` orchestration and ledger modules
- **Secondary surfaces**: `.claude/commands/`, `command-manifest.yaml`, tests
- **Human boundary impact**: moderate (approval gate, deterministic redirect/block reasons, operator-visible status lines)

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
| `scripts/pipeline_driver.py` | Driver execution, runtime envelope, success event append, dry-run and trigger gating | Modify | Center of orchestration hardening and canonical execution boundary. |
| `scripts/pipeline_driver_state.py` | Phase-state authority and drift detection | Modify | Must remain ledger-authoritative and block hint conflicts. |
| `scripts/pipeline_ledger.py` | Sequence validation and append guardrails | Modify | Enforces phase transition state machine. |
| `scripts/task_ledger.py` | Task-scoped lifecycle authority consumed by implement close checks | Reuse + Modify | Integrates implement phase-close prerequisites with pipeline completion. |
| `scripts/speckit_implement_gate.py` | Deterministic implement verification gates | Modify | Must feed phase-close decision path before terminal emission. |
| `scripts/pipeline_driver_contracts.py` | Manifest route/contract normalization + runner payload parsing | Modify | Prevents contract drift between docs and runtime. |
| `command-manifest.yaml` | Canonical command artifacts/events/mode declarations | Modify | Must include explicit route metadata and migrated emit contracts. |
| `.claude/commands/speckit.implement.md` + `.claude/commands/speckit.solution.md` + `.claude/commands/speckit.sketch.md` | Producer-oriented command contract text | Modify | Keep orchestration ownership out of command-doc logic and remove executable gate/ledger procedures. |

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

- Commands involved: `speckit.sketch`, `speckit.solution`, `speckit.implement`
- Expected artifact paths: `${FEATURE_DIR}/sketch.md` plus command-owned phase artifacts declared in manifest
- Expected events (post-migration target): `sketch_completed`, `solution_approved`, `implementation_completed`

### Manifest Alignment Notes

- Manifest already declares `speckit.sketch` as generative driver mode with `sketch.md` scaffold artifact.
- Manifest still declares `speckit.implement` as `mode: legacy` with no emit contract, so migration is required to satisfy FR-018/FR-020/SC-006.
- Canonical `/speckit.run` trigger contract is a required orchestration surface and must be explicitly represented in route/dispatch governance.

---

## Architecture Flow Delta

### Delta Summary

- Clarifies canonical trigger boundary: `/speckit.run` routes to deterministic driver execution.
- Clarifies that direct phase command reruns are allowed when at/below latest allowed step, while forward overreach is blocked/redirected.
- Clarifies that success-event append is derived from manifest emit contracts and phase-close gates, not hardcoded command assumptions.
- Clarifies that phase-state authority remains ledger-first even when feature-dir artifacts exist.

### Added / Refined Nodes, Edges, or Boundaries

- Refined node: `append_pipeline_success_event` as post-step success append boundary.
- Refined edge: `load_driver_routes -> emit_contracts -> ledger append command`.
- Refined boundary: runtime failure path writes deterministic debug sidecar instead of opaque failures.
- Added node: `phase-close-gates` prior to terminal phase event emission.
- Added boundary: runner-adapter contract as the only accepted transport shape for LLM phase payload execution.

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

- `/speckit.run` trigger contract and `pipeline_driver.py` CLI execution boundary.
- `pipeline_ledger.py append|validate|assert-phase-complete` CLI contracts.
- `task_ledger.py assert-can-start|append|validate` CLI contracts for implement lifecycle integration.
- `pipeline_driver_contracts.load_driver_routes` route contract for command IDs.

### New or Changed Public Symbols

- Existing symbols expected to change behavior/coverage:
  - `scripts/pipeline_driver.py:run_step`
  - `scripts/pipeline_driver.py:append_pipeline_success_event`
  - `scripts/pipeline_driver_state.py:resolve_phase_state`
  - `scripts/pipeline_ledger.py:validate_sequence`
  - `scripts/speckit_implement_gate.py` phase-close checks used by driver-managed implement completion
  - `scripts/pipeline_driver_contracts.py:load_driver_routes`

### Ownership Boundaries

- Driver owns orchestration execution and exit-envelope interpretation.
- Ledger owns event sequence validation and append acceptance.
- Implement task-lifecycle truth stays task-ledger scoped until phase-close success authorizes pipeline terminal emission.
- Command docs own artifact-production guidance only, not event append mechanics.

---

## State / Lifecycle / Failure Model

### State Authority

- Pipeline ledger is source-of-truth for last event and approval state.
- Task ledger is source-of-truth for task lifecycle state during implement execution.
- Feature-dir artifacts are consistency signals, not phase authority.
- Drift flags are raised when hints/artifacts disagree with ledger sequence.

### Lifecycle / State Transitions

- Plan-approved state is prerequisite for sketch/solution progression.
- Sketch completion is an explicit event state, not implicit file presence.
- Solution progression must preserve sequence constraints (including estimation/tasking gates).
- Implement completion requires deterministic preflight + per-task verification + phase-close success before `implementation_completed`.

### Retry / Replay / Ordering / Cancellation

- Event append path remains append-only with sequence validation.
- Invalid/duplicate ordering is rejected by ledger sequence checks.
- Runtime step retries must preserve deterministic envelopes and avoid duplicate terminal outcomes.
- Implement retries must never duplicate `implementation_completed`; idempotency is enforced at phase-close boundary.
- Direct rerun of current/earlier steps remains allowed; only forward progression beyond latest allowed step is rejected.

### Degraded Modes / Fallbacks / Recovery

- Runtime command failures produce sidecar diagnostics under `.speckit/runtime-failures`.
- Missing/invalid output envelopes map to deterministic failure reason codes.
- Legacy transition compatibility remains bounded by cutover rules; forward overreach bypass remains disallowed.

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

- Preserve deterministic rerun behavior for direct phase invocations while routes migrate.
- Migrate `speckit.implement` from legacy mode to driver-managed contract with explicit phase-close/emit metadata.
- Keep transition compatibility rules until all pre-cutover patterns are retired.

### Rollback Triggers

- Any regression where denied approval causes side effects.
- Any regression where completion events append without validation pass.
- Any regression where direct invocation progresses beyond latest allowed step without deterministic block/redirect.
- Any regression where `implementation_completed` is emitted on failed phase-close or emitted more than once.

### Rollback Constraints

- Ledger events are append-only; rollback is forward-fix via new events/code.
- Command-manifest and driver-contract changes must stay synchronized to rollback safely.
- Task-ledger semantics must remain preserved while changing pipeline-level implement completion logic.

---

## Human-Task and Operator Boundaries

- Human approval token remains explicit before side-effectful phase execution.
- Operators may run dry-run first to inspect phase state before live execution.
- Operators receive deterministic redirect/block reason codes when invoking legacy direct phase commands.
- Runtime failure investigation remains manual via generated sidecar diagnostics.

---

## Verification Strategy

### Unit-Testable Seams

- `resolve_phase_state` reconciliation and drift flagging.
- `validate_sequence` transition and shape enforcement.
- `load_driver_routes` mode normalization and emit-contract parsing.
- Implement phase-close predicates (`speckit_implement_gate` + task-ledger assertions).

### Contract Verification Needs

- Manifest emit contracts and driver append behavior stay aligned.
- Command-doc shape tests confirm producer-only contract wording.
- Runner-adapter request/response envelope contract remains deterministic and parseable.

### Integration / Reality-Check Paths

- End-to-end driver feature-flow tests for allowed/blocked/error envelopes.
- Approval deny path must show no side effects and deterministic reason codes.
- `/speckit.run` canonical trigger path must be covered with rerun-allowed and forward-overreach-blocked branch checks.
- Implement close path must verify once-only `implementation_completed` emission on phase-close success.

### Lifecycle / Retry / Duplicate Coverage Needs

- Validate-before-emit ordering under failure and retry scenarios.
- Duplicate/invalid transition attempts must remain blocked.
- Implement-phase close failure must emit no terminal event, and retries must remain idempotent.

### Deterministic Oracles (if known)

- Exit envelope schema (`ok`, `exit_code`, `gate/reasons`, `next_phase`, `error_code/debug_path`).
- Ledger append acceptance/rejection based on strict transition map.
- Runner-adapter envelope schema (`stdin` JSON request -> `stdout` JSON result) for generative phases.

### Regression-Sensitive Areas

- Driver route fallback between generative and legacy command modes.
- Sequence transitions around sketch/solution/tasking/analysis phases.
- Rerun-vs-forward-progression gating policy for direct phase invocations.
- Implement closeout boundary between task-ledger lifecycle and pipeline terminal completion.

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
- Preserve local Codex viability through runner-adapter normalization rather than raw `codex exec` payload coupling.

---

## Design Gaps and Repo Contradictions

### Missing Seams

- CodeGraph caller/callee edges are available in default per-repo context for seeded symbols.
- Scoped `--context scripts` lookups and module dependency (`cgc analyze deps`) remain sparse for this seam.

### Unsupported Assumptions

- Treat global caller listings for duplicated symbol names (`validate_sequence`, `read_events`, `cmd_append`) as ambiguous unless file-qualified and bounded-read anchored.

### Plan vs Repo Contradictions

- Plan requires canonical `/speckit.run` orchestration trigger while current manifest-command surfaces are still centered on phase commands.
- Plan requires driver-managed implement terminal emission (`implementation_completed`) while current manifest seam for `speckit.implement` remains legacy with no emit contract.

### Blocking Design Issues

- None at design level, but migration gaps above must be resolved before claiming FR-015/FR-018/SC-006 completion.

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
- Canonical trigger and rerun-vs-forward-progression gate policy for direct invocation paths.
- Implement phase-close predicate + once-only `implementation_completed` terminal emission contract.

Downstream `/speckit.tasking` may refine:

- Exact sequencing of test-first slices inside each user story.
- Fine-grained symbol ownership across `pipeline_driver*` and ledger contract modules.

### Additional Tasking Notes

- Include explicit tasks for contract/doc/manifest alignment in the same change slices.
- Include regression tasks for approval rejection side effects and duplicate event prevention.
- Include dedicated tasks for implement migration that preserve task-ledger semantics while adding pipeline-level completion emission.

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
  - Terminal phase events require phase-close gate success before append.
- **Dependencies**: SK-02.
- **Verification / regression concern**:
  - Ensure invalid transitions never mutate ledger state.

### Slice SK-04: Manifest route and emit-contract normalization

- **Objective**: Keep runtime route/emit behavior fully driven by manifest contracts, including canonical trigger routing and implement close emission metadata.
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
  - Redirect/block behavior for legacy direct invocation must be represented by deterministic route policy.
- **Dependencies**: SK-01.
- **Verification / regression concern**:
  - Guard against manifest/doc drift causing wrong route mode or event selection.

### Slice SK-05: Producer-only command contract alignment

- **Objective**: Keep command docs as producer contracts and remove implicit orchestration ownership.
- **Primary seam**: `.claude/commands/speckit.implement.md`
- **Touched files**:
  - `.claude/commands/speckit.implement.md`
  - `.claude/commands/speckit.sketch.md`
  - `.claude/commands/speckit.solution.md`
  - `command-manifest.yaml`
  - `specs/023-deterministic-phase-orchestration/quickstart.md`
  - `tests/unit/test_validate_markdown_doc_shapes.py`
- **Touched symbols**:
  - `command-manifest.yaml:commands.speckit.implement`
  - `command-manifest.yaml:commands.speckit.sketch`
  - `command-manifest.yaml:commands.speckit.solution`
  - `tests/unit/test_validate_markdown_doc_shapes.py:test_validate_markdown_doc_shape_accepts_compact_expanded`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Command docs do not directly append ledger events.
  - Driver ownership language remains explicit and consistent.
  - Command docs avoid embedding executable gate procedures and only emit producer payload expectations.
- **Dependencies**: SK-04.
- **Verification / regression concern**:
  - Markdown/doc-shape tests catch contract wording regressions.

### Slice SK-06: Regression and acceptance hardening

- **Objective**: Encode deterministic oracles for sequencing, approval, trigger policy, and idempotency.
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
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_legacy_direct_phase_redirect_or_blocked`
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_implement_completion_emits_once`
  - `tests/contract/test_pipeline_driver_contract.py:test_step_result_schema_blocked_requires_gate_and_reasons`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - No completion append on failed validation.
  - No side effects on denied approval.
  - No successful forward-progression bypass path outside canonical orchestration trigger.
  - Direct reruns at/below latest allowed step remain permitted.
  - `implementation_completed` emits exactly once on close-pass and never on close-fail.
- **Dependencies**: SK-01 through SK-05.
- **Verification / regression concern**:
  - Ensure migration path remains deterministic across legacy and driver-managed commands.

### Slice SK-07: Canonical trigger routing and legacy redirect/block enforcement

- **Objective**: Make `/speckit.run` the canonical progression trigger while allowing deterministic direct reruns and blocking/redirecting only forward overreach.
- **Primary seam**: `scripts/pipeline_driver.py:resolve_step_mapping`
- **Touched files**:
  - `scripts/pipeline_driver.py`
  - `scripts/pipeline_driver_contracts.py`
  - `command-manifest.yaml`
  - `tests/integration/test_pipeline_driver_feature_flow.py`
- **Touched symbols**:
  - `scripts/pipeline_driver.py:resolve_step_mapping`
  - `scripts/pipeline_driver_contracts.py:load_driver_routes`
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_deterministic_route_blocked`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Canonical orchestration entrypoint remains deterministic and machine-enforced.
  - Direct rerun outcomes and forward-overreach blocked outcomes are explicit and reason-coded.
- **Dependencies**: SK-01, SK-02, SK-04.
- **Verification / regression concern**:
  - Prevent any direct command path from bypassing gate/validation/emit sequencing for forward progression.

### Slice SK-08: Implement phase-close orchestration and terminal emission

- **Objective**: Migrate implement execution to driver-managed deterministic flow with task-ledger-informed phase-close gates and once-only `implementation_completed` emission.
- **Primary seam**: `scripts/pipeline_driver.py:append_pipeline_success_event`
- **Touched files**:
  - `scripts/pipeline_driver.py`
  - `scripts/speckit_implement_gate.py`
  - `scripts/task_ledger.py`
  - `command-manifest.yaml`
  - `tests/integration/test_pipeline_driver_feature_flow.py`
  - `tests/unit/test_pipeline_ledger_sequence.py`
- **Touched symbols**:
  - `scripts/pipeline_driver.py:append_pipeline_success_event`
  - `scripts/speckit_implement_gate.py`
  - `scripts/task_ledger.py:cmd_assert_can_start`
  - `tests/integration/test_pipeline_driver_feature_flow.py:test_implement_completion_emits_once`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Implement close failure never emits `implementation_completed`.
  - Implement close success emits `implementation_completed` exactly once.
  - Existing task-ledger lifecycle semantics remain intact.
- **Dependencies**: SK-01 through SK-07.
- **Verification / regression concern**:
  - Ensure phase-close retries preserve idempotency and do not corrupt task/pipeline ledger ordering.

---

### Recovery Delta Slices (Post-Drift Realignment)

### Slice SK-09: Canonical Codex trigger artifact + manifest route

- **Objective**: Add Codex-native canonical trigger contract (`speckit.run`) as a concrete artifact + manifest route, not metadata-only inference.
- **Primary seam**: `command-manifest.yaml:commands.speckit.run`
- **Touched files**:
  - `command-manifest.yaml`
  - `.claude/commands/speckit.run.md`
  - `tests/unit/test_pipeline_driver.py`
- **Touched symbols**:
  - `scripts/pipeline_driver.py:resolve_step_mapping`
  - `tests/unit/test_pipeline_driver.py:test_resolve_step_mapping_uses_real_manifest`
- **Likely net-new files**:
  - `.claude/commands/speckit.run.md`
- **Reuse / Modify / Create**: Modify existing + create canonical trigger command doc artifact.
- **Major constraints / invariants**:
  - Canonical trigger must resolve deterministically from manifest contracts.
  - Trigger artifact presence must be machine-checkable.

### Slice SK-10: Runner-required generative execution enforcement

- **Objective**: Remove permissive `handoff_execution: not_configured` success path; missing runner must be a deterministic failure state with no append.
- **Primary seam**: `scripts/pipeline_driver.py:run_generative_handoff`
- **Touched files**:
  - `scripts/pipeline_driver.py`
  - `tests/unit/test_pipeline_driver.py`
- **Touched symbols**:
  - `scripts/pipeline_driver.py:run_generative_handoff`
  - `tests/unit/test_pipeline_driver.py:test_run_generative_handoff_returns_handoff_when_runner_not_configured`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Missing runner must fail with deterministic gate/error_code.
  - Failure path must not allow completion append.

### Slice SK-11: Required migration routes no longer legacy

- **Objective**: Migrate `speckit.tasking` and `speckit.implement` route contracts to non-legacy driver-managed modes with explicit route metadata.
- **Primary seam**: `command-manifest.yaml` command route entries
- **Touched files**:
  - `command-manifest.yaml`
  - `scripts/pipeline_driver_contracts.py`
  - `tests/unit/test_pipeline_driver.py`
  - `tests/integration/test_pipeline_driver_feature_flow.py`
- **Touched symbols**:
  - `scripts/pipeline_driver_contracts.py:load_driver_routes`
  - `scripts/pipeline_driver.py:route_legacy_step`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Recovery work must keep deterministic rerun-at/below-current behavior.
  - Forward overreach remains blocked/redirected.

### Slice SK-12: Command-contract normalization enforcement hardening

- **Objective**: Normalize command docs and strengthen contract validators so required docs failing compact/expanded shape or executable-procedure bans fail deterministically.
- **Primary seam**: `scripts/validate_markdown_doc_shapes.py:validate_markdown_doc_shape`
- **Touched files**:
  - `scripts/validate_markdown_doc_shapes.py`
  - `.claude/commands/speckit*.md` (required migrated command set)
  - `tests/unit/test_validate_markdown_doc_shapes.py`
- **Touched symbols**:
  - `scripts/validate_markdown_doc_shapes.py:_find_forbidden_procedure_markers`
  - `tests/unit/test_validate_markdown_doc_shapes.py:test_validate_markdown_doc_shape_accepts_compact_expanded`
- **Likely net-new files**:
  - `None`
- **Reuse / Modify / Create**: Modify existing.
- **Major constraints / invariants**:
  - Doc-shape gate must validate the required migrated surface, not a hand-picked subset.
  - Contract enforcement scope must be explicit and reproducible.

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

- Run `/speckit.tasking` to append recovery delta tasks (T050+), then execute `/speckit.implement` on that appended set.
