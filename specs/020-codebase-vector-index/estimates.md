# Effort Estimate: Codebase Vector Index

**Date**: 2026-04-14 | **Total Points**: 77 | **T-shirt Size**: Large  
**Estimated by**: AI (speckit.estimate) — calibrate against actuals after implementation

---

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T000 | 1 | Record the runtime gate as N/A in the task file | Pure documentation of an already-known no-ingress condition. |
| T001 | 1 | Create the `src/mcp_codebase/index/` package skeleton and exports | Simple package scaffolding with no business logic. |
| T002 | 3 | Define index domain and config models | Multiple typed models and config entry points shared across the whole feature. |
| T003 | 3 | Implement Python and markdown extractors | Two parser implementations plus exclusion and no-docstring handling. |
| T004 | 5 | Implement the vector store and service orchestration | Crosses extraction, persistence, query, refresh, and failure handling boundaries. |
| T005 | 3 | Wire the vector index into the MCP server and CLI adapter | Adds a new adapter surface across server and command entry point. |
| T006 | 3 | Add the code-symbol lookup integration test | Requires end-to-end fixture setup and metadata assertions against the new query path. |
| T007 | 2 | Add the Python symbol extraction unit test | Straightforward extractor regression with a clear expected output shape. |
| T008 | 3 | Implement code-symbol query ranking and result shaping | Core query behavior plus scope filtering and ranked metadata composition. |
| T009 | 2 | Add the code-symbol provenance normalization test | Focused regression for no-docstring and span preservation. |
| T010 | 3 | Add the markdown discovery integration test | Exercises the markdown path, breadcrumb formatting, and preview output. |
| T011 | 3 | Implement markdown query ranking and preview shaping | Moderate logic across service and result model boundaries. |
| T012 | 2 | Add the markdown extraction unit test | Straightforward nested-heading and preview regression. |
| T013 | 3 | Add the incremental refresh and interrupted recovery integration test | Exercises watcher/update flow and last-good snapshot behavior. |
| T014 | 5 | Implement watchdog/post-commit refresh and incremental content-hash updates | Multi-boundary lifecycle work across watcher, service, and refresh scheduling. |
| T015 | 3 | Implement atomic swap and last-good snapshot preservation | Store-level failure handling with a clear rollback/no-partial-write invariant. |
| T016 | 5 | Add exclusion and post-edit surfacing regression tests | Requires fixture edits, excluded-path verification, and query-after-edit validation. |
| T017 | 3 | Add the staleness delta integration test | Needs build-at-A / observe-at-B setup and explicit commit-delta assertions. |
| T018 | 3 | Implement staleness reporting in service and adapters | Service + CLI/MCP plumbing for freshness status, not just data storage. |
| T019 | 2 | Add quickstart assertions for staleness output and update guidance | Documentation-focused validation with a small amount of command text coupling. |
| T020 | 2 | Update quickstart smoke validation for the final local workflow | Mostly docs and operator steps, with a narrow smoke-check surface. |
| T021 | 2 | Finish the final local workflow documentation | Low-complexity documentation polish across the operator path. |
| T022 | 5 | Add the SC-001/SC-002 timing-budget benchmark regression | Deterministic performance harness work across full build and incremental refresh timing. |
| T023 | 5 | Add the max-volume load regression | Synthetic large-fixture coverage that must prove the index stays queryable without OOM failure. |
| T024 | 2 | Add the configurable exclude-pattern regression | Focused regression to prove configured exclusion rules are honored beyond the built-in generated-artifact exclusions. |
| T025 | 3 | Implement configurable exclude-pattern loading and filtering | Small but real configuration and extractor-path change with clear policy behavior. |

---

### T002 — Solution Sketch

