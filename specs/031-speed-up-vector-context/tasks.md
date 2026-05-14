# Tasks: speed up vector context

**Input**: Design documents from `/specs/031-speed-up-vector-context/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)
**Skills**: None required beyond the standard repo workflow

**Tests**: This feature changes a read-path contract and must carry targeted unit and integration coverage with the implementation tasks.

**Organization**: Tasks are grouped by user story so each story can be implemented and verified independently once the shared routing helpers exist.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no direct dependency)
- **[Story]**: Which user story this task belongs to (for example, `US1`, `US2`, `US3`)
- Every task description includes an explicit file path and ends with a backticked primary seam reference for HUD scaffolding.

## Path Conventions

- Repo-root Python scripts live under `scripts/`
- Unit tests live under `tests/unit/`
- Integration and performance checks live under `tests/integration/`
- Feature artifacts live under `specs/031-speed-up-vector-context/`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture the benchmark corpus and shared validation seams before routing changes begin.

- [X] T000 Define the accepted scoped, broad, and markdown benchmark corpus in `specs/031-speed-up-vector-context/tasks.md` and `specs/031-speed-up-vector-context/plan.md` — `specs/031-speed-up-vector-context/plan.md:Research Baseline`

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the query-classification and trust-state helpers that every story depends on.

- [X] T001 [P] Introduce early query-scope classification helpers for scoped versus broad `read_code context` requests in `scripts/read_code.py` — `scripts/read_code.py:read_code_context`
- [X] T002 [P] Introduce request-scoped trust evaluation and fast-path freshness helpers in `scripts/read_code_health.py` — `scripts/read_code_health.py:_refresh_indexes_for_read`
- [X] T003 Wire the new query-scope and trust helpers into the existing preflight contract in `scripts/read_code.py` and `scripts/read_code_health.py` — `scripts/read_code.py:_resolve_pattern_anchor`

## Phase 3: User Story 1 - Fast Scoped Context Reads (Priority: P1) 🎯 MVP

**Goal**: Return the same seam for exact path, symbol, and file-local queries without paying broad freshness and markdown costs by default.

**Independent Test**: Run the scoped benchmark corpus against known-file and exact-symbol reads, verify the selected seam is unchanged, and confirm the scoped path skips irrelevant markdown work and repeated heavyweight freshness proofs.

### Tests for User Story 1

- [X] T004 [P] [US1] Add scoped fast-path regression coverage for exact-symbol and file-local context reads in `tests/unit/test_read_code_shortlist.py` and `tests/unit/test_read_code_index_refresh.py` — `tests/unit/test_read_code_shortlist.py:_query_semantic_anchor_candidate`

### Implementation for User Story 1

- [X] T005 [US1] Restrict scoped code queries so irrelevant markdown retrieval is skipped in `scripts/read_code.py` — `scripts/read_code.py:_query_semantic_anchor_candidate`
- [X] T006 [US1] Apply scope-local or session-trusted freshness shortcuts for scoped reads in `scripts/read_code_health.py` — `scripts/read_code_health.py:vector_refresh_by_state`
- [X] T007 [US1] Update `read_code context` output and inline behavior to preserve current seam selection while using the scoped fast path in `scripts/read_code.py` — `scripts/read_code.py:read_code_context`

## Phase 4: User Story 2 - Efficient Broad Discovery (Priority: P2)

**Goal**: Preserve markdown-aware broad discovery while only escalating to heavyweight trust and fallback work when broad results are weak, empty, stale, or ambiguous.

**Independent Test**: Run broad natural-language queries that rely on code, markdown, and mixed discovery; verify relevant seams still surface and the slower path is reserved for ambiguous or stale outcomes.

### Tests for User Story 2

- [X] T008 [P] [US2] Add broad discovery and mixed code-plus-markdown coverage in `tests/unit/test_read_code_shortlist.py` and `tests/integration/test_codebase_vector_index.py` — `tests/integration/test_codebase_vector_index.py:test_code_symbol_lookup_returns_metadata`

### Implementation for User Story 2

- [X] T009 [US2] Rework broad-query routing so healthy-session trust can satisfy normal discovery reads in `scripts/read_code.py` and `scripts/read_code_health.py` — `scripts/read_code.py:_resolve_pattern_anchor`
- [X] T010 [US2] Make broad fallback and recovery conditional on empty, weak, stale, or conflicting outcomes in `scripts/read_code.py` — `scripts/read_code.py:_resolve_pattern_anchor`

## Phase 5: User Story 3 - Clear Freshness Escalation (Priority: P3)

**Goal**: Make trust reuse, invalidation, and escalation behavior predictable enough that maintainers can understand when a fast path was used and when recovery logic was necessary.

**Independent Test**: Exercise healthy, stale, and ambiguous trust states, confirm invalidation after relevant edits, and verify recovery-path behavior remains observable and safe.

### Tests for User Story 3

- [X] T011 [P] [US3] Add stale-trust, invalidation, and escalation observability coverage in `tests/unit/test_read_code_index_refresh.py` and `tests/integration/test_codebase_vector_index_performance.py` — `tests/unit/test_read_code_index_refresh.py:_refresh_indexes_for_read`

### Implementation for User Story 3

- [X] T012 [US3] Implement explicit trust invalidation and escalation-state signaling in `scripts/read_code_health.py` and `scripts/read_code.py` — `scripts/read_code_health.py:vector_index_probe`
- [X] T013 [P] [US3] Update read-code help text or command documentation to describe the new broad-versus-scoped trust behavior in `scripts/read_code.py` and `specs/031-speed-up-vector-context/plan.md` — `scripts/read_code.py:module:docstring`

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Lock the benchmark artifact and ensure the settled graph is ready for estimate, HUD, and implement phases.

- [ ] T014 Capture the post-change benchmark evidence and accepted validation commands in `specs/031-speed-up-vector-context/tasks.md` and `tests/integration/test_codebase_vector_index_performance.py` — `tests/integration/test_codebase_vector_index_performance.py:module`
- [ ] T015 De-prioritize test-file candidates in regular context discovery unless the request explicitly targets tests in `scripts/read_code.py` and `tests/unit/test_read_code_shortlist.py` — `scripts/read_code.py:_vector_anchor_rank`

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1: no dependencies
- Phase 2: depends on Phase 1
- Phase 3: depends on Phase 2
- Phase 4: depends on Phase 2 and can start after the shared routing helpers land
- Phase 5: depends on Phases 3 and 4 because escalation behavior builds on both scoped and broad trust paths
- Phase 6: depends on Phases 3 through 5

### User Story Dependencies

- **US1 (P1)**: starts after the foundational classification and trust helpers exist
- **US2 (P2)**: starts after the same foundational helpers exist; it should build on the scoped routing contract rather than reintroduce a separate path
- **US3 (P3)**: starts after US1 and US2 because invalidation and observability are only meaningful once both fast paths exist

### Within Each User Story

- Write the tests for the story before or alongside the first implementation task that changes the behavior under test.
- Complete the routing/helper edits before touching user-facing output or docs for that story.
- Keep benchmark and observability updates after the functional trust-routing changes so the measurements reflect the final behavior.

### Parallel Opportunities

- T004 can run in parallel with T008 once the foundational helpers are defined because the scoped and broad test coverage touch different assertions.
- T005 and T006 should stay sequential because the scoped retrieval gate depends on the trust shortcut contract.
- T008 and T011 can run in parallel after Phase 2 because they cover different outcome classes and test files.
- T013 and T014 can run in parallel at the end once the implementation and benchmark outputs are stable.
- T014 and T015 can run in parallel at the end because benchmark capture and test-candidate ranking polish touch different seams.

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Finish Phase 2 to establish classification and scoped trust helpers.
2. Deliver US1 to remove the biggest measured latency waste: unnecessary broad freshness proof and markdown search for scoped code queries.
3. Verify the scoped benchmark corpus before moving to broader discovery changes.

### Incremental Delivery

1. Ship US1 for the immediate latency win on exact path, exact symbol, and file-local reads.
2. Extend the routing to broad discovery in US2 without regressing markdown usefulness.
3. Finish with US3 so trust invalidation and escalation become explicit and maintainable.

### Parallel Team Strategy

1. One engineer can own `scripts/read_code.py` routing while another prepares the unit and integration test updates after the foundational helper contract is agreed.
2. Once US1 is stable, a second engineer can take the broad-discovery and benchmark work while the first engineer finalizes escalation signaling and documentation.

## Notes

- The task graph follows the approved design-slice ordering from `plan.md`: `PL-01` then `PL-02` then `PL-03`.
- Every non-human task is anchored to an explicit file path and primary seam so HUD scaffolding can attach concrete implementation context.
- No task is intentionally estimated at `8` or `13`; the later estimate phase should either confirm medium-sized tasks or force a breakdown before finalize.

### Accepted Benchmark Corpus

- Scoped corpus: exact-path, exact-symbol, and file-local reads for Python sources, including the existing `_vector_anchor_rank` benchmark shape and equivalent scoped lookups that should stay on the fast path.
- Broad corpus: code-plus-markdown discovery questions that require mixed semantic reading, including natural-language “how does this work?” queries.
- Markdown corpus: markdown-first reads for specs, HUDs, quickstarts, and other task artifacts that explain intent better than code alone.
- Escalation corpus: healthy, stale, and ambiguous trust states that validate when recovery or heavier freshness proof is required.

### Validation Expectations

- Preserve the existing measured timings already captured in `plan.md`; do not re-estimate or replace them in this task.
- Keep the accepted benchmark corpus stable so later implementation tasks can use it as the regression baseline.
- Run `uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file specs/031-speed-up-vector-context/tasks.md --json` after any edit to confirm the task file format remains valid.

## Plan Design Slice Index

Use these plan slices as the authoritative tasking inputs:

- `PL-01` — Scoped Trust Fast Path
- `PL-02` — Broad Discovery and Conditional Escalation
- `PL-03` — Benchmark and Regression Coverage
