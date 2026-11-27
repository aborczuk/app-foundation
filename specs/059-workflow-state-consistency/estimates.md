# Effort Estimate: Workflow State Consistency

**Date**: 2026-11-27 | **Total Points**: 37 | **T-shirt Size**: M
**Estimated by**: AI (speckit.estimate)

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T001 | 2 | Add canonical `normalize_feature_id()` helper in `scripts/pipeline_ledger.py` | Small, pure validation/normalization function with clear regex contract. |
| T002 | 2 | Add failing unit tests for deterministic vector edit fingerprinting in `tests/unit/test_read_code_health.py` | Covers edit, refresh, commit, and post-refresh edit cases in an existing test module. |
| T003 | 5 | Replace porcelain-only signature with deterministic content fingerprint across `scripts/read_code_health.py`, `src/mcp_codebase/health.py`, and `scripts/hook_refresh_indexes.py` | One cohesive fingerprinting seam spanning refresh persistence and read-time freshness verification. |
| T004 | 2 | Add failing unit tests for non-destructive `apply_strategy()` and `prepare_tasking()` in `tests/unit/test_plan_step.py` and `tests/unit/test_speckit_solution_step.py` | Targeted regression assertions over existing plan and solution test suites. |
| T005 | 3 | Make `_write_selected_scaffold()` and `apply_strategy()` preserve populated sections in `scripts/speckit_plan_step.py` | Localized section-merge logic inside one file with clear template-preservation rules. |
| T006 | 2 | Guard `prepare_tasking()` to preserve populated `tasks.md` in `scripts/speckit_solution_step.py` | Small existence/content guard before template write in one function. |
| T007 | 2 | Add failing unit tests for `NNN`/`NNN-slug` normalization in `tests/unit/test_pipeline_ledger_sequence.py` and `tests/unit/test_pipeline_driver.py` | Covers append, assert-phase-complete, validate, and malformed-ID rejection. |
| T008 | 3 | Wire `normalize_feature_id()` across `scripts/pipeline_ledger.py`, `scripts/pipeline_driver.py`, and `scripts/pipeline_driver_state.py` | Single cohesive ID-normalization seam with append-only compatibility guarantee. |
| T009 | 2 | Add estimate-to-ledger contract alignment tests in `tests/unit/test_pipeline_ledger_sequence.py` | Verifies docs, manifests, ledger transitions, and driver state agree. |
| T010 | 3 | Reconcile estimate command doc, manifests, ledger transitions, and driver state | Synchronizes four declarative/state files around one canonical contract. |
| T011 | 5 | Add live-backend verification tests for vector index refresh and `read_code.py` in `tests/integration/test_live_vector_fingerprint_and_read_code.py` | Exercises real local index refresh, git commit boundary, and live `read_code.py` execution. |
| T012 | 3 | Document migration/compatibility and feature `061` boundary in `docs/governance/pipeline-driver-readme.md` and `docs/governance/speckit-end-to-end.md` | Operator-facing documentation update covering all four state fixes and scope boundary. |
| T013 | 3 | Run full targeted test, ruff, and ledger/manifest validation suite | End-to-end verification across unit, contract, and live-backend suites. |

## Solution Sketch

Each implementation seam maps cleanly to a single cohesive task of 2–5 points:
- **Vector fingerprint seam (`T002`–`T003`, `T011`)**: Unify fingerprint generation across refresh and read checks using tracked/indexed file content digests instead of raw `git status --porcelain` state.
- **Non-destructive scaffolding seam (`T004`–`T006`)**: Merge/preserve populated markdown sections in `speckit_plan_step.py` and skip overwriting populated `tasks.md` in `speckit_solution_step.py`.
- **Feature ID normalization seam (`T001`, `T007`–`T008`)**: Normalize `NNN` and `NNN-slug` via one helper in `pipeline_ledger.py` reused by `pipeline_driver.py` and `pipeline_driver_state.py`.
- **Estimate contract alignment seam (`T009`–`T010`)**: Align `.claude/commands/speckit.estimate.md`, both `command-manifest.yaml` files, `pipeline_ledger.py`, and `pipeline_driver_state.py`.

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup & Contract Baselines | 2 | 1 | 0 |
| Phase 2: User Story 1 (Vector Fingerprinting) | 7 | 2 | 1 |
| Phase 3: User Story 2 (Non-Destructive Scaffolding) | 7 | 3 | 2 |
| Phase 4: User Story 3 (Feature ID Normalization) | 5 | 2 | 1 |
| Phase 5: User Story 4 (Estimate Contract Alignment) | 5 | 2 | 1 |
| Phase 6: User Story 5 (Live Verification & Docs) | 8 | 2 | 1 |
| Phase 7: Verification and Handoff | 3 | 1 | 0 |
| **Total** | **37** | **13** | **6** |

## Warnings

- No task is scored 8 or 13; no further breakdown passes are required.
- Live-backend verification (`T011`) exercises real local index/read-code paths and should run in an isolated temp repo fixture so repository index state is not corrupted.