**Modify**: `src/mcp_codebase/index/domain.py:IndexScope`, `CodeSymbol`, `MarkdownSection`, `IndexMetadata`, `QueryResult`; `src/mcp_codebase/index/config.py:IndexConfig`  
**Create**: `src/mcp_codebase/index/domain.py`, `src/mcp_codebase/index/config.py`  
**Reuse**: Existing repo-root and path-validation conventions from `src/mcp_codebase/config.py` and `security.py`  
**Composition**: Domain models define the finite freshness and result shapes; config centralizes storage path, model id, and scope defaults for the service and adapters  
**Failing test assertion**: A build or ingest path should reject malformed freshness metadata and preserve typed fields for source path, line range, and scope  
**Domains touched**: 02, 09, 17

### T003 — Solution Sketch

**Modify**: `src/mcp_codebase/index/extractors/python.py:extract_python_symbols`; `src/mcp_codebase/index/extractors/markdown.py:extract_markdown_sections`  
**Create**: `src/mcp_codebase/index/extractors/python.py`, `src/mcp_codebase/index/extractors/markdown.py`  
**Reuse**: Existing path-safety conventions and markdown section-reading patterns  
**Composition**: Python extraction turns AST/tree-sitter output into symbol units; markdown extraction turns headings/content into breadcrumbed section units; both feed the same normalized content unit schema  
**Failing test assertion**: A symbol with no docstring still produces a valid record, and generated artifacts or excluded paths are skipped instead of causing a failure  
**Domains touched**: 02, 12, 14, 17

### T004 — Solution Sketch

**Modify**: `src/mcp_codebase/index/store/chroma.py:ChromaIndexStore`; `src/mcp_codebase/index/service.py:VectorIndexService`; `build_vector_index_service`  
**Create**: `src/mcp_codebase/index/store/chroma.py`, `src/mcp_codebase/index/service.py`  
**Reuse**: Existing local codegraph health/freshness patterns and repo-local storage conventions under `.codegraphcontext/`  
**Composition**: The service orchestrates build/query/refresh/status; the store stages writes, atomically swaps snapshots, and preserves the prior active collection on failure  
**Failing test assertion**: An interrupted refresh leaves the previous snapshot queryable and the active collection never shows partial state  
**Domains touched**: 03, 04, 07, 11, 12, 14, 17

### T005 — Solution Sketch

**Modify**: `src/mcp_codebase/server.py:register_vector_index_tools`; `src/mcp_codebase/indexer.py:main`  
**Create**: `src/mcp_codebase/indexer.py`  
**Reuse**: Existing MCP registration pattern in `server.py` and the repo’s CLI entry-point style  
**Composition**: The MCP server exposes search/status/refresh through the shared service; the CLI adapter stays thin and delegates all decisions to the same service implementation  
**Failing test assertion**: A query or refresh request routes through the shared service and preserves the existing pyright tools unchanged  
**Domains touched**: 10, 16, 17

### T006 — Solution Sketch

**Modify**: `tests/integration/test_codebase_vector_index.py:test_code_symbol_lookup_returns_metadata`; service query path and fixtures  
**Create**: `tests/integration/test_codebase_vector_index.py`  
**Reuse**: Existing `tests/integration/` style and repo-local fixture patterns  
**Composition**: The integration test builds the index over representative source, exercises code-symbol search, and checks that rank/top-K/metadata are actionable for `read_code_context` follow-up  
**Failing test assertion**: Querying a known code concern returns the correct symbol in the top results with file path, line range, and symbol type  
**Domains touched**: 12, 14, 17

### T008 — Solution Sketch

**Modify**: `src/mcp_codebase/index/service.py:VectorIndexService.query`; `src/mcp_codebase/index/domain.py:QueryResult`  
**Create**: none  
**Reuse**: Existing service orchestration and typed result contracts  
**Composition**: Query ranking and scope filtering stay in the service layer, and the result model packages the file span and provenance needed to jump directly into the read tool  
**Failing test assertion**: A code-only query returns ranked results with complete metadata and an empty query path returns an empty list rather than an error  
**Domains touched**: 04, 10, 14, 17

### T010 — Solution Sketch

