# Read Code Stdio Worker

This document describes the current long-lived worker path behind `scripts/read_code.py` for semantic retrieval and reranking.

## Purpose

`read_code` had two separate startup costs on fresh discovery:

- semantic query service initialization
- reranker model initialization

Within one long-lived Python process, both costs are now pushed into a persistent stdio worker so repeated `context` reads do not rebuild that runtime every request.

This document is about the active worker-backed path, not the older socket/file-RPC experiments.

## Why Stdio

The repo tried socket-backed daemon transport first. That did not hold up for the sandboxed agent path:

- direct UDS and loopback transport were not reliable from the sandbox
- file-RPC fallback added unacceptable latency and was removed

The active design keeps the worker in the same execution domain as the caller:

- one subprocess
- newline-delimited JSON over `stdin` / `stdout`
- no socket
- no file request/response queue

That gives a secure local transport boundary without widening network or filesystem surface area.

## Ownership Split

`read_code.py` remains the orchestrator. It still owns:

- request parsing
- scratchpad reuse
- semantic candidate selection
- fallback policy
- compact rendering
- search metadata logging

The stdio worker owns only expensive warm runtime state:

- `VectorIndexService`
- reranker model warmup
- semantic `query` execution
- reranker `score` execution

## Active Files

- `scripts/read_code.py`
  - client orchestration
  - worker lifecycle inside `_ReadCodeRerankerBackend`
  - semantic retrieval path in `_vector_query_candidates(...)`
- `src/mcp_codebase/index/reranker_stdio_worker.py`
  - persistent worker entrypoint
  - stdio request loop
  - `health`, `query`, `score`, and `shutdown` operations

## Request Protocol

The worker speaks one JSON object per line.

Startup:

- worker emits `{"op":"ready", ...}`

Supported requests:

- `{"op":"health"}`
- `{"op":"query","query":...,"top_k":...,"scope":...,"file_path":...}`
- `{"op":"score","query":...,"passages":[...]}`
- `{"op":"shutdown"}`

Supported responses:

- `ready`
- `health`
- `query`
- `score`
- `shutdown`

Every successful response includes the worker `pid`. Long-lived reuse is proven by stable `pid` across multiple requests.

## Startup And Reuse Flow

First worker-backed request in one `read_code` process:

1. `read_code` calls `_ensure_worker_ready()`
2. `_ensure_worker_ready()` launches `python -m src.mcp_codebase.index.reranker_stdio_worker`
3. worker constructs one `VectorIndexService`
4. worker warms the reranker once
5. worker emits `ready`
6. caller reuses that same process for later `query` and `score` requests

Subsequent worker-backed requests in the same `read_code` process:

1. caller keeps the cached subprocess handle
2. caller writes one JSON line
3. worker responds with one JSON line
4. no service rebuild and no reranker reload occurs

## Semantic Retrieval Flow

The active semantic query path is:

1. `_vector_find_candidates(...)`
2. `_vector_query_candidates(...)`
3. worker-backed `query_items(...)` on `_ReadCodeRerankerBackend`
4. worker `query` op inside `reranker_stdio_worker.py`
5. `VectorIndexService.query(...)`
6. serialized result items return to `read_code`
7. `_vector_matches_from_query_items(...)` converts and ranks them

Fallback:

- if worker query fails or is unavailable, `_vector_query_candidates(...)` falls back to the local in-process `VectorIndexService`

This keeps the read path working while still preferring the warm worker.

## Rerank Flow

The active rerank path is:

1. `_rerank_semantic_candidates(...)`
2. backend `score_pairs(...)`
3. worker `score` op
4. `VectorIndexService.rerank_scores(...)`

Fallback:

- if worker score fails or is unavailable, reranking falls back immediately to heuristic ordering

There is no longer a slow file-RPC fallback.

## What This Does And Does Not Guarantee

Guaranteed now:

- repeated worker-backed requests inside one `read_code` Python process reuse the same warm runtime
- semantic retrieval and reranking both use the same worker process
- worker failures fail fast

Not guaranteed now:

- separate fresh `uv run --no-sync python scripts/read_code.py ...` CLI invocations do not share one worker automatically
- this is process-local persistence, not system-wide daemon persistence

That distinction matters. The current design solves startup cost reuse for the agent-owned process path, not for unrelated standalone shell invocations.

## Relationship To Scratchpad Reuse

Scratchpad reuse and worker reuse solve different costs.

Scratchpad reuse:

- avoids repeating the same resolved search work in one session
- makes rereads effectively instant when the exact cached result is still valid

Worker reuse:

- reduces startup cost on fresh semantic retrieval and rerank work
- matters when there is no scratchpad hit yet

Both paths are active and complementary.

## Verification Surface

The worker path is verified in three layers:

- unit protocol tests for `health`, `query`, `score`, and `shutdown`
- unit client tests for worker-backed query/score and fallback behavior
- live integration tests proving:
  - worker PID stability across multiple `score` requests
  - worker PID stability across multiple `context` requests in one process
  - worker reuse for `_vector_query_candidates(...)` without touching the local service path

## Current Limits

- naming still reflects older daemon terminology in a few test/module names
- metadata currently emphasizes rerank source more than semantic query source
- cross-process persistence is still out of scope for the active worker design

## Practical Rule

When reasoning about `read_code` performance:

- exact reread speed is usually a scratchpad question
- fresh semantic search speed is now partly a stdio worker question
- separate shell invocation latency is still a process-boundary question
