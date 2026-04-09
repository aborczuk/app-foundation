# Effort Estimate: ClickUp + n8n Operational Control Plane — Phase 3 HITL Auditability

**Date**: 2026-04-04  
**Total Points**: 100  
**T-shirt Size**: N/A (not specified in spec.md)  
**Estimated by**: AI (`speckit.estimate`) calibrated to current codebase complexity

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T000 | 1 | Validate ingress/runtime gate evidence in tasks.md | Documentation and checklist validation only |
| T001 | 2 | Verify HITL env keys in `config.py` | Single-file config review/update with existing loader pattern |
| T002 | 2 | Validate completion/HITL contract doc | Contract doc alignment task without runtime coupling |
| T003 | 5 | Paused-run persistence schema/APIs in `state_store.py` | Large state module (`684` LOC) with migration + API invariants |
| T004 | 3 | Idempotent non-dispatch processed-event helpers | Moderate transaction semantics in existing store patterns |
| T005 | 3 | Resume/cancel transport paths in `dispatcher.py` | Medium async transport work in bounded client module |
| T006 | 3 | Outcome rendering for resumed/cancelled/timeout | Medium logic branching in `clickup_client.py` templates |
| T007 | 5 | Reconciliation ordering in `service.py` | High-impact orchestration logic inside `902` LOC service |
| T008 | 5 | Transaction-boundary safeguards in `state_store.py` | Multi-step commit/rollback guarantees touching core lifecycle data |
| T009 | 3 | Foundational rollback/idempotency regressions | Medium test expansion around DB failure/replay paths |
| T010 | 2 | Schema tests for `waiting_input` requirements | Straightforward unit assertions in existing schema suite |
| T011 | 2 | Contract tests for completion callback rules | Contract surface already established; additive scenarios |
| T012 | 3 | Integration wait-to-resume via `HITL_RESPONSE:` | Cross-module integration test in large harness file |
| T013 | 3 | Running-loop async lifecycle regression | Moderate async regression coverage with event-loop expectations |
| T014 | 3 | Timeout-to-blocked re-dispatch regression | Multi-step scenario but follows existing integration pattern |
| T015 | 5 | `waiting_input` callback handling in `app.py` | Endpoint flow + ClickUp write + state-store mutation in `560` LOC module |
| T016 | 5 | Operator-response resume orchestration in `service.py` | Complex branching and state interactions in core orchestrator |
| T017 | 3 | Timeout blocked-status + advisory cleanup | Medium completion-path logic with existing helper reuse |
| T018 | 3 | No-orphan advisory-state validation | Medium integration assertions for cleanup invariants |
| T019 | 3 | Manual cancel integration regression | Multi-event lifecycle scenario across webhook + dispatcher |
| T020 | 2 | Cancel payload unit coverage | Isolated dispatcher unit assertions |
| T021 | 2 | Outcome rendering unit tests | Small deterministic output assertions |
| T022 | 3 | Reconciliation regression on cancel endpoint failure | Medium negative-path integration coverage |
| T023 | 3 | Manual cancel signal detection logic | Moderate status-transition logic in existing service |
| T024 | 5 | Cancel dispatch + release/cleanup + persistence | Core multi-step orchestration with side-effect guarantees |
| T025 | 3 | Operator-safe lifecycle completion summaries | Medium formatting/guarding logic in app completion path |
| T026 | 2 | Full control-plane suite run task | Execution/verification task across existing tests |
| T027 | 2 | Pyright validation for touched modules | Bounded type-check task on known file set |
| T028 | 2 | Behavior-map update | Focused documentation synchronization task |
| T029 | 2 | Runbook/evidence updates in quickstart | Focused doc update with known scenarios |
| T030 | 2 | Async cleanup cross-story validation | Additive verification assertions in existing integration suite |
| T031 | 2 | Transaction-integrity cross-story validation | Additive unit/integration assertions for impossible states |
| T032 | 2 | Multi-run chronological audit integration scenario | Focused integration scenario using existing harness with explicit history assertions |
| T033 | 2 | Full lifecycle phase contract assertions | Additive contract checks for required lifecycle phase coverage |
| T034 | 2 | Repo-local Codex `SessionStart` required-doc context hook | Small bounded governance automation: one hook config + one script reading known files |

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 5 | 3 | 2 |
| Phase 2: Foundational | 27 | 7 | 3 |
| Phase 3: US1 (P1) | 29 | 9 | 3 |
| Phase 4: US2 (P2) | 21 | 7 | 3 |
| Phase 5: Polish | 18 | 9 | 2 |
| **Total** | **100** | **35** | **13** |

## Warnings

- No tasks scored `8` or `13`; no mandatory breakdown loop required.
- Highest-risk tasks are `T007`, `T008`, `T015`, `T016`, and `T024` (5 points) due to orchestration/state coupling across `app.py`, `service.py`, and `state_store.py`.

## Risk-Adjusted Range

- Baseline: **100 points**
- Risk-adjusted range: **88-114 points** based on integration-test variability and state-machine edge-case handling.
