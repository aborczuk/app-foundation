# Effort Estimate: Autonomous Spec Pipeline Upgrade

**Date**: 2026-07-10 | **Total Points**: 153 (re-estimated after breakdown) | **T-shirt Size**: XL
**Estimated by**: AI (`speckit.estimate`) — calibrate against actuals after implementation.

---

## Estimation Gate Status

The mandatory point-breakdown gate is **clear**: all 38 current tasks score 5 points or fewer. This re-estimate supersedes the former four 8-point parent tasks (`T009`, `T013`, `T021`, and `T026`) with their completed bounded suffix-task breakdowns. HUD implementation-ticket completeness remains owned by `/speckit.tasking`; this estimate does not alter task or HUD content.

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T001 | 5 | Pinned capability preflight | New preflight contract must parse CLI JSON and enforce release, root, feature, and version invariants. |
| T002 | 3 | Preflight unit coverage | Focused failure matrix against the new preflight seam. |
| T003 | 5 | Upgrade inventory and rehearsal | New inventory, hashing, clean-checkout inputs, and rollback-evidence contract. |
| T004 | 3 | Inventory unit coverage | Focused classification and rollback-metadata cases. |
| T005 | 5 | Manifest ownership routing | Extends the central command manifest across ownership, route, validator, provenance, and event contracts. |
| T006 | 5 | Manifest validation | Extends the existing validator to reject ambiguous production routes and validate new ownership fields. |
| T007 | 3 | Manifest consistency tests | Covers defined manifest invariants and retained route constraints. |
| T008 | 3 | Command-source compatibility mapping | Updates the Codex/Claude command surfaces to use the canonical start-or-resume route. |
| T009a | 3 | Command-adapter policy contracts | Defines the allowlisted executable/argv, validated request, root-cwd, and permission boundary in one module. |
| T009b | 3 | Validated-request runner | Adds bounded root-cwd process execution and structured result capture behind the defined contract. |
| T009c | 3 | Result redaction and envelope | Finalizes caps, protected-value redaction, and actionable structured policy/runner failures. |
| T010 | 5 | Adapter security tests | Broad adversarial contract matrix for the command adapter. |
| T011 | 5 | Adapter routing integration | Connects the safety boundary into the existing pipeline driver/phase adapter without reintroducing shell text. |
| T012 | 2 | Shell-guard governance docs | Narrow documentation update for the already-defined reviewed command contract. |
| T013a | 3 | Phase-adapter declarative contracts | Defines bounded phase declarations for inputs, outputs, runner, validator, diagnostics, events, and effects. |
| T013b | 3 | Phase-contract registration and resolution | Registers ordered phase contracts and rejects missing or incompatible declarations before execution. |
| T013c | 5 | Phase-adapter execution boundary | Invokes declared runners and validators while enforcing post-validation-only event and handoff behavior. |
| T014 | 5 | Specify-phase success gate | Modifies the existing specify step so incomplete generation cannot emit success. |
| T015 | 3 | Validator outcome models | Bounded typed outcome model supporting the defined retry, pause, failure, and completion states. |
| T016 | 3 | Workflow-adapter tests | Focused success/failure-gate coverage for the new adapter seam. |
| T017 | 5 | Loop policy | Implements bounded structured loops, persisted-output selection, and deterministic post-loop assertions. |
| T018 | 3 | Loop tests | Focused stale-output, exhaustion, malformed-condition, retry, and false-success cases. |
| T019 | 5 | Human intervention policy | New reason/authority/effect/resume contract at a protected workflow boundary. |
| T020 | 3 | Human-policy tests | Defined reason-code and unauthorized-resume matrix. |
| T021a | 3 | Reconciliation evidence collection | Collects cursor, ledger, planning, runtime, artifact, manifest, version, and lease evidence without mutation. |
| T021b | 5 | Drift and compatibility evaluation | Implements cross-authority conflict evaluation with bounded diagnostics and one non-mutating next action. |
| T021c | 5 | Lease-aware idempotent replay | Adds replay and boundary reconciliation so attempts, events, artifacts, and cursor converge without duplicate effects. |
| T022 | 5 | Reconciliation tests | Multi-source drift, idempotency, compatibility, and missing-pointer cases. |
| T023 | 5 | Feature lease lifecycle | Extends existing locking across acquisition, renewal, pause, expiry, recovery, and workflow integration. |
| T024 | 5 | Handoff envelope | New compact contract combines identity, state, permissions, versions, lease, and diagnostics. |
| T025 | 3 | Envelope tests | Focused stdout/stderr, redaction, pointer, and downstream-handoff coverage. |
| T026a | 5 | Pinned-engine live harness | Builds the live prompt-to-handoff harness and bounded machine-readable evidence capture. |
| T026b | 5 | Live command, repair, and pause tests | Exercises reviewed-command validation, bounded repair, and classified pause/resume on the live harness. |
| T026c | 5 | Live fault and resume tests | Exercises crash recovery, handoff convergence, and terminal reconciliation without implementation start. |
| T027 | 5 | Upgrade rehearsal integration tests | Clean-checkout and rollback verification against the upgrade boundary. |
| T028 | 5 | Security fixture tests | Broad policy-boundary fixtures across traversal, interpolation, secrets, output, timeout, and effects. |
| T029 | 3 | Governance documentation | Two governance documents must capture the defined runtime and operator process model. |
| T030 | 3 | Final solution gates | Executes and records the defined tasking/HUD/acceptance/ledger/prompt-to-handoff readiness evidence. |

Solution sketches for 3+ point tasks are intentionally omitted: their required design details must come from completed HUDs, and estimation must not invent them.

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup and Upgrade Baseline | 16 | 4 | 2 |
| Phase 2: Manifest and Ownership Routing | 16 | 4 | 2 |
| Phase 3: Safe Command and Shell Adapter | 21 | 6 | 2 |
| Phase 4: Pre-Implementation Workflow Adapters | 22 | 6 | 2 |
| Phase 5: Loop, Human Pause, and Handoff Policy | 16 | 4 | 2 |
| Phase 6: Durable Resume, Reconciliation, Lease, and Envelope | 31 | 7 | 2 |
| Phase 7: Live Verification and Documentation | 31 | 7 | 2 |
| **Total** | **153** | **38** | **14** |

## Warnings

- No current task scores 8 or 13 points; the mandatory breakdown/re-estimate loop is complete for point-based warnings.
- The feature remains high risk because it spans pinned upstream behavior, command safety, durable multi-authority state, and live-engine verification. The 153-point total is an estimate, not an implementation commitment.
- Non-point HUD completeness remains governed by `/speckit.tasking`; this command intentionally preserves HUD content rather than adding missing implementation design.

## Changes from Previous Estimate

- Replaced `T009` (8) with `T009a` (3), `T009b` (3), and `T009c` (3).
- Replaced `T013` (8) with `T013a` (3), `T013b` (3), and `T013c` (5).
- Replaced `T021` (8) with `T021a` (3), `T021b` (5), and `T021c` (5).
- Replaced `T026` (8) with `T026a` (5), `T026b` (5), and `T026c` (5).
- Task count changed from 30 to 38 and total points from 137 to 153; no unchanged task was rescored.

## Required Next Action

Run `/speckit.implement` when the tasking-owned HUD completeness gate is satisfied. No `estimation_completed` event was emitted in this run because the requested scope is limited to the command-owned estimate artifact.
