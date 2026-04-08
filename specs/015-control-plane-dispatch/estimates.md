# Effort Estimate: ClickUp + n8n Operational Control Plane — Phase 1: Event-Driven Workflow Dispatch

**Date**: 2026-04-02 | **Total Points**: 145 | **T-shirt Size**: L
**Estimated by**: AI (speckit.estimate) — calibrate against actuals after implementation

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T001 | 1 | Create control-plane package scaffold | New package init under `src/clickup_control_plane/` is a trivial greenfield scaffold. |
| T002 | 3 | Implement runtime env-var configuration and required API key validation | Mirrors validation patterns in `src/csp_trader/config.py` while adding control-plane specific env guards. |
| T003 | 2 | Add allowlist/workflow mapping example configuration | New static config artifact with bounded schema and no runtime integration complexity. |
| T004 | 1 | Add operator env template for control-plane secrets | Single-file env template creation with straightforward key listing. |
| T005 | 1 | Create control-plane test package scaffolding | Minimal package scaffolding aligned with existing `tests/unit` and `tests/integration` layout. |
| T006 | 2 | Add operator API-key placement checkpoint and verification section | Focused documentation update in existing quickstart flow. |
| T007 | 3 | Implement normalized webhook event and dispatch decision schemas | Medium modeling task with strict enum/shape requirements from `data-model.md` and contract decisions. |
| T008 | 3 | Implement ClickUp webhook signature verification helpers | Security boundary implementation with deterministic reject behavior similar to typed error handling in `mcp_trello`. |
| T009 | 3 | Implement allowlist and routing-metadata policy evaluator | Multi-branch policy logic but localized to one module and explicit rules from spec FRs. |
| T010 | 5 | Implement SQLite state store schema and atomic dedupe+active-run transaction boundaries | High-impact persistence logic spanning transaction semantics, lock invariants, and idempotent dedupe. |
| T011 | 3 | Add rollback/no-partial-write transaction regression tests | Medium failure-path test matrix validating ACID behavior in new state-store paths. |
| T012 | 3 | Implement stale active-run reconciliation service | Reconciliation logic crosses local DB + live ClickUp state and needs careful stale-state transitions. |
| T013 | 3 | Add stale/orphan local-state reconciliation regression tests | Integration validation of startup/reconnect reconciliation behavior with drift-oriented assertions. |
| T014 | 3 | Implement ClickUp outcome writer with redacted operator-safe messages | HTTP client + safe message shaping modeled after `src/mcp_trello/trello_client.py` typed/sanitized boundaries. |
| T015 | 5 | Implement n8n dispatch client with explicit timeout/cancel lifecycle handling | Async external call lifecycle (timeouts/cancel/shutdown) with failure-mode handling across process boundaries. |
| T016 | 3 | Add running-loop async lifecycle regression tests | Event-loop safety tests are medium complexity and must prove no nested loop/lifecycle regressions. |
| T017 | 5 | Implement FastAPI startup/shutdown dependency wiring and reconciliation bootstrap | App lifecycle orchestration across multiple new modules and startup-state integrity gating. |
| T018 | 3 | Add webhook contract coverage for accepted/error envelopes | New contract test suite verifying decision and error shape commitments in contract doc. |
| T019 | 2 | Add signature acceptance/rejection unit tests | Focused auth branch testing with predictable inputs/outcomes. |
| T020 | 2 | Add allowlist and missing-routing-metadata unit tests | Constrained policy-unit matrix with clear branch expectations. |
| T021 | 5 | Add happy-path trigger-to-dispatch-to-outcome integration test | Full-path integration across endpoint, policy, state store, n8n dispatch, and ClickUp outcome writeback. |
| T022 | 5 | Add duplicate replay-burst idempotency integration test | Replay burst behavior requires durable dedupe assertions and dispatch count correctness under load. |
| T023 | 3 | Add one-active-run guard integration test | Concurrency guard integration is medium due timing/state assertions. |
| T024 | 3 | Add out-of-scope and missing-metadata indicator integration tests | Multi-branch operator-visible rejection behavior across two policy denial modes. |
| T025 | 3 | Add schema-mismatch blocked-indicator integration test | Failure-path integration with explicit blocked-task outcome assertions. |
| T026 | 3 | Implement webhook endpoint request validation and response contract | Endpoint-level request/response contract wiring with validation and sanitized error mapping. |
| T027 | 5 | Implement dispatch orchestration service for policy→state→dispatch decisions | Core orchestration module coordinates multiple dependencies and terminal decision paths. |
| T028 | 3 | Wire endpoint orchestration across policy, state store, dispatcher, and ClickUp client | Medium wiring effort with dependency injection and response normalization concerns. |
| T029 | 3 | Implement workflow-type routing and n8n trigger payload builder | Deterministic mapping logic with moderate request-shape validation requirements. |
| T030 | 5 | Implement one-active-run enforcement and dedupe decision persistence | Stateful decision/write ordering under concurrent events with strict durability requirements. |
| T031 | 3 | Implement operator-visible outcome templates for all terminal decisions | Medium templating and reason-code mapping task tied to contracted operator messaging. |
| T032 | 3 | Implement schema-mismatch detection and blocked-task outcome path | Additional guarded branch integrated into outcome writer and decision pipeline. |
| T033 | 3 | Enforce reconciliation checkpoint before dispatch lock acquisition | Medium safety gate joining reconciliation state with live dispatch execution path. |
| T034 | 3 | Add no-unresolved-drift integration assertion after reconciliation | Integration assertion work validating state-safety invariant after reconciliation. |
| T035 | 3 | Add cross-scenario orphan async-task cleanup validation | Medium async teardown coverage across multiple scenario outcomes. |
| T036 | 3 | Add impossible-state/no-partial-write validation coverage | Medium invariant testing over negative persistence cases in state transitions. |
| T037 | 2 | Update adopted dependency setup and failure-mode troubleshooting | Documentation refinement for ClickUp+n8n operator setup and failure handling. |
| T038 | 1 | Add dependency-security recheck checkpoint | Small checklist addition in existing quickstart workflow. |
| T039 | 1 | Run control-plane contract/unit/integration suites and record verification notes | Execution/recording task with minimal implementation complexity. |
| T040 | 3 | Add signature+policy latency benchmark test asserting p95 < 300ms | Medium perf-test harness work in integration suite with repeatable timing assertions. |
| T041 | 3 | Add state-store dedupe/lock latency benchmark test asserting p95 < 50ms | Medium perf regression test in state-store unit context with deterministic instrumentation. |
| T042 | 2 | Add replay-burst benchmark assertion report (100 identical events, zero duplicate dispatches) | Small-to-medium extension of replay integration path with benchmark output assertions. |
| T043 | 3 | Add stale out-of-order event regression test and `stale_event` assertion | Medium integration regression for newly introduced stale-event decision branch. |
| T044 | 5 | Implement stale-event ordering decision handling in service and state store | Cross-module logic update (service + persistence) with ordering semantics and decision persistence. |
| T045 | 3 | Add action-scope violation regression test | Medium negative-path integration coverage for new scope-violation policy branch. |
| T046 | 5 | Implement action-scope guard enforcement in policy and service | Cross-module enforcement update with policy mapping, orchestration integration, and operator-safe outcomes. |
| T047 | 3 | Implement dedicated local offline QA runner with task handoff payload + explicit PASS/FIX_REQUIRED verdict output | New script under `scripts/` with local handoff parsing, verdict normalization, and deterministic machine-readable output contract. |
| T048 | 2 | Wire offline QA runner usage into implementation workflow docs | Cross-doc workflow wiring in `.claude/commands/speckit.implement.md` and `.speckit/README.md` to align runtime process and task lifecycle expectations. |

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 10 | 6 | 3 |
| Phase 2: Foundational | 39 | 11 | 3 |
| Phase 3: User Story 1 (P1) | 57 | 17 | 3 |
| Phase 4: Polish & Cross-Cutting | 34 | 12 | 4 |
| Ad-Hoc Tasks | 5 | 2 | 0 |
| **Total** | **145** | **48** | **13** |

## Changes from Previous Estimate

- Previous estimate (2026-04-02): **140 points**, **46 tasks**.
- Current estimate: **145 points**, **48 tasks**.
- Net change: **+5 points** and **+2 tasks**.
- Added tasks: `T047`, `T048`.
- Existing tasks retained original scoring; increase is driven by adding the offline QA runner and workflow wiring tasks.

## Risk-Adjusted Estimate

- **Optimistic** (0.8x): 116.0 points — if external integration behavior matches assumptions and benchmark tuning is straightforward
- **Expected** (1.0x): 145 points — baseline estimate
- **Pessimistic** (1.5x): 217.5 points — if async lifecycle/state guard regressions require multiple refinement passes

## Warnings

- No tasks scored 8 or 13; breakdown loop is clear.
- Highest uncertainty tasks: **T010, T015, T017, T021, T022, T027, T030, T044, T046, T047** (cross-boundary async/state coordination and local QA handoff contract hardening).
- Data-model decision enums were expanded in spec/contracts; keep implementation enum definitions in `schemas.py` aligned during build-out.
