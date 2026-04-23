# Effort Estimate: Deterministic Phase Orchestration

**Date**: 2026-04-22 | **Total Points**: 47 | **T-shirt Size**: L  
**Estimated by**: AI (speckit.estimate) — calibrated to existing repo seams and prior deterministic flow patterns.

---

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T001 | 2 | Shared feature-flow fixture seam | Existing integration harness extension with low uncertainty. |
| T002 | 2 | Runner-adapter helper seam | Local contract-helper additions in one test surface. |
| T003 | 3 | Runtime envelope hardening | Core execution seam with multiple deterministic failure branches. |
| T004 | 3 | Ledger-authoritative phase resolution | State reconciliation + reason-code semantics in critical flow. |
| T005 | 3 | Transition/append contract enforcement | Sequence authority and mutation guards across ledger boundary. |
| T006 | 3 | Manifest route + emit normalization | Contract parsing plus deterministic rejection behavior. |
| T007 | 2 | Unit validate-before-emit tests | Focused assertions in existing unit suite. |
| T008 | 2 | Integration blocked-validation tests | Known integration fixture path with bounded setup. |
| T009 | 3 | Success-append behavior wiring | Driver append seam change with parse-failure protections. |
| T010 | 2 | Approval deny/invalid integration tests | Adds branch coverage with existing flow harness. |
| T011 | 2 | Approval gate implementation | Constrained runtime gate path update in one module. |
| T012 | 2 | Doc-shape/manifest contract tests | Existing doc-shape rules extended for this feature. |
| T013 | 3 | Producer-only doc contract alignment | Multi-doc + manifest consistency updates. |
| T014 | 3 | Canonical trigger/rerun-overreach tests | Integration branching around deterministic policy edges. |
| T015 | 2 | Legacy/generative migration regression | Existing migration test seam extension. |
| T016 | 3 | Canonical trigger route implementation | Driver mapping branch logic with reason-code outputs. |
| T017 | 3 | Implement phase-close orchestration | Cross-module closeout seam with once-only emission rules. |
| T018 | 2 | Implement idempotency regressions | Additional deterministic assertions in current test suite. |
| T019 | 2 | Runner-adapter parse-failure coverage | Contract assertions for no-emit on parse failure. |
| T020 | 1 | Human dry-run/live-run evidence capture | Manual validation and quickstart evidence updates. |

---

### T003 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:run_step` to normalize success/blocked/error envelopes with deterministic reason fields.  
**Create**: none.  
**Reuse**: existing runtime failure sidecar path and envelope schema checks.  
**Composition**: validate subprocess result shape, map to deterministic envelope, preserve debug sidecar path on failures.  
**Failing test assertion**: malformed result payload cannot produce `ok=true` and cannot advance phase.  
**Domains touched**: deterministic runtime, orchestration.

### T004 — Solution Sketch

**Modify**: `scripts/pipeline_driver_state.py:resolve_phase_state` to prioritize ledger truth and emit machine-readable drift reasons.  
**Create**: none.  
**Reuse**: current phase resolution event stream reads and lock checks.  
**Composition**: compute current phase from ledger, compare hints, produce deterministic drift metadata where mismatched.  
**Failing test assertion**: stale hint cannot override ledger-derived phase.  
**Domains touched**: state authority, reliability.

### T005 — Solution Sketch

**Modify**: `scripts/pipeline_ledger.py:validate_sequence` and append guard checks for strict transition-map enforcement.  
**Create**: none.  
**Reuse**: current append command contract and transition definitions.  
**Composition**: pre-validate event predecessor constraints, reject invalid transitions before any append side effect.  
**Failing test assertion**: invalid predecessor event returns rejected outcome and ledger file remains unchanged.  
**Domains touched**: governance ledger, sequence safety.

### T006 — Solution Sketch

**Modify**: `scripts/pipeline_driver_contracts.py:load_driver_routes` to enforce explicit route metadata and deterministic unknown-mode failure.  
**Create**: none.  
**Reuse**: existing mode normalization and emit-contract parsing seams.  
**Composition**: parse manifest route entries, validate required fields, return normalized map consumed by runtime dispatch.  
**Failing test assertion**: unknown mode returns deterministic contract error and no fallback route is selected.  
**Domains touched**: command contract, routing.

### T009 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:append_pipeline_success_event` to append only after validated success and parse-safe route resolution.  
**Create**: none.  
**Reuse**: existing append command invocation flow and sequence validation checks.  
**Composition**: enforce validate-before-emit boundary, short-circuit append on invalid payload/result, preserve explicit error envelope.  
**Failing test assertion**: parse failure in step result emits no completion event.  
**Domains touched**: event emission, deterministic gating.

### T013 — Solution Sketch

**Modify**: `.claude/commands/speckit.{sketch,solution,implement}.md` and `command-manifest.yaml` contract wording/metadata alignment.  
**Create**: none.  
**Reuse**: compact/expanded command template structure and manifest emit contracts.  
**Composition**: remove direct gate/append procedures from docs, retain producer payload expectations, align manifest route declarations.  
**Failing test assertion**: doc-shape validator flags any command doc that reintroduces executable gate/ledger append instructions.  
**Domains touched**: governance docs, contract consistency.

### T014 — Solution Sketch

**Modify**: integration flow tests around canonical trigger vs direct invocation branch outcomes.  
**Create**: none.  
**Reuse**: `test_pipeline_driver_feature_flow` scenario harness and deterministic reason checks.  
**Composition**: encode allowed rerun branch and forward-overreach blocked/redirected branch assertions.  
**Failing test assertion**: direct forward progression beyond allowed latest step is blocked with explicit reason code.  
**Domains touched**: trigger policy, regression safety.

### T016 — Solution Sketch

**Modify**: `scripts/pipeline_driver.py:resolve_step_mapping` for canonical trigger routing and direct-invocation policy handling.  
**Create**: none.  
**Reuse**: manifest-derived route map and phase resolution output.  
**Composition**: route `/speckit.run` as canonical path, allow direct reruns at/below allowed step, block/redirect forward overreach.  
**Failing test assertion**: direct rerun at current step is permitted while next-step overreach is rejected deterministically.  
**Domains touched**: orchestration routing, progression control.

### T017 — Solution Sketch

**Modify**: `scripts/speckit_implement_gate.py` and driver closeout append boundary for once-only `implementation_completed`.  
**Create**: none.  
**Reuse**: task-ledger assertions and pipeline append sequencing rules.  
**Composition**: run implement close predicates, append terminal event only on close-pass, enforce idempotent retries.  
**Failing test assertion**: implement close failure cannot emit `implementation_completed`.  
**Domains touched**: implement lifecycle, terminal emission safety.

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 4 | 2 | 2 |
| Phase 2: Foundational | 12 | 4 | 0 |
| Phase 3: US1 | 7 | 3 | 2 |
| Phase 4: US2 | 4 | 2 | 1 |
| Phase 5: US3 | 5 | 2 | 1 |
| Phase 6: US4 | 8 | 3 | 2 |
| Phase 7: Polish | 7 | 4 | 2 |
| **Total** | **47** | **20** | **10** |

---

## Warnings

- No tasks scored 8 or 13 in the settled estimate set; breakdown loop not required.
- Most uncertainty is concentrated in T003/T016/T017 due to cross-boundary orchestration behavior.
- Human validation task T020 cannot be parallelized with automated runtime verification evidence generation.
