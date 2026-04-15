---

description: "Task list for Codebase Vector Index"
---

# Tasks: Codebase Vector Index

**Input**: Design documents from `/specs/020-codebase-vector-index/`
**Prerequisites**: plan.md, sketch.md, solutionreview.md, research.md, data-model.md, quickstart.md
**Tests**: Included because the feature spec explicitly requires deterministic query, refresh, staleness, and recovery coverage.
**Organization**: Tasks are grouped by user story so each story can be implemented and validated independently.

## Format: `[ID] [P?] [Story] Description — file:symbol`

- **[P]**: Can run in parallel with no incomplete dependencies.
- **[Story]**: Which user story the task belongs to (`US1`, `US2`, `US3`, `US4`).
- Include exact file paths in descriptions.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the repo-local index package and record the runtime gate status before story work begins.

- [X] T000 [P] Record External Ingress + Runtime Readiness Gate as N/A with rationale in `specs/020-codebase-vector-index/tasks.md` — specs/020-codebase-vector-index/tasks.md:T000
- [X] T001 [P] Create the `src/mcp_codebase/index/` package skeleton and public exports — src/mcp_codebase/index/__init__.py:__all__

**Runtime Gate Rationale**: N/A — the vector index feature is local-only, reads from the repo checkout, and exposes no external ingress or remote runtime readiness surface.

**Checkpoint**: Runtime gate status is explicit and the new package imports cleanly.

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core domain, extraction, storage, and adapter seams that every story depends on.

- [X] T002 Define index domain and config models for `IndexScope`, `CodeSymbol`, `MarkdownSection`, `IndexMetadata`, `QueryResult`, and `IndexConfig` — src/mcp_codebase/index/domain.py:IndexScope
- [X] T003 Implement Python and markdown extractors with exclusion and no-docstring handling — src/mcp_codebase/index/extractors/python.py:extract_python_symbols
- [X] T004 Implement the vector store and service orchestration for build/query/refresh/status — src/mcp_codebase/index/store/chroma.py:ChromaIndexStore
- [X] T005 Wire the vector index service into the MCP server and CLI adapter entrypoint — src/mcp_codebase/server.py:register_vector_index_tools

**Checkpoint**: The foundation supports query, refresh, and status orchestration without inventing new architecture.

## Phase 3: User Story 1 - Semantic Symbol Lookup (Priority: P1) 🎯 MVP

**Goal**: An agent can query the code index for a concept and get ranked symbols with enough provenance to jump directly into `read_code_context`.

**Independent Test**: Index built over `src/`; a semantic code-symbol query returns a ranked symbol with file path, line range, signature, docstring, and empty-result behavior for nonsense queries.

### Tests for User Story 1

- [X] T006 [P] [US1] Add a failing integration test for code-symbol lookup metadata, scope filtering, and empty-result behavior — tests/integration/test_codebase_vector_index.py:test_code_symbol_lookup_returns_metadata
- [X] T007 [P] [US1] Add a unit test for Python symbol extraction, signatures, and no-docstring normalization — tests/unit/test_vector_index_extractors.py:test_extract_python_symbols

### Implementation for User Story 1

- [X] T008 [US1] Implement code-symbol query ranking and result shaping in `VectorIndexService` — src/mcp_codebase/index/service.py:VectorIndexService.query
- [ ] T009 [US1] Preserve `read_code_context`-ready provenance in code-symbol results, including empty-string docstrings and line spans — src/mcp_codebase/index/domain.py:CodeSymbol

**Checkpoint**: Code-symbol lookup is independently usable and returns actionable provenance.

## Phase 4: User Story 2 - Markdown Section Discovery (Priority: P2)

**Goal**: An agent can query markdown topics and get ranked sections with breadcrumb and preview data for direct `read_markdown_section` follow-up.

**Independent Test**: Index built over `specs/` and `.claude/`; a markdown-topic query returns the expected section breadcrumb, file path, and preview.

### Tests for User Story 2

- [ ] T010 [P] [US2] Add a failing integration test for markdown section discovery, breadcrumb rendering, and preview output — tests/integration/test_codebase_vector_index.py:test_markdown_section_lookup_returns_breadcrumb
- [ ] T011 [P] [US2] Add a unit test for markdown extraction, nested headings, and section preview normalization — tests/unit/test_vector_index_extractors.py:test_extract_markdown_sections

### Implementation for User Story 2

- [ ] T012 [US2] Implement markdown query ranking and preview shaping in `VectorIndexService` — src/mcp_codebase/index/service.py:VectorIndexService.query
- [ ] T013 [US2] Preserve `read_markdown_section`-ready breadcrumb metadata and section depth in markdown results — src/mcp_codebase/index/domain.py:MarkdownSection

**Checkpoint**: Markdown discovery is independently usable and returns breadcrumb-rich section results.

