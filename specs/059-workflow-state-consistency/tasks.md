# Tasks: Workflow State Consistency

**Input**: `spec.md`, `plan.md`, and `spec.json` in `specs/059-workflow-state-consistency/`
**Prerequisites**: Approved plan slices PL-01 through PL-05
**Terminal boundary**: Deliver deterministic vector edit fingerprinting, non-destructive Plan/Solution scaffolding, canonical feature-ID normalization, estimate-to-ledger contract alignment, live-backend verification, and migration/compatibility documentation; leave persistent warmed-reranker ownership to feature `061-persistent-repo-research-backends`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Task may run in parallel when it changes a different file.
- **[Story]**: Traceability to a specification user story (`US1`–`US5`).

## Phase 1: Setup & Contract Baselines

**Purpose**: Establish shared canonical feature-ID normalization and baseline regression harnesses before changing runtime state paths.

- [X] T001 Add canonical `normalize_feature_id()` helper supporting `NNN` and `NNN-slug` with malformed-ID rejection in `scripts/pipeline_ledger.py`

**Checkpoint**: Shared feature-ID normalizer is in place for ledger and driver callers.

---

## Phase 2: User Story 1 - Deterministic Vector Edit Fingerprinting (Priority: P1) 🎯 MVP

**Goal**: Vector edit fingerprints remain identical across edits, refreshes, git commits, and reads while deterministically detecting real post-refresh modifications.

**Independent Test**: Edit a tracked file, run index refresh, commit the unchanged file, and run freshness checks; confirm zero false-positive staleness after refresh or commit, and deterministic staleness detection after a subsequent real edit.

### Acceptance Criteria

- Identical indexed content produces the same vector edit fingerprint before and after a git commit (`FR-001`, `FR-002`).
- Genuine post-refresh edits to indexed files trigger bounded, deterministic staleness detection (`FR-003`).
- Ignored runtime directories (`.codegraphcontext/`, `.speckit/`, `.uv-cache/`, `logs/`, `shadow-runs/`) do not cause fingerprint drift.

### Tests for User Story 1

- [X] T002 [P] [US1] Add failing unit tests for deterministic content-based vector edit fingerprinting across edit, refresh, commit, and real post-refresh modification in `tests/unit/test_read_code_health.py`

### Implementation for User Story 1

- [X] T003 [US1] Replace porcelain-only vector edit signature with a deterministic indexed-content fingerprint across `scripts/read_code_health.py`, `src/mcp_codebase/health.py`, and `scripts/hook_refresh_indexes.py`

**Checkpoint**: Vector edit fingerprinting is deterministic across edits, refreshes, commits, and reads.

---

## Phase 3: User Story 2 - Non-Destructive Plan Apply-Strategy and Solution Task Creation (Priority: P1)

**Goal**: `apply_strategy()` and `prepare_tasking()` preserve already-populated `plan.md` and `tasks.md` content while continuing to scaffold missing artifacts from custom templates.

**Independent Test**: Populate `plan.md` and `tasks.md` with authored sections, run `speckit_plan_step.py apply-strategy` and `speckit_tasking_step.py prepare-tasking`, and verify populated content is preserved intact while missing files still scaffold from `.specify/templates/`.

### Acceptance Criteria

- `apply_strategy()` preserves populated sections in `plan.md` and never replaces authored content with blank template stubs (`FR-004`, `FR-006`).
- `prepare_tasking()` preserves populated `tasks.md` files and only scaffolds from `.specify/templates/tasks-template.md` when missing or empty (`FR-005`, `FR-006`).
- Custom templates and custom workflow steps remain intact.

### Tests for User Story 2

- [X] T004 [P] [US2] Add failing unit tests verifying `apply_strategy()` preserves populated `plan.md` sections and `prepare_tasking()` preserves populated `tasks.md` in `tests/unit/test_plan_step.py` and `tests/unit/test_speckit_solution_step.py`

### Implementation for User Story 2

- [X] T005 [US2] Update `_write_selected_scaffold()` and `apply_strategy()` to merge and preserve populated sections instead of overwriting with blank stubs in `scripts/speckit_plan_step.py`
- [X] T006 [P] [US2] Guard `prepare_tasking()` to preserve existing populated `tasks.md` files while still scaffolding missing or empty files from custom templates in `scripts/speckit_solution_step.py`

**Checkpoint**: Plan apply-strategy and Solution task creation are non-destructive and preserve custom templates.

---

## Phase 4: User Story 3 - Consistent Feature ID Normalization Across Driver and Ledger (Priority: P1)

**Goal**: `pipeline_ledger.py`, `pipeline_driver.py`, and `pipeline_driver_state.py` accept both `NNN` and `NNN-slug` feature IDs, normalize to canonical `NNN` at the ledger boundary, and preserve append-only audit integrity.

**Independent Test**: Run `pipeline_driver.py` and `pipeline_ledger.py` (`append`, `assert-phase-complete`, `validate`) with both `059` and `059-workflow-state-consistency` against an isolated ledger and verify identical canonical resolution, malformed-ID rejection, and zero mutation of historical records.

### Acceptance Criteria

- `pipeline_ledger.py` (`append`, `assert-phase-complete`, `validate`) accepts both `NNN` and `NNN-slug` and writes canonical `NNN` (`FR-007`, `FR-009`).
- `pipeline_driver.py` (`append_requested_pipeline_event`, `append_pipeline_success_event`) and `pipeline_driver_state.py` (`resolve_phase_state`) normalize both forms consistently (`FR-007`).
- Malformed feature IDs fail deterministically without mutating `.speckit/pipeline-ledger.jsonl` (`FR-008`, `FR-009`).