**Modify**: `tests/integration/test_codebase_vector_index.py:test_markdown_section_lookup_returns_breadcrumb`; markdown fixtures  
**Create**: `tests/integration/test_codebase_vector_index.py`  
**Reuse**: Existing markdown reading and breadcrumb conventions from the repo’s documentation workflow  
**Composition**: The integration test indexes `specs/` and `.claude/`, queries a topic phrase, and verifies breadcrumb, file path, and preview are enough for direct section reads  
**Failing test assertion**: A markdown-topic query returns the expected section header chain and preview text without requiring a broad file scan  
**Domains touched**: 12, 14, 16, 17

### T011 — Solution Sketch

**Modify**: `src/mcp_codebase/index/service.py:VectorIndexService.query`; `src/mcp_codebase/index/domain.py:MarkdownSection`  
**Create**: none  
**Reuse**: Existing service/query shape and markdown section contract  
**Composition**: Markdown query ranking mirrors code query behavior but returns breadcrumbed sections and previews, keeping the adapter contract consistent across content types  
**Failing test assertion**: A markdown-only query returns section results with breadcrumb and preview while a code-only scope excludes markdown entries  
**Domains touched**: 04, 10, 14, 17

### T013 — Solution Sketch

**Modify**: `tests/integration/test_codebase_vector_index.py:test_incremental_refresh_preserves_last_good_snapshot`; watcher fixtures  
**Create**: `tests/integration/test_codebase_vector_index.py`  
**Reuse**: Existing refresh/freshness patterns from the codegraph health workflow  
**Composition**: The integration test edits a file, triggers refresh, and verifies the new symbol appears while an interrupted run still leaves the previous snapshot queryable  
**Failing test assertion**: An interrupted refresh does not replace the active snapshot and does not make queries fail spuriously  
**Domains touched**: 07, 11, 12, 17

### T014 — Solution Sketch

**Modify**: `src/mcp_codebase/index/service.py:VectorIndexService.refresh_changed_files`; watcher plumbing  
**Create**: none  
**Reuse**: Repository-local file-change detection patterns and the existing safe refresh posture  
**Composition**: The service computes the changed-file set, refreshes only those sources, and uses watchdog/post-commit triggers as front doors to the same incremental update path  
**Failing test assertion**: A changed file refreshes the index without rebuilding unchanged data, and duplicate watcher events coalesce into one update cycle  
**Domains touched**: 07, 11, 12, 17

### T015 — Solution Sketch

**Modify**: `src/mcp_codebase/index/store/chroma.py:ChromaIndexStore`  
**Create**: none  
**Reuse**: The repo’s existing last-good / safe-reindex philosophy from codegraph health handling  
**Composition**: Refresh writes stage into a separate snapshot, then swap the active collection only after the staged data is complete and validated  
**Failing test assertion**: If refresh fails mid-run, the prior snapshot remains active and no partial write becomes query-visible  
**Domains touched**: 03, 11, 12, 17

### T016 — Solution Sketch

**Modify**: `tests/integration/test_codebase_vector_index.py:test_refresh_excludes_generated_artifacts`; extractors  
**Create**: `tests/integration/test_codebase_vector_index.py`  
**Reuse**: Existing exclusion conventions and repo-local generated-artifact boundaries  
**Composition**: The regression suite verifies that `__pycache__`, `.pyc`, and configured excludes never enter the index, and that a local edit makes the updated symbol surface after refresh  
**Failing test assertion**: Generated artifacts are skipped and a post-edit query returns the edited symbol instead of the stale one  
**Domains touched**: 12, 13, 14, 17

### T017 — Solution Sketch

**Modify**: `tests/integration/test_codebase_vector_index.py:test_staleness_reports_commit_delta`; fixture setup  
**Create**: `tests/integration/test_codebase_vector_index.py`  
**Reuse**: Existing commit-vs-head freshness model from codegraph health checks  
**Composition**: The test builds at one commit, advances the working tree, and verifies the status path reports both the recorded commit and the current delta  
**Failing test assertion**: After HEAD moves, the status path reports stale-by-N rather than claiming the index is current  
**Domains touched**: 11, 12, 17

