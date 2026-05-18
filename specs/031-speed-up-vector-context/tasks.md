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

**Purpose**: Lock the benchmark artifact, prove the persistent rerank path is actually consumed by normal `context` queries, close out the failed standalone-CLI persistence branch honestly, and move the accepted agent path onto the only transport now proven to persist across sandboxed agent turns: a project-local MCP stdio server.

- [X] T014 Capture the post-change benchmark evidence and accepted validation commands in `specs/031-speed-up-vector-context/tasks.md` and `tests/integration/test_codebase_vector_index_performance.py` — `tests/integration/test_codebase_vector_index_performance.py:module`
  - Evidence corpus: scoped exact-path / exact-symbol reads, broad code-plus-markdown discovery, markdown-first reads, and stale/escalation cases remain covered by the existing performance and regression suite.
  - Validation commands:
    - `uv run --no-sync python scripts/pytest_guard.py run -- tests/unit/test_read_code_index_refresh.py tests/unit/test_read_code_shortlist.py -k escalation`
    - `uv run --no-sync python scripts/pytest_guard.py run -- tests/integration/test_codebase_vector_index_performance.py -k 'invalidation or timing'`
    - `uv run python scripts/ruff_guard.py scripts/read_code_health.py scripts/read_code.py tests/unit/test_read_code_index_refresh.py tests/unit/test_read_code_shortlist.py tests/integration/test_codebase_vector_index_performance.py`
- [X] T015 De-prioritize test-file candidates in regular context discovery unless the request explicitly targets tests in `scripts/read_code.py` and `tests/unit/test_read_code_shortlist.py` — `scripts/read_code.py:_vector_anchor_rank`
- [X] T016 [P] Add reranker-daemon transport coverage for shortlist-sized scoring and shared-file fallback in `tests/unit/test_read_code_reranker_daemon.py` and `tests/unit/test_read_code_shortlist.py` — `scripts/read_code.py:_rerank_semantic_candidates`
- [X] T017 Cap rerank requests to the shortlist-sized candidate window and route daemon scoring through a transport-neutral client in `scripts/read_code.py` — `scripts/read_code.py:_rerank_semantic_candidates`
- [X] T018 Keep Unix-socket and shared-file transports behind the same daemon scoring contract in `scripts/read_code.py`, `src/mcp_codebase/index/reranker_runtime.py`, and `src/mcp_codebase/index/reranker_daemon.py` — `src/mcp_codebase/index/reranker_daemon.py:build_app`
- [X] T019 [P] Add live-backend verification that normal `read_code context` queries record `rerank_source: daemon`, avoid per-search reranker startup on repeated first-search ranking requests, and fall back cleanly when transport is unavailable in `tests/integration/test_codebase_vector_index_performance.py` and `tests/unit/test_read_code_reranker_daemon.py` — `tests/integration/test_codebase_vector_index_performance.py:module`
- [X] T020 Capture daemon status, fallback, and live verification commands for the reranker service in `specs/031-speed-up-vector-context/tasks.md` and `specs/031-speed-up-vector-context/plan.md` — `specs/031-speed-up-vector-context/plan.md:Design Slices`
  - Status command: `uv run --no-sync python scripts/read_code.py daemon status`
  - Live proof test: `SPECKIT_RUN_LIVE_RERANKER_DAEMON_TESTS=1 uv run --no-sync python scripts/pytest_guard.py run -- tests/integration/test_codebase_vector_index_performance.py::test_live_read_code_context_records_daemon_rerank_source_without_restarting_daemon`
  - Fresh-session daemon proof commands:
    - `READ_CODE_SESSION_ID=daemon-live-check-1 uv run --no-sync python scripts/read_code.py context "_vector_trust_decision" --path scripts/read_code_health.py`
    - `READ_CODE_SESSION_ID=daemon-live-check-2 uv run --no-sync python scripts/read_code.py context "_vector_trust_decision" --path scripts/read_code_health.py`
  - Verified outcome: both fresh-session live queries recorded `rerank_source: daemon`, and the live integration test proved the daemon `started_at` value stayed constant across separate first-search requests.
