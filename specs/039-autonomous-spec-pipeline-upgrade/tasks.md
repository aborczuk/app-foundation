# Tasks: autonomous spec pipeline upgrade

**Input**: `spec.md`, `plan.md`, and `spec.json` in `specs/039-autonomous-spec-pipeline-upgrade/`
**Prerequisites**: approved plan with slices PL-01 through PL-07
**Terminal boundary**: create an implementation-ready handoff only; do not start implementation work in this workflow.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Task can run in parallel because it targets a different file or independent test seam.
- **[Story]**: Traceability to the user story that proves value.
- Every non-human task names concrete files or symbols.

## Phase 1: Setup and Upgrade Baseline

**Purpose**: Establish pinned upstream and repo baseline before any migration mutation.

- [ ] T001 [US4] Add pinned Spec Kit capability preflight and version contract in scripts/speckit_workflow_preflight.py covering `specify version --features --json`, approved release `v0.12.9`, project root, feature directory, and no floating `latest` values.
- [ ] T002 [P] [US4] Add unit coverage for preflight pass/fail cases in tests/unit/test_speckit_workflow_preflight.py, including missing workflow support, wrong release, malformed JSON, and ambiguous project root.
- [ ] T003 [US4] Add upgrade inventory and rehearsal support in scripts/speckit_upgrade_inventory.py for CLI/project/customization files, hashes, clean-checkout reproduction inputs, and rollback evidence.
- [ ] T004 [P] [US4] Add unit coverage for inventory classification and rollback metadata in tests/unit/test_speckit_upgrade_inventory.py.

**Checkpoint**: Capability and inventory checks can run without artifact or ledger mutation.

## Phase 2: Manifest and Ownership Routing

**Purpose**: Make one integration-neutral source own pre-implementation workflow routes.

- [ ] T005 [US1] Extend command-manifest.yaml with workflow step ownership, permission class, result artifact, validator, event, provenance, and pre-implementation terminal route fields for the autonomous pipeline.
- [ ] T006 [P] [US1] Extend manifest validation in scripts/pipeline_ledger.py:cmd_validate_manifest to reject legacy or ambiguous routes for canonical pre-implementation phases.
- [ ] T007 [P] [US1] Add manifest consistency tests in tests/unit/test_validate_command_manifest.py for workflow fields, mirror version drift, route ownership conflicts, and prohibited implementation-start routes.
- [ ] T008 [US1] Update Codex/Claude command source generation or compatibility mapping in .codex/skills/speckit-run/SKILL.md and .claude/commands/speckit.run.md so one command source starts or resumes the workflow through handoff.

**Checkpoint**: Canonical routes resolve to one owner and one result contract.

## Phase 3: Safe Command and Shell Adapter

**Purpose**: Preserve argv safety behind upstream `shell` workflow steps.

- [ ] T009a [US2] Define scripts/speckit_command_adapter.py request and reviewed-command policy contracts for allowlisted executable/argv resolution, validated input schema, repository-root cwd, and permission class so any unreviewed effective command is rejected before process creation.
- [ ] T009b [US2] Implement the validated-request runner in scripts/speckit_command_adapter.py with root-cwd execution, bounded timeout and output capture, and a single structured JSON stdout result with bounded stderr diagnostics.
- [ ] T009c [US2] Add result-channel redaction and envelope finalization in scripts/speckit_command_adapter.py so approved command results preserve output caps, redact protected values, and report actionable policy or runner failures without shell-text execution.
- [ ] T010 [P] [US2] Add adapter security tests in tests/unit/test_speckit_command_adapter.py for rejected dynamic executable, cwd escape, untrusted interpolation, oversized output, malformed JSON, timeout, and redaction.
- [ ] T011 [US2] Integrate command adapter routing into scripts/pipeline_driver.py or the selected workflow phase adapter without enabling arbitrary shell text.
- [ ] T012 [P] [US2] Update docs/governance/shell-hook-guards.md with the reviewed command contract, output channels, and protected-effect boundary.

