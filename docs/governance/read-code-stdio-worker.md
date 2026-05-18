# Read Code MCP Backend

This document describes the active warm-backend path behind [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py).

## Purpose

`read_code` has two expensive backend costs on fresh semantic work:

- semantic query service startup
- reranker model startup

The active design pushes both costs into one MCP-backed backend process so repeated backend requests inside one `read_code` Python process do not rebuild that runtime every call.

## Active Design

The live backend is:

- [`src/mcp_codebase/project_backend_server.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
- launched over stdio
- spoken to through an MCP client/session inside [`_ReadCodeRerankerBackend`](/Users/andreborczuk/app-foundation/scripts/read_code.py)

The backend exposes bounded MCP tools:

- `get_process_identity`
- `health`
- `query`
- `score`
- `read_code_context`
- `read_code_find`
- `read_code_analyze`
- `read_code_window`

## Ownership Split

The shared [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py) orchestration still owns:

- request parsing
- scratchpad reuse
- candidate shaping and rendering
- fallback policy
- metadata logging

The MCP backend now owns:

- `VectorIndexService`
- semantic `query`
- reranker `score`
- direct agent-facing `read_code_context`
- direct agent-facing `read_code_find`
- direct agent-facing `read_code_analyze`
- direct agent-facing `read_code_window`

## Current Reuse Boundary

Guaranteed now:

- repeated direct MCP read calls reuse one warm backend `pid` inside one live server process
- repeated backend calls inside one `read_code` Python process also reuse one backend `pid`
- semantic query and rerank use the same backend process
- backend failures fail fast to local/heuristic fallback

Not guaranteed now:

- separate fresh `uv run --no-sync python scripts/read_code.py ...` invocations do not reuse one backend automatically
- cross-turn proof for direct MCP `read_code_*` calls is still the remaining gate in the current thread

That distinction is the current open gap.

## Verified Behavior

Direct live backend proof passes and now exercises the MCP-native read surface:

- `SPECKIT_RUN_LIVE_MCP_PERSISTENCE_TESTS=1 uv run --no-sync python scripts/pytest_guard.py run -- tests/integration/test_codebase_vector_index_performance.py::test_live_project_local_mcp_server_exposes_identity_health_query_and_score`
- artifact-backed cross-turn direct-MCP proof passes:
  - baseline: `.codegraphcontext/read-code-mcp-read-surface-baseline.json`
  - comparison: `.codegraphcontext/read-code-mcp-read-surface-probe.json`
  - validator:
    - `uv run --no-sync python scripts/pytest_guard.py run -- tests/integration/test_codebase_vector_index_performance.py::test_live_project_local_mcp_read_surface_artifact_matches_across_turns`

Same-process rerank reuse passes:

- `SPECKIT_RUN_LIVE_RERANKER_STDIO_CONTEXT_TESTS=1 uv run --no-sync python scripts/pytest_guard.py run -- tests/integration/test_codebase_vector_index_performance.py::test_live_read_code_context_records_worker_rerank_source_without_restarting_worker`

Same-process semantic query reuse passes:

- `SPECKIT_RUN_LIVE_RERANKER_STDIO_CONTEXT_TESTS=1 uv run --no-sync python scripts/pytest_guard.py run -- tests/integration/test_codebase_vector_index_performance.py::test_live_vector_query_candidates_reuse_worker_without_local_service`

Fresh CLI invocation persistence currently fails:

- `uv run --no-sync python scripts/probe_read_code_worker_persistence.py --reset`
- `uv run --no-sync python scripts/probe_read_code_worker_persistence.py`

Observed on May 17, 2026:

- first backend `pid`: `47366`
- second backend `pid`: `47540`
- `same_pid: false`
- `same_started_at: false`

So the active path is MCP-backed, but still per-invocation for standalone CLI use.

Observed on May 17, 2026 for the accepted direct MCP read surface:

- baseline backend `pid`: `56118`
- comparison backend `pid`: `56118`
- `same_pid: true`
- `same_started_at: true`

## Practical Reading

When evaluating `read_code` performance:

- reread speed is usually a scratchpad question
- fresh query/rerank speed inside one process is now an MCP backend question
- direct agent reads should target the MCP `read_code_*` tools, not fresh CLI subprocesses
- fresh standalone `uv run ... read_code.py ...` latency is still a process-boundary question

## Next Requirement

The original sandboxed-agent goal is now satisfied on the direct MCP path: direct `read_code_*` calls keep the same `pid` and `started_at` across agent turns. The CLI subprocess path remains compatibility-only and is not the accepted warm path for agent reads.