- [ ] T021 [P] Add failing contract and live-backend coverage for daemon-owned semantic retrieval startup reuse in `tests/unit/test_read_code_reranker_daemon.py`, `tests/unit/test_read_code_shortlist.py`, and `tests/integration/test_codebase_vector_index_performance.py` — `tests/integration/test_codebase_vector_index_performance.py:module`
  - Prove a fresh-session first-search query records daemon-backed semantic retrieval when transport is healthy.
  - Prove a repeated fresh-session first-search query avoids per-request semantic query startup and keeps the same daemon process identity.
  - Preserve clean local fallback when daemon query transport is unavailable or times out.
- [ ] T022 Route semantic query requests through a transport-neutral daemon client contract in `scripts/read_code.py` and `src/mcp_codebase/index/reranker_runtime.py` — `scripts/read_code.py:_vector_query_candidates`
  - Keep the synchronous client path bounded to `health -> query -> fallback`.
  - Reuse the existing UDS-or-file-RPC transport boundary instead of introducing a second daemon or a second client stack.
- [ ] T023 Move warm semantic query service ownership and request handling into the existing daemon in `src/mcp_codebase/index/reranker_daemon.py`, `src/mcp_codebase/index/service.py`, and `src/mcp_codebase/index/store/chroma.py` — `src/mcp_codebase/index/reranker_daemon.py:build_app`
  - Keep reranker and semantic retrieval in the same long-lived process.
  - Ensure daemon-side startup owns the remaining vector query initialization that still happens per first-search request today.
- [ ] T024 Record daemon-vs-local semantic query sourcing in search metadata and preserve scratchpad behavior in `scripts/read_code.py` and `tests/unit/test_read_code_shortlist.py` — `scripts/read_code.py:_append_search_metadata_event`
  - Add bounded metadata fields that distinguish daemon-backed semantic retrieval from local fallback.
  - Keep scratchpad rereads and first-read `--inline-body` gating behavior unchanged.
- [ ] T025 Capture status, live-proof, and fallback verification commands for daemon-backed semantic retrieval in `specs/031-speed-up-vector-context/plan.md` and `specs/031-speed-up-vector-context/tasks.md` — `specs/031-speed-up-vector-context/plan.md:Plan Completion Summary`
  - Record the settled live verification commands and the acceptance outcome for daemon-owned first-search retrieval.
  - Include at least one proof that repeated fresh-session first-search reads avoid per-request semantic query startup when the daemon is healthy.
- [X] T026 [P] Add failing contract and live-backend persistence coverage for the project-local MCP stdio server in `tests/unit/test_persistence_probe_server.py` and `tests/integration/test_codebase_vector_index_performance.py` — `src/mcp_codebase/persistence_probe_server.py:get_process_identity`
  - Prove the MCP server keeps the same `pid` and `started_at` across separate agent turns.
  - Prove the persistence check is the gate before migrating `read_code` warm backend ownership onto the MCP path.
- [X] T027 Build a project-local MCP stdio backend server that owns warm semantic query and rerank operations in `src/mcp_codebase/` and wire it in `.codex/config.toml` — `src/mcp_codebase/persistence_probe_server.py:get_process_identity`
  - Keep the persistence-probe server contract as the base shape and extend it into the real backend server instead of introducing another socket daemon or another repo-local worker.
  - Expose bounded backend operations that can serve semantic query startup reuse and rerank startup reuse from one persistent process.
- [X] T028 Route `read_code` backend requests through the MCP-persistent server with bounded fallback in `scripts/read_code.py` and `tests/unit/test_read_code_reranker_daemon.py` — `scripts/read_code.py:_vector_query_candidates`
  - Keep the synchronous client path minimal: `server call -> result -> fallback`.
  - Remove dependency on the per-invocation stdio worker for the active `read_code` path once the MCP server contract is live.
- [ ] T029 [P] Add live-backend verification that fresh `uv run ... scripts/read_code.py context ...` invocations reuse the same MCP-owned warm backend for both semantic query and rerank in `tests/integration/test_codebase_vector_index_performance.py` and `scripts/probe_read_code_worker_persistence.py` — `tests/integration/test_codebase_vector_index_performance.py:module`
  - Prove repeated fresh CLI invocations reuse one backend `pid` and avoid per-search semantic-query and reranker startup.
  - Preserve the existing scratchpad reread fast path and clean heuristic/local fallback when the MCP backend is unavailable.
- [X] T030 Capture the accepted MCP persistence proof, verification commands, and operator guidance in `docs/governance/read-code-stdio-worker.md`, `specs/031-speed-up-vector-context/plan.md`, and `specs/031-speed-up-vector-context/tasks.md` — `docs/governance/read-code-stdio-worker.md`
  - Record the exact persistence proof commands and the backend identity values used to verify the platform-owned server survives across turns.
  - Retire obsolete daemon/file-RPC wording where it conflicts with the accepted MCP-persistent path.
