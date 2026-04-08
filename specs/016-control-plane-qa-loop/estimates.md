# Effort Estimate: ClickUp + n8n Operational Control Plane — Phase 2: QA Verification & Rework Loop

**Date**: 2026-04-03 | **Total Points**: 91 | **T-shirt Size**: M
**Estimated by**: AI (speckit.estimate)

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T000 | 3 | Resolve ingress/runtime readiness gate failures | Requires runtime routing diagnosis and evidence capture before implementation can proceed safely. |
| T001 | 2 | Add QA loop config/status thresholds | Bounded config extension in existing module. |
| T002 | 1 | Update QA loop config examples/docs | Focused documentation/config sample update. |
| T003 | 1 | Add QA loop module scaffold | Minimal scaffold file creation. |
| T004 | 1 | Add QA loop unit test scaffold | Minimal test scaffold setup. |
| T005 | 2 | Add completion callback contract models | Bounded schema expansion for executor terminal signaling. |
| T006 | 2 | Add completion-token config parsing + callback auth checks | Small config/auth validation extension in existing runtime wiring. |
| T007 | 3 | Implement completion callback path (writeback + lock release) | Multi-branch runtime logic touching outcome writes and lock lifecycle safety. |
| T008 | 2 | Add host Codex webhook runner script | New but contained script with CLI execution + callback posting logic. |
| T009 | 2 | Add completion callback contract tests | Focused acceptance/rejection coverage for callback surface. |
| T010 | 3 | Add integration regression for callback unlock + redispatch | End-to-end state safety regression around lock release sequencing. |
| T011 | 1 | Document completion token + host-runner usage | Focused operational docs/env template update. |
| T012 | 3 | Configure external n8n webhook handlers to invoke host runner | External wiring + verification evidence capture with moderate operational uncertainty. |
| T013 | 3 | Extend QA schemas and failure-report models | Moderate schema expansion aligned to contract fields and decision states. |
| T014 | 3 | Extend dispatcher QA route + payload builder | Adds mapped route and enriched payload shape. |
| T015 | 3 | Implement QA outcome write helpers | Multi-branch outcome formatting and write paths. |
| T016 | 3 | Implement QA policy gates | Branching policy logic for missing criteria and blocked-state behavior. |
| T017 | 5 | Implement QA failure-streak/escalation primitives | Core policy logic with state transitions and threshold invariants. |
| T018 | 3 | Add running-loop lifecycle regression for QA path | Async safety regression in existing dispatcher suite. |
| T019 | 3 | Add blocked-state no-redispatch integration regression | State-safety regression across orchestration and policy behavior. |
| T020 | 3 | Contract coverage for QA pass/fail/escalation | Contract matrix expansion with multiple terminal outcomes. |
| T021 | 3 | Unit tests for streak increment/reset logic | Deterministic policy-unit matrix with reset edge cases. |
| T022 | 3 | Integration test for QA pass path | End-to-end pass transition validation. |
| T023 | 3 | Integration test for fail-to-build + report | End-to-end fail branch and payload validation. |
| T024 | 3 | Integration test for third-fail escalation | Escalation threshold behavior across repeated attempts. |
| T025 | 3 | Integration test for manual unblock reset | Human-unblock path and counter reset assertions. |
| T026 | 5 | Implement QA attempt evaluation service | New service module coordinating outcome semantics and attempt state. |
| T027 | 5 | Wire QA loop into orchestration flow | Cross-module orchestration updates in existing core service. |
| T028 | 3 | Wire endpoint response mapping for QA decisions | Endpoint response normalization for added decisions. |
| T029 | 3 | Implement missing-criteria short-circuit path | Negative-path handling with operator-visible outcomes. |
| T030 | 3 | Implement fail-to-build transition + structured report | Outcome branch with strict structured report contract. |
| T031 | 5 | Implement blocked-after-3-fails + redispatch reject | Critical escalation gating across policy + QA service. |
| T032 | 3 | Implement manual-unblock reset flow | Reset and re-enable automation path wiring. |
| T033 | 3 | Attach prior failure context and artifacts | Payload/context propagation across dispatcher and outcome writer. |
| T034 | 3 | Add cross-scenario async cleanup/no-orphan validation | Cross-scenario lifecycle cleanup assertions. |
| T035 | 3 | Add stale/out-of-order QA event regression | Ordering/regression safety for streak integrity. |
| T036 | 2 | Update troubleshooting and verification runbook | Focused operational doc refinement. |
| T037 | 1 | Add dependency-security recheck notes | Small release checklist addition. |
| T038 | 1 | Run suites and capture verification notes | Execution + documentation capture task. |

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 8 | 5 | 3 |
| Phase 1B: Executor Completion Lane | 18 | 8 | 3 |
| Phase 2: Foundational | 23 | 7 | 2 |
| Phase 3: User Story 1 (P1) | 34 | 14 | 2 |
| Phase 4: Polish & Cross-Cutting | 10 | 5 | 2 |
| **Total** | **91** | **39** | **12** |

## Risk-Adjusted Estimate

- **Optimistic** (0.8x): 73 points
- **Expected** (1.0x): 91 points
- **Pessimistic** (1.4x): 127 points

## Changes from Previous Estimate

- Added blocking Executor Completion Lane tasks (`T005`-`T012`) to capture real coding execution and terminal completion wiring.
- Increased total from `75` to `91` points to reflect executor/callback implementation and remaining external n8n handler wiring.

## Warnings

- No tasks scored 8 or 13; breakdown loop is clear.
- Highest uncertainty tasks: `T017`, `T026`, `T027`, `T031`, `T012`.
- Runtime ingress gate (`T000`) and executor completion lane wiring (`T012`) are resolved; highest uncertainty now concentrates in QA-loop core logic tasks (`T017`, `T026`, `T027`, `T031`).
