# Effort Estimate: Consolidate Edit Validation

**Date**: 2026-11-27 | **Total Points**: 56 | **T-shirt Size**: L
**Estimated by**: AI (speckit.estimate)

## Per-Task Estimates

| Task ID | Points | Seam Boundary | Integration Surface | Rationale |
|---------|--------|---------------|---------------------|-----------|
| T001 | 3 | Shared evidence/freshness/env unit test suite (`tests/unit/test_workflow_evidence.py`) | `scripts/workflow_evidence.py`, `scripts/cgc_owner.py` | Covers content/config/lockfile/selector digest invalidation, atomic persistence, freshness transitions, and `repo_local_tool_env()`. |
| T002 | 5 | Shared stdlib-only state module (`scripts/workflow_evidence.py`) | `.codegraphcontext/workflow-state/`, `scripts/cgc_owner.py` | One cohesive foundation module encapsulating typed models, atomic JSON IO, evidence digests, freshness state, and repo-local tool env. |
| T003 | 2 | PostToolUse hook unit tests (`tests/unit/test_hook_posttool_edit_validation.py`) | `scripts/hook_posttool_edit_validation.py`, `scripts/workflow_evidence.py` | Focused regression tests proving zero intermediate validator/refresh runs and accurate stale-scope marking. |
| T004 | 3 | PostToolUse edit-tracking seam (`scripts/hook_posttool_edit_validation.py`) | `scripts/hook_edit_paths.py`, `scripts/workflow_evidence.py` | Small refactor replacing eager validator/refresh calls with changed-path and stale-scope tracking. |
| T005 | 3 | Edit orchestration unit tests (`tests/unit/test_edit_code_consolidation.py`) | `scripts/edit_code.py`, `scripts/workflow_evidence.py` | Covers shared validate/sync rules, skip-flag removal, evidence reuse/invalidation, and closeout rejection cases. |
| T006 | 5 | Unified validation engine & evidence reuse (`scripts/edit_code.py`) | `scripts/workflow_evidence.py`, `ruff_guard.py`, `pyright_guard.py`, `pytest_guard.py`, `validate_python_docstrings.py` | One cohesive validation seam unifying `validate` and unskippable `sync` with single-run evidence reuse. |
| T007 | 3 | Closeout freshness gate & commit evidence (`scripts/edit_code.py`) | `scripts/workflow_evidence.py`, `scripts/hook_refresh_indexes.py` | Isolated closeout handoff seam verifying/refreshing remaining stale scopes and persisting commit evidence. |
| T008 | 3 | Authoritative read freshness tests (`tests/unit/test_read_code_freshness.py`) | `scripts/read_code.py`, `scripts/read_code_health.py`, `scripts/workflow_evidence.py` | Tests stale-on-read refresh, zero-duplicate clean reads, fail-closed stderr behavior, and non-authoritative `window` reads. |
| T009 | 5 | On-demand freshness enforcement (`scripts/read_code_health.py`, `scripts/read_code.py`, `scripts/hook_refresh_indexes.py`) | `scripts/workflow_evidence.py`, `scripts/cgc_owner.py` | One cohesive freshness seam spanning authoritative read preflight, scoped refresh updates, and fail-closed reporting. |
| T010 | 2 | Git commit safeguard tests (`tests/unit/test_git_commit_safeguards.py`) | `scripts/git_pre_commit_lint.py`, `scripts/git_post_commit_refresh.py` | Focused tests for missing, corrupt/mismatched, and exact-match commit evidence paths. |
| T011 | 3 | Git pre/post-commit fallback seam (`scripts/git_pre_commit_lint.py`, `scripts/git_post_commit_refresh.py`) | `scripts/workflow_evidence.py`, `.githooks/` | Small evidence-verification guard added ahead of existing ruff and refresh fallback calls. |
| T012 | 3 | Bootstrap & sandbox isolation tests (`tests/unit/test_bootstrap_session_isolation.py`) | `scripts/bootstrap_session.py`, `scripts/cgc_safe_index.py`, `scripts/workflow_evidence.py` | Covers healthy-skip behavior, multi-scope failure aggregation, stderr surfacing, and restricted-HOME zero-`~/.codegraphcontext` checks. |
| T013 | 5 | Bootstrap health gate & repo-local CGC isolation (`scripts/bootstrap_session.py`, `scripts/cgc_safe_index.py`, `scripts/cgc_owner.py`, `scripts/read_code.py`, `scripts/hook_refresh_indexes.py`) | `scripts/workflow_evidence.py`, `scripts/read_code_health.py` | One cohesive runtime-isolation seam gating bootstrap indexing, aggregating failures, and wiring `repo_local_tool_env()`. |
| T014 | 5 | Live-backend end-to-end integration tests (`tests/integration/test_live_edit_validation_consolidation.py`) | Real local git repo, validators, `read_code.py`, `bootstrap_session.py`, restricted `HOME` | Constitution IV live-backend verification across the full edit -> freshness -> closeout -> commit -> bootstrap lifecycle. |
| T015 | 3 | Active workflow documentation consolidation (`AGENTS.md`, `docs/governance/shell-hook-guards.md`) | Operator/agent workflow rules and hook docs | Aligns all active docs to a single unambiguous owner per validation, freshness, and commit safeguard seam. |
| T016 | 3 | Final verification pass (`scripts/`, `tests/`) | `pytest_guard.py`, `ruff_guard.py`, `pyright_guard.py`, `validate_python_docstrings.py` | Full targeted unit + live-backend test, lint, static type, and docstring verification across all touched paths. |