- [X] T031 [P] Add failing contract and live-backend coverage for an MCP-native `read_code` agent surface in `tests/unit/test_project_backend_server.py` and `tests/integration/test_codebase_vector_index_performance.py` — `src/mcp_codebase/project_backend_server.py:module`
  - Prove the persistent project-local MCP server exposes bounded `context`, `find`, `analyze`, and `window` operations suitable for direct agent use.
  - Prove repeated agent-turn calls keep the same backend `pid` and `started_at` while preserving the accepted scoped and broad benchmark corpus behavior.
  - Preserve clean bounded failures for unsupported arguments or unavailable backend state.
- [X] T032 Route the reusable `read_code` orchestration into importable helpers and expose MCP-native `context`, `find`, `analyze`, and `window` tools in `scripts/read_code.py` and `src/mcp_codebase/project_backend_server.py` — `scripts/read_code.py:read_code_context`
  - Keep `scripts/read_code.py` as the CLI compatibility layer, not the primary warm path for agent reads.
  - Reuse the existing classification, scratchpad/history, metadata, and rendering logic instead of re-implementing a second read stack inside the MCP server.
- [X] T033 Migrate live agent-path verification onto the MCP-native read surface in `tests/integration/test_codebase_vector_index_performance.py` and `src/mcp_codebase/persistence_probe_server.py` — `tests/integration/test_codebase_vector_index_performance.py:module`
  - Prove direct MCP `context`/`find`/`analyze`/`window` calls return parity-equivalent results without spawning fresh `uv run ... scripts/read_code.py ...` subprocesses.
  - Prove the same persistent backend serves both semantic query and rerank work across separate agent turns in the sandbox.
- [X] T034 Capture the accepted MCP-native agent-read proof, verification commands, and operator guidance in `docs/governance/read-code-stdio-worker.md`, `specs/031-speed-up-vector-context/plan.md`, and `specs/031-speed-up-vector-context/tasks.md` — `docs/governance/read-code-stdio-worker.md`
  - Record `T029` as the failed standalone-CLI persistence branch and `T031` through `T033` as the accepted sandboxed-agent path.
  - Retire obsolete “CLI subprocesses can be warm” wording and document the direct-MCP usage contract for agents.

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
- T016 should land before or alongside T017 so the shortlist-sized rerank boundary has regression coverage before the transport contract changes.
- T017 and T018 should stay sequential because the shortlist-sized rerank boundary must be stable before the shared transport contract is finalized.
- T019 and T020 can run in parallel at the end once the daemon path and metadata outputs are stable.
- T029 and T030 stay paired as the standalone-CLI persistence proof and its documentation closeout; if that proof fails, use it as the gate before starting the MCP-native agent branch.
- T031 and T032 should stay sequential because the MCP-native read contract needs to exist before the shared `read_code` orchestration can be moved behind it.
- T033 and T034 can run in parallel at the end once the MCP-native read surface is stable.
- T021 should land before or alongside T022 so the daemon semantic-retrieval contract is pinned down before the client routing changes.
- T022 and T023 should stay sequential because the daemon client contract needs to stabilize before the daemon-side semantic query handler is finalized.
- T024 and T025 can run in parallel at the end once daemon-backed semantic retrieval and metadata fields are stable.
- T026 should land before T027 because the MCP persistence proof is the architectural gate for the migration.
- T027 and T028 should stay sequential because the server contract needs to stabilize before `read_code` switches its active backend path.
- T029 and T030 can run in parallel at the end once MCP-backed query and rerank reuse are stable.

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

- The task graph follows the approved design-slice ordering from `plan.md`: `PL-01` then `PL-02` then `PL-03`, followed by the transport/startup extensions. The older daemon-worker tasks remain for audit history, while `T026` through `T030` capture the standalone-CLI MCP branch that proved the persistence boundary and `T031` through `T034` capture the accepted MCP-native agent route.
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
- `PL-04` — Persistent Reranker Transport Boundary
- `PL-05` — Daemon Lifecycle, Observability, and Live Proof
- `PL-06` — Daemon-Backed Semantic Retrieval
- `PL-07` — Daemon-Owned Remaining First-Search Startup
- `PL-08` — MCP-Native Agent Read Surface