### Tests for User Story 3

- [X] T007 [P] [US3] Add failing unit tests for `NNN` and `NNN-slug` normalization, malformed-ID rejection, and historical ledger compatibility in `tests/unit/test_pipeline_ledger_sequence.py` and `tests/unit/test_pipeline_driver.py`

### Implementation for User Story 3

- [X] T008 [US3] Wire `normalize_feature_id()` into `pipeline_ledger.py`, `scripts/pipeline_driver.py`, and `scripts/pipeline_driver_state.py` without rewriting historical ledger entries

**Checkpoint**: Both `NNN` and `NNN-slug` feature IDs resolve and append identically across driver and ledger commands.

---

## Phase 5: User Story 4 - Aligned Estimate Command and Ledger Transition Contract (Priority: P2)

**Goal**: `.claude/commands/speckit.estimate.md`, `command-manifest.yaml`, `.specify/command-manifest.yaml`, `scripts/pipeline_ledger.py`, and `scripts/pipeline_driver_state.py` agree on exact estimate/tasking prerequisites, emitted events, required fields, and follow-on transitions.

**Independent Test**: Run `pipeline_ledger.py validate-manifest` and transition contract tests covering `plan_approved` → `estimation_completed` / `tasking_completed` → `analysis_completed` and verify zero contradictions across docs, manifests, and ledger rules.

### Acceptance Criteria

- Canonical `tasking_completed` (`task_count`, `story_count`) and compatibility `estimation_completed` transitions, prerequisites, and phase mappings match across all four sources of truth (`FR-010`).
- `pipeline_ledger.py validate` and `validate-manifest` pass with zero discrepancies.

### Tests for User Story 4

- [X] T009 [P] [US4] Add contract tests asserting alignment between `.claude/commands/speckit.estimate.md`, `command-manifest.yaml`, `.specify/command-manifest.yaml`, `scripts/pipeline_ledger.py`, and `scripts/pipeline_driver_state.py` in `tests/unit/test_pipeline_ledger_sequence.py`

### Implementation for User Story 4

- [X] T010 [US4] Reconcile estimate/tasking event declarations, required fields, and transition rules across `.claude/commands/speckit.estimate.md`, `command-manifest.yaml`, `.specify/command-manifest.yaml`, `scripts/pipeline_ledger.py`, and `scripts/pipeline_driver_state.py`

**Checkpoint**: Estimate command docs, manifests, driver state, and ledger transitions are fully aligned.

---

## Phase 6: User Story 5 - Live-Backend Verification and Migration Documentation (Priority: P2)

**Goal**: Real local vector index refresh and `read_code.py` paths are verified against live backends (separate from mocked tests), and migration/compatibility behavior plus the feature `061` boundary are documented.

**Independent Test**: Run the live-backend integration test suite for edit → refresh → read → commit → verify flows and inspect the governance docs for migration rules and feature `061` boundary clarity.

### Acceptance Criteria

- Live-backend verification tests exercise real vector index refresh, fingerprint stability across commit boundaries, and real `read_code.py` queries without stubbing backend persistence (`FR-011`).
- Migration/compatibility documentation covers `NNN`/`NNN-slug` normalization, append-only ledger compatibility, non-destructive scaffolding, estimate transitions, and the explicit boundary with feature `061` (`FR-012`, `FR-013`).

### Tests & Documentation for User Story 5

- [X] T011 [US5] Add live-backend verification tests for real vector index refresh, commit-invariant fingerprinting, and `read_code.py` paths in `tests/integration/test_live_vector_fingerprint_and_read_code.py`
- [X] T012 [P] [US5] Document migration, backward compatibility, and the feature `061` persistent warmed-reranker scope boundary in `docs/governance/pipeline-driver-readme.md` and `docs/governance/speckit-end-to-end.md`

**Checkpoint**: Live-backend verification passes and operator migration/compatibility documentation is complete.

---

## Phase 7: Verification and Handoff

**Purpose**: Run full targeted test, lint, ledger, and manifest verification across all touched seams.

- [X] T013 Run targeted unit, contract, and live-backend test suites plus ruff and ledger/manifest validation via `scripts/pytest_guard.py`, `scripts/ruff_guard.py`, and `scripts/pipeline_ledger.py`

## Dependencies & Execution Order

- T001 precedes T007–T008 (shared feature-ID normalizer).
- T002 precedes T003 (US1 TDD sequence); T004 precedes T005–T006 (US2 TDD sequence); T007 precedes T008 (US3 TDD sequence); T009 precedes T010 (US4 TDD sequence).
- T011 runs after T003 (verifies live vector fingerprinting and `read_code.py`).
- T012 runs after T005, T006, T008, and T010 so documentation matches final behavior.
- T013 runs after all implementation, live-verification, and documentation tasks complete.

## Parallel Opportunities

- US1 (`T002`/`T003`), US2 (`T004`–`T006`), and US3 (`T007`/`T008`) touch disjoint seams and can run in parallel once `T001` is complete.
- `T005` (`speckit_plan_step.py`) and `T006` (`speckit_solution_step.py`) touch separate files and can run in parallel.

## Plan Design Slice Index

- Slice PL-01 - Deterministic vector edit fingerprinting across reads, refreshes, commits, and verification: T002, T003
- Slice PL-02 - Non-destructive Plan apply-strategy and Solution task creation: T004, T005, T006
- Slice PL-03 - Consistent NNN and NNN-slug feature ID normalization in pipeline ledger and driver: T001, T007, T008
- Slice PL-04 - Align estimate command, manifests, and ledger transition contract: T009, T010
- Slice PL-05 - Live-backend verification and migration/compatibility documentation: T011, T012, T013