### T018 — Solution Sketch

**Modify**: `src/mcp_codebase/index/service.py:VectorIndexService.status`; MCP/CLI adapters  
**Create**: none  
**Reuse**: Existing doctor/status output patterns and the shared service factory  
**Composition**: Status reporting stays derived from stored metadata and HEAD comparison, then the MCP and CLI surfaces render that same freshness result to callers  
**Failing test assertion**: The status path reports `up to date` or `stale` with a recorded commit delta instead of a raw internal state dump  
**Domains touched**: 10, 16, 17

### T022 — Solution Sketch

**Modify**: `tests/integration/test_codebase_vector_index_performance.py:test_index_build_and_refresh_meets_timing_budgets`; benchmark fixtures or harness helpers  
**Create**: `tests/integration/test_codebase_vector_index_performance.py`  
**Reuse**: Existing deterministic test patterns and the feature’s local build/refresh commands  
**Composition**: The benchmark regression measures the full build and a single-file incremental update against the spec timing budgets, using fixed fixtures and a bounded assertion window so the result is repeatable  
**Failing test assertion**: Full build exceeds the SC-001 budget or single-file refresh exceeds the SC-002 budget under the repo’s local fixture set  
**Domains touched**: 04, 11, 12, 17

### T023 — Solution Sketch

**Modify**: `tests/integration/test_codebase_vector_index_performance.py:test_index_handles_max_volume_without_oom`; large-fixture generation  
**Create**: `tests/integration/test_codebase_vector_index_performance.py`  
**Reuse**: The same local indexing pipeline and query surface used by the functional tests  
**Composition**: The load regression generates or loads a bounded synthetic corpus above the max-volume threshold and verifies the index can build and answer queries without OOM or partial-state failure  
**Failing test assertion**: A corpus with >1,000 symbols or >500 markdown sections causes memory failure, incomplete indexing, or an unqueryable active snapshot  
**Domains touched**: 04, 11, 12, 17

### T024 — Solution Sketch

**Modify**: `tests/integration/test_codebase_vector_index_performance.py:test_configurable_excludes_respected`; exclusion fixtures  
**Create**: `tests/integration/test_codebase_vector_index_performance.py`  
**Reuse**: Existing generated-artifact exclusion expectations and the same local indexing harness used by the other integration tests  
**Composition**: The regression injects a configured exclude pattern that is not one of the built-in defaults, then verifies the indexed content skips matching paths while still indexing the rest of the corpus  
**Failing test assertion**: A path matched by configured excludes still appears in the index, or the configured exclude rule is ignored entirely  
**Domains touched**: 12, 13, 14, 17

### T025 — Solution Sketch

**Modify**: `src/mcp_codebase/index/config.py:IndexConfig.exclude_patterns`; extractor filtering path  
**Create**: none  
**Reuse**: Existing scope-filter and generated-artifact exclusion behavior from the extractor pipeline  
**Composition**: Configured exclude patterns are loaded into the index configuration and applied consistently by both code and markdown extractors before embedding, so the policy is enforced before data reaches the store  
**Failing test assertion**: A configured exclude pattern is not honored by the index pipeline or is only applied to one extractor path  
**Domains touched**: 04, 11, 12, 17

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 2 | 2 | 2 |
| Phase 2: Foundational | 14 | 4 | 0 |
| Phase 3: User Story 1 | 10 | 4 | 2 |
| Phase 4: User Story 2 | 10 | 4 | 2 |
| Phase 5: User Story 3 | 16 | 4 | 2 |
| Phase 6: User Story 4 | 8 | 3 | 1 |
| Phase 7: Performance, Scale & Cross-Cutting Concerns | 12 | 3 | 3 |
| Phase 8: Exclusion Pattern Coverage | 5 | 2 | 0 |
| **Total** | **77** | **26** | **12** |

---

## Warnings

- None.
- No task scores 8 or 13.
- No async lifecycle guard gap remains unrepresented in the task graph.
- No state-safety or transaction-integrity gap remains unrepresented in the task graph.