**Checkpoint**: Any effective command differing from the reviewed contract is rejected before process creation.

## Phase 4: Pre-Implementation Workflow Adapters

**Purpose**: Run generative pre-implementation phases from prompt to validated handoff.

- [ ] T013a [US1] Define declarative phase-adapter contracts in scripts/speckit_workflow_adapter.py for declared inputs, template, output, mutation scope, runner, validator, diagnostics, success event, and side-effect boundary.
- [ ] T013b [US1] Register and resolve the ordered `orchestrate -> extract -> scaffold -> LLM Action -> validate -> emit/handoff` phase contracts in scripts/speckit_workflow_adapter.py, rejecting missing or incompatible contract declarations before a phase runs.
- [ ] T013c [US1] Implement the phase-adapter execution boundary in scripts/speckit_workflow_adapter.py so it invokes the declared runner and validator, exposes declared diagnostics, and permits success-event or handoff requests only after a valid contract outcome.
- [ ] T014 [US1] Wire specify-phase generation so scripts/speckit_specify_step.py cannot emit success after scaffold-only or failed fill.
- [ ] T015 [P] [US1] Add validator outcome models in scripts/speckit_workflow_outcomes.py for pass, recoverable retry, human pause, transient dependency failure, terminal machine failure, and completed states.
- [ ] T016 [P] [US1] Add unit tests for workflow adapter success/failure gates in tests/unit/test_speckit_workflow_adapter.py.

**Checkpoint**: Generated artifacts must pass phase-specific deterministic gates before success events are requested.

## Phase 5: Loop, Human Pause, and Handoff Policy

**Purpose**: Make autonomous continuation safe and stop only for classified reasons.

- [ ] T017 [US1] Add loop policy support in scripts/speckit_workflow_loops.py for `while` and `do-while` repair/convergence using latest persisted validator or task output, finite budgets, deterministic conditions, and post-loop assertions.
- [ ] T018 [P] [US1] Add loop tests in tests/unit/test_speckit_workflow_loops.py covering stale output, cap exhaustion, malformed condition output, recoverable retry, and no false success.
- [ ] T019 [US2] Add human intervention policy in scripts/speckit_human_policy.py with reason codes, authority, required information, allowed choices, prohibited effects, and typed resume validation.
- [ ] T020 [P] [US2] Add human policy tests in tests/unit/test_speckit_human_policy.py for material ambiguity, mandated approval, sensitive access, destructive work, external effect, drift, exhausted recovery, and unauthorized resume.

**Checkpoint**: Validated machine-decidable phases continue automatically; protected effects pause before mutation.

## Phase 6: Durable Resume, Reconciliation, Lease, and Envelope

**Purpose**: Allow a fresh agent or downstream implementation workflow to resume safely.

- [ ] T021a [US3] Add reconciliation evidence collection in scripts/speckit_workflow_reconcile.py for workflow cursor, pipeline ledger, task/planning evidence, runtime results, artifacts, manifest, versions, and the current feature lease.
- [ ] T021b [US3] Implement deterministic cross-authority drift and compatibility evaluation in scripts/speckit_workflow_reconcile.py that returns explicit conflicts, bounded diagnostic pointers, and one non-mutating next action instead of selecting state silently.
- [ ] T021c [US3] Add lease-aware idempotent replay and next-boundary reconciliation decisions in scripts/speckit_workflow_reconcile.py so committed events, attempts, artifact state, and the cursor converge without duplicate effects.
- [ ] T022 [P] [US3] Add reconciliation tests in tests/unit/test_speckit_workflow_reconcile.py for drift blocking, non-mutating next action, duplicate event idempotency, version incompatibility, and missing artifact pointers.
- [ ] T023 [US3] Add or extend feature lease handling in scripts/feature_lock.py and the workflow adapter for acquire, renew, release, pause, expiry, and recovery behavior.
- [ ] T024 [US3] Add implementation-ready handoff envelope generation in scripts/speckit_handoff_envelope.py with identity, phase/task attempt, last event, pending reason, permitted action, next step, versions, lease, and diagnostic pointers.
- [ ] T025 [P] [US3] Add envelope tests in tests/unit/test_speckit_handoff_envelope.py for compact JSON stdout, stderr diagnostics, artifact pointers, redaction, and downstream implementation workflow handoff.

