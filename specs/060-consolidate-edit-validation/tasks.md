# Tasks: Consolidate Edit Validation

**Input**: `spec.md`, `plan.md`, and `spec.json` in `specs/060-consolidate-edit-validation/`
**Prerequisites**: Approved plan slices `PL-01` through `PL-07`
**Terminal boundary**: Deliver decoupled non-blocking edit tracking, unified optional/closeout validation with reusable content/config/dependency/selector evidence, on-demand authoritative-read freshness, evidence-aware git commit fallback safeguards, healthy-skip `bootstrap_session()` with failure aggregation and repo-local `~/.codegraphcontext` isolation, live-backend verification, and consolidated workflow documentation; benchmarking is out of scope for `060` (owned by feature `062`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Task may run in parallel when it changes a different file and has no unsatisfied dependency.
- **[Story]**: Traceability to a specification user story (`US1`–`US6`).

## Phase 1: Foundational — Shared Evidence, Freshness State, and Repo-Local Tool Env (PL-01)

**Purpose**: Establish the shared stdlib-only evidence, freshness-state, and repo-local tool-environment module before modifying hooks, `edit_code.py`, discovery readers, or `bootstrap_session.py`.

**⚠️ CRITICAL**: No user story implementation may begin until this phase is complete.

- [ ] T001 Add failing unit tests for changed-path tracking, evidence digest computation and invalidation (content, config, `uv.lock`, Python minor version, validator identity, selectors), per-backend/per-scope freshness transitions (`current`, `stale`, `unverifiable`), atomic JSON persistence, and `repo_local_tool_env()` zero-`~/.codegraphcontext` path resolution in `tests/unit/test_workflow_evidence.py`
- [ ] T002 Implement stdlib-only `scripts/workflow_evidence.py` with typed models, atomic JSON persistence under `.codegraphcontext/workflow-state/`, evidence digest helpers reusing `scripts/cgc_owner.py` content fingerprinting, freshness state helpers, and `repo_local_tool_env()` (depends on T001)

**Checkpoint**: Shared workflow evidence, freshness-state persistence, and repo-local tool environment helpers are tested and ready for all downstream seams.

---

## Phase 2: User Story 1 - Non-Blocking Intermediate Multi-File Edits (Priority: P1) 🎯 MVP

**Goal**: Decouple `scripts/hook_posttool_edit_validation.py` from technical validation and synchronous index refreshes so coding agents can assemble temporarily inconsistent multi-file edits while accurately tracking changed paths and staleness.

**Independent Test**: Simulate PostToolUse Edit/Write payloads for temporarily inconsistent multi-file Python edits and verify zero `ruff`, `pyright`, docstring, or `hook_refresh_indexes.py` invocations occur while affected paths and discovery scopes are recorded as `stale`.

### Acceptance Criteria

- Saving an intermediate edit records the affected repo-local paths and marks affected discovery backends/scopes `stale` (`FR-001`, `FR-010`).
- Intermediate edits trigger zero automatic technical validator runs (`ruff`, `pyright`, docstring checks) and zero synchronous discovery refreshes (`FR-002`, `FR-003`, `SC-001`).
- Non-repo-local paths remain ignored safely by the hook.

### Tests for User Story 1

- [ ] T003 [P] [US1] Add failing unit tests verifying `run_posttool_request()` tracks changed repo-local paths and marks affected discovery scopes `stale` with zero technical validator or synchronous refresh invocations in `tests/unit/test_hook_posttool_edit_validation.py`

### Implementation for User Story 1

- [ ] T004 [US1] Refactor `scripts/hook_posttool_edit_validation.py` so `run_posttool_request()` records changed paths and marks affected discovery backends/scopes `stale` via `scripts/workflow_evidence.py` without running validators or synchronous refreshes (depends on T002, T003)

**Checkpoint**: Temporarily inconsistent multi-file edits succeed without intermediate validator failures or synchronous refreshes, and affected scopes are marked `stale`.

---

## Phase 3: User Story 2 - Consolidated Optional Validation and Unskippable Closeout (Priority: P1) 🎯 MVP

**Goal**: Make `scripts/edit_code.py` the single owner of optional intermediate validation (`validate`) and mandatory unskippable closeout (`sync`), reusing verified validation evidence on unchanged states, refreshing remaining stale discovery scopes, and emitting commit evidence before handoff.

**Independent Test**: Run `edit_code.py validate` followed by `edit_code.py sync` on an unchanged multi-file change set; verify each mandatory validator runs at most once, closeout rejects any failing check or unverifiable discovery state with no skip bypass, and modifying content, config, `uv.lock`, or test selection invalidates cached evidence.

### Acceptance Criteria

- `edit_code.py validate` and `edit_code.py sync` apply identical pass, failure, and evidence rules across `ruff`, `pyright`, `validate_python_docstrings.py`, targeted `pytest`, and required docs checks (`FR-004`, `FR-005`).
- `edit_code.py sync` provides no `--skip-ruff` or `--skip-pyright` bypass path and rejects 100% of closeout attempts with failing checks or unverifiable discovery state (`FR-006`, `SC-005`).
- Reusable validation evidence matches content hashes, validator config, `uv.lock`, Python minor version, validator identity, and test selectors; any change invalidates affected evidence, and unchanged validated states run each mandatory validator at most once (`FR-007`, `FR-008`, `FR-009`, `SC-002`).
- `edit_code.py sync` verifies/refreshes any remaining stale discovery scopes and persists commit evidence before handoff succeeds (`FR-013`).

### Tests for User Story 2

- [ ] T005 [P] [US2] Add failing unit tests for unified `validate`/`sync` checks, removal of closeout skip flags, evidence reuse and invalidation on content/config/dependency/selector changes, closeout discovery-freshness enforcement, and commit-evidence emission in `tests/unit/test_edit_code_consolidation.py`

### Implementation for User Story 2

- [ ] T006 [US2] Update `scripts/edit_code.py` so `validate` and `sync` share one validation engine enforcing all mandatory checks, remove closeout skip bypasses from `sync`, and reuse/persist validation evidence via `scripts/workflow_evidence.py` (depends on T002, T005)
- [ ] T007 [US2] Wire final discovery-freshness verification/refresh and staged/committed commit-evidence persistence into `scripts/edit_code.py` `sync` so unverifiable discovery state blocks handoff (depends on T006)

**Checkpoint**: `edit_code.py` owns optional validation and unskippable closeout with single-run evidence reuse and verified discovery freshness.

---

## Phase 4: User Story 3 - On-Demand Discovery Freshness on Authoritative Reads (Priority: P1)

**Goal**: Enforce per-backend/per-scope freshness on authoritative index-backed reads (`read_code.py` `context`, `find`, `analyze`) so stale scopes refresh automatically before returning results, clean repeated reads trigger zero duplicate refreshes, direct `window` reads never refresh, and refresh failures fail closed.

**Independent Test**: Mark a scope `stale`, run an authoritative `read_code.py` query and verify exactly one scoped refresh runs and marks the scope `current`; repeat the query on unchanged state and verify zero refreshes; simulate a refresh failure on stale state and verify fail-closed exit with stderr and no authoritative label.

### Acceptance Criteria

- Authoritative reads (`read_code.py` `context`, `find`, `analyze`) refresh affected stale scopes before returning results or fail closed with captured stderr without labeling stale results authoritative (`FR-011`, `SC-004`).
- Repeated authoritative reads against unchanged `current` discovery state trigger zero duplicate refreshes across every supported backend (`FR-012`, `SC-003`).
- Direct disk reads (`read_code.py window`, `read_markdown.py`) never trigger index refreshes (`FR-018`).

### Tests for User Story 3

- [ ] T008 [P] [US3] Add failing unit tests for on-demand stale refresh, zero duplicate refreshes on clean repeated reads, fail-closed error handling with stderr, and no-refresh `window` reads in `tests/unit/test_read_code_freshness.py`

### Implementation for User Story 3

- [ ] T009 [US3] Update `scripts/read_code_health.py`, `scripts/read_code.py`, and `scripts/hook_refresh_indexes.py` to enforce per-backend/per-scope freshness on authoritative reads, persist `current`/`unverifiable` transitions via `scripts/workflow_evidence.py`, and fail closed on refresh errors (depends on T002, T008)

**Checkpoint**: Authoritative reads are fresh-on-demand, idempotent on clean state, and fail closed on refresh failure.

---

## Phase 5: User Story 4 - Evidence-Aware Git Commit Fallback Safeguards (Priority: P2)

**Goal**: Preserve direct Git commit safeguards while skipping duplicate lint and refresh runs when verifiable commit evidence proves the exact staged or committed content and configuration already passed.

**Independent Test**: Run `scripts/git_pre_commit_lint.py` and `scripts/git_post_commit_refresh.py` under three states: (1) direct commit with no evidence, (2) mismatched/stale/corrupt evidence, and (3) exact matching governed evidence; verify safeguards execute in (1) and (2) and skip duplicate work only in (3).

### Acceptance Criteria

- Direct Git commits outside `edit_code.py` execute full pre-commit lint and post-commit refresh safeguards (`FR-014`, `FR-016`, `SC-006`).
- Missing, stale, corrupt, or mismatched commit evidence always triggers the existing safeguard (`FR-016`, `SC-006`).
- Exact verified commit evidence skips duplicate `ruff` and refresh invocations without weakening direct-commit safety (`FR-015`, `SC-006`).

### Tests for User Story 4

- [ ] T010 [P] [US4] Add failing unit tests covering direct commits without evidence, mismatched/corrupt evidence fallback, and exact-match evidence skip for `git_pre_commit_lint.py` and `git_post_commit_refresh.py` in `tests/unit/test_git_commit_safeguards.py`

### Implementation for User Story 4

- [ ] T011 [US4] Update `scripts/git_pre_commit_lint.py` and `scripts/git_post_commit_refresh.py` to verify staged/committed content and config hashes against `scripts/workflow_evidence.py` evidence before skipping or running fallback safeguards (depends on T002, T010)

**Checkpoint**: Direct Git activity retains full safeguards while governed commits avoid duplicate pre-commit lint and post-commit refresh work.

---

## Phase 6: User Story 5 - Healthy-Skip Bootstrap, Failure Aggregation, and Repo-Local CGC Isolation (Priority: P1)

**Goal**: Stop `scripts/bootstrap_session.py` from re-indexing already-healthy snapshots, aggregate multi-scope failures with actual subprocess stderr, and isolate all CodeGraph/discovery entrypoints strictly to repo-local `.codegraphcontext/` paths with zero `~/.codegraphcontext` access.

**Independent Test**: Run `bootstrap_session()` on a healthy snapshot and verify zero `cgc_safe_index.py` invocations; simulate a failing first scope followed by a succeeding later scope and verify `bootstrap_ok=False` with actual subprocess stderr surfaced; run `cgc_safe_index.py`, `read_code.py`, and `bootstrap_session.py` under a restricted/unwritable `HOME` and verify zero `~/.codegraphcontext` access.

### Acceptance Criteria

- `bootstrap_session()` invokes zero `cgc_safe_index.py` runs when `codegraph_health_probe` already reports healthy and no scopes are marked stale (`FR-020`, `SC-008`).
- Multi-scope indexing aggregates failure state across all scopes (later succeeding scopes never overwrite earlier failures) and surfaces actual subprocess stderr in `codegraph_detail` (`FR-021`, `SC-008`).
- `cgc_safe_index.py`, `read_code.py`, `bootstrap_session.py`, and `hook_refresh_indexes.py` isolate config, cache, and database state to repo-local paths with zero `~/.codegraphcontext` access (`FR-022`, `SC-008`).

### Tests for User Story 5

- [ ] T012 [P] [US5] Add failing unit tests for healthy-skip `bootstrap_session()`, multi-scope failure aggregation with stderr surfacing, and restricted-HOME zero-`~/.codegraphcontext` isolation in `tests/unit/test_bootstrap_session_isolation.py`

### Implementation for User Story 5

- [ ] T013 [US5] Update `scripts/bootstrap_session.py`, `scripts/cgc_safe_index.py`, `scripts/cgc_owner.py`, `scripts/read_code.py`, and `scripts/hook_refresh_indexes.py` to gate bootstrap indexing on health+staleness, aggregate failures with subprocess stderr, and apply `repo_local_tool_env()` to all discovery/indexing subprocesses (depends on T002, T012)

**Checkpoint**: `bootstrap_session()` skips healthy snapshots, never masks scope failures, and runs cleanly inside workspace-scoped sandboxes without touching `~/.codegraphcontext`.

---

## Phase 7: User Story 6 - Live-Backend Verification and Workflow Documentation Consolidation (Priority: P2)

**Goal**: Prove the consolidated edit, freshness, closeout, commit-safeguard, and sandbox-isolation workflow against real local backends and align active workflow documentation to one unambiguous owner per responsibility.

**Independent Test**: Run the live-backend integration test suite against a temporary git repo with real local validators/indexers and audit active workflow docs for contradictory ownership or timing rules.

### Acceptance Criteria

- Live-backend integration tests exercise real multi-file temporarily inconsistent edits -> consistency restoration -> authoritative read freshness -> `edit_code.py` validate/sync -> git hook fallback -> restricted-HOME `bootstrap_session()` (`FR-019`, `SC-001`–`SC-006`, `SC-008`).
- Active workflow docs (`AGENTS.md`, `docs/governance/shell-hook-guards.md`) state one unambiguous owner and execution point for edit tracking, optional validation, mandatory closeout validation, on-demand freshness, final freshness, and commit safeguards with zero contradictions (`FR-017`, `FR-018`, `SC-007`).

### Tests & Documentation for User Story 6

- [ ] T014 [P] [US6] Add live-backend integration tests covering end-to-end multi-file edit consistency, single-run validation evidence, on-demand freshness, git hook fallback, and restricted-HOME `bootstrap_session()` isolation in `tests/integration/test_live_edit_validation_consolidation.py` (depends on T004, T007, T009, T011, T013)
- [ ] T015 [P] [US6] Consolidate active workflow ownership documentation in `AGENTS.md` and `docs/governance/shell-hook-guards.md` to eliminate contradictory validation and refresh timing rules (depends on T004, T007, T009, T011, T013)

**Checkpoint**: Live-backend verification passes and active workflow documentation has a single unambiguous owner per seam.

---

## Phase 8: Final Verification and Handoff

**Purpose**: Verify all unit tests, live-backend integration tests, lint, static types, and governance gates pass across the entire `060` change set.

- [ ] T016 Run full targeted unit and live-backend pytest suite via `scripts/pytest_guard.py`, `scripts/ruff_guard.py`, `scripts/pyright_guard.py`, and `scripts/validate_python_docstrings.py` across all touched `scripts/` and `tests/` files (depends on T014, T015)

**Checkpoint**: Feature `060` is verified end-to-end and ready for closeout.