## Solution Sketch

Every design slice (`PL-01`–`PL-07`) decomposes into cohesive 2–5 point tasks with clear seam boundaries:
- **Foundation (`T001`–`T002`)**: Single stdlib-only `scripts/workflow_evidence.py` module backed by `.codegraphcontext/workflow-state/` reusing `scripts/cgc_owner.py` content fingerprinting.
- **Edit tracking (`T003`–`T004`)**: `scripts/hook_posttool_edit_validation.py` becomes a fast, non-blocking path/staleness recorder.
- **Validation & closeout (`T005`–`T007`)**: `scripts/edit_code.py` unifies optional `validate` and unskippable closeout `sync` with single-run evidence reuse, final freshness verification, and commit-evidence emission.
- **On-demand freshness (`T008`–`T009`)**: `scripts/read_code_health.py` and `scripts/read_code.py` refresh stale scopes on authoritative reads (`context`, `find`, `analyze`), skip clean repeats, leave `window` reads untouched, and fail closed on error.
- **Commit safeguards (`T010`–`T011`)**: `scripts/git_pre_commit_lint.py` and `scripts/git_post_commit_refresh.py` skip duplicate work only on exact verified evidence match.
- **Bootstrap & isolation (`T012`–`T013`)**: `scripts/bootstrap_session.py` skips healthy snapshots, aggregates scope failures with stderr, and all CodeGraph/discovery subprocesses run under `repo_local_tool_env()`.
- **Live verification & docs (`T014`–`T016`)**: Real-backend integration coverage and single-owner documentation updates, followed by full guarded validation.

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Foundational (`PL-01`) | 8 | 2 | 0 |
| Phase 2: User Story 1 — Non-Blocking Edits (`PL-02`) | 5 | 2 | 1 |
| Phase 3: User Story 2 — Unified Validate & Closeout (`PL-03`) | 11 | 3 | 1 |
| Phase 4: User Story 3 — On-Demand Freshness (`PL-04`) | 8 | 2 | 1 |
| Phase 5: User Story 4 — Commit Safeguards (`PL-05`) | 5 | 2 | 1 |
| Phase 6: User Story 5 — Bootstrap & Isolation (`PL-06`) | 8 | 2 | 1 |
| Phase 7: User Story 6 — Live Verification & Docs (`PL-07`) | 8 | 2 | 2 |
| Phase 8: Final Verification and Handoff | 3 | 1 | 0 |
| **Total** | **56** | **16** | **7** |

## Warnings

- No task is scored 8 or 13 (`PL-03` was decomposed into `T005` [3], `T006` [5], and `T007` [3]); no further breakdown passes are required.
- Live-backend integration tests (`T014`) must run in an isolated temporary git repository and restricted temporary `HOME` directory so repository index state and user-home files are never mutated.
