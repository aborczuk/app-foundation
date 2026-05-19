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
- paired with one detached repo-local daemon:
  - [`src/mcp_codebase/index/reranker_daemon.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/reranker_daemon.py)
  - owns semantic query and rerank state behind one shared local endpoint

The backend exposes bounded MCP tools:

- `get_process_identity`
- `health`
- `query`
- `score`
- `read_code_context`
- `read_code_find`
- `read_code_analyze`
- `read_code_window`

## Key Runtime Symbols

The main runtime symbols for this path are:

- [`_ReadCodeRerankerBackend`](/Users/andreborczuk/app-foundation/scripts/read_code.py)
  - the `read_code.py` side MCP client/session owner
  - owns stdio child reuse for CLI callers
  - owns daemon lifecycle and endpoint discovery for the detached background daemon
- [`project_backend_server.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
  - the live MCP stdio server process
  - registers `query`, `score`, `read_code_context`, `read_code_find`, `read_code_analyze`, `read_code_window`, `warmup`, `health`, `daemon_runtime_report`, and identity/runtime probe tools
- [`_DirectReadCodeBackend`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
  - the in-server adapter that routes semantic query and rerank requests through the detached daemon-backed backend
- [`_DaemonVectorQueryService`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
  - the in-server proxy that lets `read_code.py` query helpers use daemon-owned semantic results without re-instantiating a local `VectorIndexService`
- [`daemon_runtime_report`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
  - the bounded ownership evidence tool for the spike path
  - reports shim identity separately from daemon identity so child-churn reattachment can be verified directly
- [`reranker_daemon.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/reranker_daemon.py)
  - the detached daemon entrypoint
  - serves both `/query` and `/score` over the shared local endpoint
- [`warmup`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
  - primes one representative scoped semantic query and one five-passage rerank through the daemon so the first real contextual read does not pay a separate query/rerank warmup hit
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

- `mps` gives the accepted warm-path latency for direct MCP reads
- `mps` also keeps a large resident model footprint because the reranker is long-lived in the detached daemon
- `cpu` avoids the MPS accelerator footprint, but rerank latency is materially worse

This means:

- the accepted fast agent path is a warm detached daemon with semantic query and rerank already loaded
- the stdio MCP child is now disposable; the warm-state owner is the daemon, not the MCP process
- the main runtime cost is now intentional daemon residency, not repeated stdio child startup
- when memory pressure matters more than latency, the relevant seam is the reranker backend in [`chroma.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/store/chroma.py), not the MCP transport layer

## Ownership Split

The shared [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py) orchestration still owns:

- request parsing
- scratchpad reuse
- candidate shaping and rendering
- fallback policy
- metadata logging

The detached daemon now owns:

- `VectorIndexService`
- semantic `query`
- reranker `score`

The MCP stdio child now owns:

- direct agent-facing `read_code_context`
- direct agent-facing `read_code_find`
- direct agent-facing `read_code_analyze`
- direct agent-facing `read_code_window`

## Current Reuse Boundary

Guaranteed now:

- repeated direct MCP read calls reuse one warm backend `pid` inside one live server process
- repeated fresh stdio MCP child sessions can reconnect to the same daemon `pid`
- repeated backend calls inside one `read_code` Python process also reuse one daemon `pid`
- semantic query and rerank use the same daemon process
- stdio child churn does not require daemon churn

Not guaranteed now:

- separate fresh `uv run --no-sync python scripts/read_code.py ...` invocations do not reuse one stdio child automatically
- separate agent/chat sessions should not assume they will inherit the same stdio child `pid`
- if the daemon is intentionally stopped, the next caller will pay the daemon startup cost again

That distinction is the current boundary of the design.

## Verified Behavior

Direct live backend proof passes and now exercises the MCP-native read surface:

- `SPECKIT_RUN_LIVE_MCP_PERSISTENCE_TESTS=1 uv run --no-sync python scripts/pytest_guard.py run -- tests/integration/test_codebase_vector_index_performance.py::test_live_project_local_mcp_server_exposes_identity_health_query_and_score`
- daemon-vs-shim ownership proof on fresh stdio sessions:
  - `SPECKIT_RUN_LIVE_MCP_PERSISTENCE_TESTS=1 uv run --no-sync python scripts/pytest_guard.py run -- tests/integration/test_codebase_vector_index_performance.py::test_live_project_local_mcp_daemon_runtime_report_matches_across_stdio_sessions`
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

## Runtime Setup

Use this checklist when starting a new Codex session and expecting warm `read_code` behavior:

1. Refresh the session so the project-local MCP server reloads the current `.codex/config.toml`.
2. Confirm the MCP server exposes the direct read tools:
   - `read_code_context`
   - `read_code_find`
   - `read_code_analyze`
   - `read_code_window`
   - the Codex MCP config now launches the server with the repo venv Python directly, so after refresh you should see one `project_backend_server` process instead of a parent `uv` wrapper plus child Python pair
3. Confirm accelerator visibility on the live MCP server before trusting rerank timings:
   - call `get_runtime_capabilities`
   - verify:
      - `mps_built: true`
      - `mps_available: true`
      - `cuda_available: false` is expected on Apple silicon
4. Prime the reranker before the first real read:
   - call `warmup`
   - verify:
      - `warmup_completed: true`
      - `daemon.healthy: true`
   - `warmup` now primes:
      - one representative scoped semantic query against `scripts/read_code.py`
      - one five-passage shortlist rerank shaped like a real `read_code_context` call
      - both of those now run through the detached daemon rather than a local in-process vector service
5. Optionally measure the live rerank path after warmup:
   - call `score_probe`

If `mps_available` is `false`, the live MCP server is still CPU-bound even if the local repo Python environment can see MPS outside the sandbox.

The stdio backend now also keeps an owner-scoped singleton pid file under `.codegraphcontext/read-code-mcp-runtime/`.
That guard reaps older backend processes started by the same launcher domain before recording the current pid, which prevents repeated test and probe runs from piling up stale MCP server processes.

## Expected Cold Starts

Expected timings are now split into three categories:

1. First daemon warmup after the detached daemon starts
   - one-time model/backend load plus first semantic-query/rerank warmup
   - the stdio child may still be fresh even when the daemon is already warm

2. First bounded probe after explicit warmup
   - same daemon, same model already loaded, but first bounded probe after the explicit warmup step

3. Warm rerank after the first probe
   - same daemon, same model already loaded

4. Full `read_code_context` on a fresh session id
   - includes semantic query plus shortlist rerank plus shared `read_code` orchestration
   - the important invariant is now:
     - the daemon `pid` and `startup_timestamp` stay stable
     - fresh stdio child `pid`s can change without forcing daemon reload

These numbers are acceptance landmarks, not hard promises. The important split is:

- first probe after server start pays warmup
- calling `warmup` at session start moves that one-time hit off the first real user read
- after the representative warmup, the first scoped `read_code_context` call should land much closer to the normal warm regime instead of paying a separate context-shaped compile hit
- repeated rerank probes on the same server should be in the low hundreds of milliseconds or better on MPS
- full direct contextual reads should be much faster after the first warmup than they were on the old CPU-bound path

## Operational Risks

The main operational risks on this path are:

- high resident memory on `mps`
  - the reranker is intentionally long-lived inside the MCP server
  - warm latency improves, but memory residency is materially higher than the CPU path
- accelerator visibility differs by runtime
  - the live MCP server may see `mps` even when other sandboxed Python paths do not
  - capability must be checked on the actual live MCP server, not inferred from another process
- stdio ownership boundaries are strict
  - a separate stdio MCP client creates its own server process
  - hooks and helper subprocesses do not share the already-managed Codex MCP server automatically
- standalone CLI reads remain cold by design
  - fresh `uv run ... scripts/read_code.py ...` invocations are compatibility-only and still pay per-process startup

## Where To Change It

Use these seams when changing runtime behavior:

- MCP server lifecycle and tool registration:
  - [`project_backend_server.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
- `read_code.py` MCP client/session behavior and fallback policy:
  - [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py)
- local reranker model loading, device choice, and precision policy:
  - [`chroma.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/store/chroma.py)
- vector index readiness and active snapshot usage:
  - [`service.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/service.py)
  - [`project_backend_server.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)

## Related Tests

The main guards for this runtime are:

- live MCP persistence and read-surface verification:
  - [`test_codebase_vector_index_performance.py`](/Users/andreborczuk/app-foundation/tests/integration/test_codebase_vector_index_performance.py)
- MCP server behavior and warmup/runtime probes:
  - [`test_project_backend_server.py`](/Users/andreborczuk/app-foundation/tests/unit/test_project_backend_server.py)
- reranker device and precision policy:
  - [`test_vector_index_store.py`](/Users/andreborczuk/app-foundation/tests/unit/test_vector_index_store.py)
- `read_code.py` backend integration and fallback behavior:
  - [`test_read_code_reranker_daemon.py`](/Users/andreborczuk/app-foundation/tests/unit/test_read_code_reranker_daemon.py)

## Accepted Constraint

The original sandboxed-agent goal is satisfied on the direct MCP path:

- direct `read_code_*` calls keep the same `pid` and `started_at` across agent turns inside one live Codex session

The original goal is not satisfied on the standalone CLI path:

- fresh `uv run ... scripts/read_code.py ...` subprocesses remain compatibility-only and are not the accepted warm path for agent reads