## Phase 5: User Story 3 - Incremental Update on Code Change (Priority: P2)

**Goal**: A local file edit or commit updates the index incrementally, without exposing partial writes or stale active snapshots.

**Independent Test**: Modify one file, trigger refresh, and query returns the updated symbol while an interrupted refresh leaves the prior snapshot queryable.

### Tests for User Story 3

- [ ] T014 [P] [US3] Add a failing integration test for watcher-driven incremental refresh and interrupted update recovery — tests/integration/test_codebase_vector_index.py:test_incremental_refresh_preserves_last_good_snapshot
- [ ] T015 [P] [US3] Add a regression test for excluded generated artifacts and post-edit symbol surfacing — tests/integration/test_codebase_vector_index.py:test_refresh_excludes_generated_artifacts

### Implementation for User Story 3

- [ ] T016 [US3] Implement watchdog/post-commit update triggers and incremental content-hash refresh — src/mcp_codebase/index/service.py:VectorIndexService.refresh_changed_files
- [ ] T017 [US3] Implement atomic swap and last-good snapshot preservation on refresh failure — src/mcp_codebase/index/store/chroma.py:ChromaIndexStore

**Checkpoint**: Incremental refresh is safe, non-blocking, and preserves the last good snapshot on failure.

## Phase 6: User Story 4 - Staleness Check (Priority: P3)

**Goal**: An agent can see whether the index is stale relative to HEAD before trusting query results.

**Independent Test**: Build at commit A, move to commit B, and status reports the index as stale with the commit delta.

### Tests for User Story 4

- [ ] T018 [P] [US4] Add a failing staleness-check regression test for recorded commit vs current HEAD — tests/integration/test_codebase_vector_index.py:test_staleness_reports_commit_delta

### Implementation for User Story 4

- [ ] T019 [US4] Implement staleness reporting in the service and MCP/CLI adapters — src/mcp_codebase/index/service.py:VectorIndexService.status
- [ ] T020 [US4] Add quickstart assertions for staleness output and update-trigger guidance — specs/020-codebase-vector-index/quickstart.md

**Checkpoint**: Staleness is observable and actionable from both the service and operator workflow.

## Phase 7: Performance, Scale & Cross-Cutting Concerns

**Purpose**: Finish documentation, validation, performance, scale, and smoke coverage for the final operator workflow.

- [ ] T021 [P] Update docs and smoke validation for the final vector-index local workflow — specs/020-codebase-vector-index/quickstart.md
- [ ] T022 [P] Add a failing benchmark regression for the SC-001/SC-002 timing budgets — tests/integration/test_codebase_vector_index_performance.py:test_index_build_and_refresh_meets_timing_budgets
- [ ] T023 [P] Add a failing load regression for the max-volume edge case — tests/integration/test_codebase_vector_index_performance.py:test_index_handles_max_volume_without_oom

**Checkpoint**: Quickstart and smoke validation match the final local workflow.

## Phase 8: Exclusion Pattern Coverage

**Purpose**: Make the configurable exclusion policy literal and independently testable.

- [ ] T024 Add a failing regression for configured exclude patterns beyond the built-in generated-artifact rules — tests/integration/test_codebase_vector_index_performance.py:test_configurable_excludes_respected
- [ ] T025 Implement configurable exclude-pattern loading and filtering in the extractor/config path — src/mcp_codebase/index/config.py:IndexConfig.exclude_patterns

**Checkpoint**: Configurable exclude patterns are enforced by the index path and proven by regression coverage.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - blocks all user stories
- **User Stories (Phase 3+)**: Depend on Foundational completion
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2)
- **User Story 2 (P2)**: Can start after Foundational (Phase 2)
- **User Story 3 (P2)**: Can start after Foundational (Phase 2)
- **User Story 4 (P3)**: Can start after Foundational (Phase 2)

### Within Each User Story

- Tests (if included) MUST be written and FAIL before implementation.
- Adopted dependencies must include installation, configuration, initialization, integration verification, failure-mode handling, and documentation updates.
- Models before services.
- Services before adapters.
- Core implementation before integration.
- Story complete before moving to next priority.

### Parallel Opportunities

- Setup tasks marked [P] can run in parallel.
- Tests marked [P] can run in parallel with each other when they do not share incomplete prerequisites.
- Different user stories can be worked on in parallel once the foundation is complete.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Stop and validate User Story 1 independently

### Incremental Delivery

1. Complete Setup + Foundational
2. Add User Story 1 and validate it
3. Add User Story 2 and validate it
4. Add User Story 3 and validate it
5. Add User Story 4 and validate it

### Parallel Team Strategy

1. Team completes Setup + Foundational together
2. Once the foundation is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
   - Developer D: User Story 4
3. Stories complete and integrate independently