**Checkpoint**: One status result gives complete next-action context without direct JSONL inspection.

## Phase 7: Live Verification and Documentation

**Purpose**: Prove prompt-to-handoff behavior and document operator use.

- [ ] T026a [US5] Add a pinned-engine live verification harness in tests/integration/test_speckit_workflow_live.py that boots a feature from a prompt and records bounded, machine-readable evidence for the governed workflow run.
- [ ] T026b [US5] Add live tests in tests/integration/test_speckit_workflow_live.py for reviewed command validation, bounded repair, and classified pause/resume using the pinned-engine harness.
- [ ] T026c [US5] Add live fault-and-resume tests in tests/integration/test_speckit_workflow_live.py for crash recovery, implementation-ready handoff convergence, and terminal reconciliation without starting implementation work.
- [ ] T027 [P] [US5] Add clean-checkout and rollback rehearsal tests in tests/integration/test_speckit_upgrade_rehearsal.py.
- [ ] T028 [P] [US5] Add security fixture tests in tests/unit/test_speckit_workflow_security.py for traversal, interpolation, cwd, executable, secret, output, timeout, and protected-effect boundaries.
- [ ] T029 [US5] Update governance documentation in docs/governance/phase-execution.md and docs/governance/shell-hook-guards.md for the prompt-to-handoff process model, runtime owner, readiness gate, pause/resume, diagnostics, and implementation workflow boundary.
- [ ] T030 [US5] Run final solution gates in scripts/speckit_solution_step.py and scripts/speckit_tasking_chain.py for task graph, HUD validation, acceptance scaffolding, ledger registration, and prompt-to-handoff verification evidence.

**Checkpoint**: The feature is ready for `/speckit.implement`; implementation itself has not started.

## Dependencies & Execution Order

- Phase 1 must complete before any route or adapter mutation.
- Phase 2 must complete before workflow adapter routes are enabled.
- Phase 3 must complete before any upstream `shell` step can execute repository commands.
- Phase 4 depends on Phases 1 through 3.
- Phase 5 depends on Phase 4 outcome contracts.
- Phase 6 depends on ledger, outcome, and adapter contracts from Phases 2 through 5.
- Phase 7 depends on all previous phases and proves the complete prompt-to-handoff path.

## Parallel Opportunities

- T002 and T004 can run after their paired implementation tasks are drafted.
- T006 and T007 can run in parallel after T005.
- T010 and T012 can run in parallel after T009c is complete.
- T015 and T016 can run in parallel with T014 after T013c is complete.
- T018 and T020 can run in parallel after T017 and T019 are defined.
- T022 and T025 can run in parallel after T021c and T024 define shared envelope contracts.
- T027 and T028 can run in parallel with documentation after the verification fixtures are stable.

## Implementation Strategy

1. Deliver the baseline/preflight and manifest ownership first so downstream tasks have stable contracts.
2. Add safe command execution before any workflow `shell` route is enabled.
3. Add phase adapters, loop policy, human policy, and reconciliation in that order.
4. Finish with live prompt-to-handoff verification and governance docs.
5. Stop at `/speckit.implement` readiness; do not execute implementation in this workflow.

## Notes

- All tasks are implementation tasks for the future `/speckit.implement` workflow; this solution phase only prepares tasking artifacts.
- No task may start implementation execution, task closeout, QA closeout, commit/push of implementation work, publication, merge, deployment, or external side effects.
- Tests must be written to fail before implementation where applicable.

## Plan Design Slice Index

- PL-01 maps to T001-T004.
- PL-02 maps to T005-T008.
- PL-03 maps to T009-T012.
- PL-04 maps to T013-T016.
- PL-05 maps to T017-T020.
- PL-06 maps to T021-T025.
- PL-07 maps to T026-T030.
