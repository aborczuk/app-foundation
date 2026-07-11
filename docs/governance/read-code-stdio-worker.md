# Read Code In-Process Runtime

This document describes the active warm-backend path behind [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py).

## Purpose

`read_code` has two expensive backend costs on fresh semantic work:

- semantic query service startup
- reranker model startup

The active design keeps both costs in the process running `scripts/read_code.py`. It preserves the search scratchpad and metadata history artifacts, but it does not register or launch an MCP server.

## Active Design

The live runtime is [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py). Its `_ReadCodeRerankerBackend` calls the process-shared `VectorIndexService` directly for semantic queries and reranking.

## Key Runtime Symbols

The main runtime symbols for this path are:

- [`_ReadCodeRerankerBackend`](/Users/andreborczuk/app-foundation/scripts/read_code.py)
  - the in-process adapter for semantic query and rerank requests
- [`_load_read_code_vector_query_service`](/Users/andreborczuk/app-foundation/scripts/read_code.py)
  - owns the process-local `VectorIndexService` singleton
- [`_read_code_search_scratchpad_path`](/Users/andreborczuk/app-foundation/scripts/read_code_health.py)
  - persists candidate stepping state independently of runtime transport
- [`_LocalSequenceRerankerBackend`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/store/chroma.py)
  - local Hugging Face reranker wrapper used by the vector index store
- [`_select_torch_device`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/store/chroma.py)
  - device policy for the local reranker backend

## Model And Runtime Policy

The active reranker model is:

- `BAAI/bge-reranker-v2-m3`

The active reranker implementation is:

- [`_LocalSequenceRerankerBackend`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/store/chroma.py)

The current device selection policy is:

- [`_select_torch_device`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/store/chroma.py) prefers:
  - `cuda`
  - then `mps`
  - then `cpu`

The current precision policy is:

- `cuda`
  - load the reranker in half precision
- `mps`
  - load the reranker in half precision
- `cpu`
  - keep the reranker in full `float32`

The current memory/latency tradeoff is:

- `mps` gives the lowest in-process rerank latency when available
- the model remains resident only for the lifetime of the `read_code.py` process
- `cpu` avoids the MPS accelerator footprint, but rerank latency is materially worse

This means:

- each fresh CLI invocation may pay model initialization once
- repeated operations in one Python process reuse the loaded service
- when memory pressure matters more than latency, the relevant seam is the reranker backend in [`chroma.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/store/chroma.py), not the MCP transport layer

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

## Default Context Payload

The default `read_code_context` response is intentionally bounded and now returns two layers:

- one selected match block
- one ranked shortlist with up to three candidates from the same result set

Selected match block fields:

- `file_path`
- `signature`
- optional `docstring`
- `cosine_similarity`
- one hint line with bounded follow-up actions such as `--inline-body`, `--next-candidate`, and call-site analysis guidance

Default shortlist fields:

- `cosine_similarity`
- `file_path`
- `unit_id`
- `line_num-line_end`
- `type`
- `body`
- `docstring`
- `raw`

Operational notes:

- the shortlist is rendered by default; `--show-shortlist` remains accepted but is no longer required for the first response
- the shortlist stays capped at three rows even when the backend returned more candidates
- when more than three candidates exist, the response prints a truncation hint that points operators to `--next-candidate` or `--candidate-index N`
- `--inline-body` remains a second-step read and still requires a prior matching context query in the current session scratchpad

## Current Reuse Boundary

Guaranteed now:

- semantic query and rerank reuse the same `VectorIndexService` inside one `read_code.py` process
- scratchpad stepping and metadata history remain persistent artifacts across invocations
- runtime failures fall back to bounded heuristic behavior

Not guaranteed now:

- a fresh CLI invocation does not inherit a loaded vector service or model from an earlier process
- a separate agent or chat session does not inherit process memory

## Verified Behavior

The in-process path is verified by the focused read-code shortlist unit tests. They assert that semantic query and rerank call the shared vector service directly rather than `_worker_query` or `_worker_score`.

The expected command is `uv run --no-sync python scripts/read_code.py context "<query>" --path <path>`. It uses no MCP transport.

## Practical Reading

When evaluating `read_code` performance:

- reread speed is usually a scratchpad question
- fresh query/rerank speed is an in-process vector-service question
- direct agent reads should use the guarded `read_code.py` CLI entrypoint
- fresh CLI latency includes one process-local model/service initialization

## Runtime Setup

Use the standard guarded CLI command for each read. The first semantic query in that process initializes the local service; subsequent query and rerank calls in the same process share it. Scratchpad-based candidate follow-ups survive as repository artifacts without requiring runtime persistence.

## Refresh Triggers

The intended local index-refresh path for read-code discovery state is commit-scoped, not push-scoped.

Live Git hook wiring:

- repo Git hooks are loaded from `.githooks/` via `core.hooksPath`
- the active refresh hook is [`.githooks/post-commit`](/Users/andreborczuk/app-foundation/.githooks/post-commit)
- that hook dispatches to [`scripts/git_post_commit_refresh.py`](/Users/andreborczuk/app-foundation/scripts/git_post_commit_refresh.py)
- `git_post_commit_refresh.py` computes the files changed in `HEAD` and passes them to [`scripts/hook_refresh_indexes.py`](/Users/andreborczuk/app-foundation/scripts/hook_refresh_indexes.py)

Refresh behavior:

- `hook_refresh_indexes.py` requests both:
  - CodeGraph refresh
  - vector index refresh
- changed paths are collected from the commit diff and scoped before refresh
- codegraph refresh is routed through [`scripts/cgc_safe_index.py`](/Users/andreborczuk/app-foundation/scripts/cgc_safe_index.py)
- vector refresh is routed through `src.mcp_codebase.indexer refresh ...`

Important boundary:

- there is currently no repo-local `pre-push` refresh hook under `.githooks/`
- pushing code is therefore not the trigger that refreshes local read-code discovery state
- the intended automatic Git-triggered refresh boundary is `post-commit`
- deterministic edit flows may also invoke `hook_refresh_indexes.py` directly as part of local validation/sync workflows
- Codex `PostToolUse` edit hooks now route through [`scripts/hook_posttool_edit_validation.py`](/Users/andreborczuk/app-foundation/scripts/hook_posttool_edit_validation.py), which runs guarded Ruff and Pyright checks for changed Python files before delegating scoped CodeGraph and vector refreshes to [`scripts/hook_refresh_indexes.py`](/Users/andreborczuk/app-foundation/scripts/hook_refresh_indexes.py)

If MPS is unavailable in the CLI process, reranking falls back to CPU even if another local process can see MPS.

## Expected Cold Starts

The first semantic query in a CLI process pays local service and model initialization. Later semantic queries and reranks in that same process are warm. Separate CLI invocations are intentionally independent.

## Operational Risks

The main operational risks on this path are:

- high resident memory on `mps` for the lifetime of a read-code process
- accelerator visibility differs by Python process
- fresh CLI reads remain cold by design, while scratchpad candidate follow-ups stay available across invocations

## Where To Change It

Use these seams when changing runtime behavior:

- `read_code.py` in-process query/rerank behavior and fallback policy:
  - [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py)
- local reranker model loading, device choice, and precision policy:
  - [`chroma.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/store/chroma.py)
- vector index readiness and active snapshot usage:
  - [`service.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/service.py)

## Related Tests

The main guards for this runtime are:

- in-process read-code query/rerank behavior:
  - [`test_read_code_shortlist.py`](/Users/andreborczuk/app-foundation/tests/unit/test_read_code_shortlist.py)
- reranker device and precision policy:
  - [`test_vector_index_store.py`](/Users/andreborczuk/app-foundation/tests/unit/test_vector_index_store.py)
- `read_code.py` backend integration and fallback behavior:
  - [`test_read_code_reranker_daemon.py`](/Users/andreborczuk/app-foundation/tests/unit/test_read_code_reranker_daemon.py)

## Accepted Constraint

The runtime intentionally trades cross-turn model persistence for a direct, deterministic in-process path. The durable cross-turn state is the scratchpad and metadata history, not an MCP process.
