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

## Key Runtime Symbols

The main runtime symbols for this path are:

- [`_ReadCodeRerankerBackend`](/Users/andreborczuk/app-foundation/scripts/read_code.py)
  - the `read_code.py` side MCP client/session owner
  - routes semantic query and rerank requests into the live backend
- [`project_backend_server.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
  - the live MCP stdio server process
  - registers `query`, `score`, `read_code_context`, `read_code_find`, `read_code_analyze`, `read_code_window`, `warmup`, `health`, and identity/runtime probe tools
- [`_DirectReadCodeBackend`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
  - the in-server adapter that lets direct `read_code_*` MCP tools reuse the already-live vector/rerank backend without spawning a nested client
- [`_ensure_vector_index_ready`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
  - the MCP-server readiness gate
  - it now uses the cheap active-snapshot seam instead of the old heavy `status()` walk on each read
- [`warmup`](/Users/andreborczuk/app-foundation/src/mcp_codebase/project_backend_server.py)
  - primes one representative scoped semantic query and one five-passage rerank so the first real contextual read does not pay a separate compile/warmup hit
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
- `mps` also keeps a large resident model footprint because the reranker is long-lived in the MCP server
- `cpu` avoids the MPS accelerator footprint, but rerank latency is materially worse

This means:

- the accepted fast agent path is a warm MCP server with the reranker already loaded
- the main runtime cost is now intentional model residency, not repeated process startup
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

- repeated direct MCP read calls reuse one warm backend `pid` inside one live server process
- repeated backend calls inside one `read_code` Python process also reuse one backend `pid`
- semantic query and rerank use the same backend process
- backend failures fail fast to local/heuristic fallback

Not guaranteed now:

- separate fresh `uv run --no-sync python scripts/read_code.py ...` invocations do not reuse one backend automatically
- command hooks or helper subprocesses that open their own stdio MCP client session do not attach to the already-running Codex-managed MCP server
- separate agent/chat sessions should not assume they will inherit the same backend `pid`

That distinction is the current boundary of the design.

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
      - `selected_device: "mps"` when MPS is exposed
   - `warmup` now primes:
      - one representative scoped semantic query against `scripts/read_code.py`
      - one five-passage shortlist rerank shaped like a real `read_code_context` call
5. Optionally measure the live rerank path after warmup:
   - call `score_probe`

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

If `mps_available` is `false`, the live MCP server is still CPU-bound even if the local repo Python environment can see MPS outside the sandbox.

The stdio backend now also keeps an owner-scoped singleton pid file under `.codegraphcontext/read-code-mcp-runtime/`.
That guard reaps older backend processes started by the same launcher domain before recording the current pid, which prevents repeated test and probe runs from piling up stale MCP server processes.

## Expected Cold Starts

Expected timings are now split into three categories:

1. First rerank after MCP server start
   - one-time model/backend load plus first MPS execution warmup
   - observed fresh local MCP `warmup` on May 17, 2026:
     - `selected_device: "mps"`
     - `elapsed_ms: 5534.555`

2. First rerank probe after explicit warmup
   - same live MCP server, same model already loaded, but first bounded probe after the explicit warmup step
   - observed fresh local MCP `score_probe` on May 17, 2026:
     - `3` passages
     - `selected_device: "mps"`
     - `elapsed_ms: 1954.922`

3. Warm rerank after the first probe
   - same live MCP server, same model already loaded
   - observed fresh local MCP `score_probe` on May 17, 2026:
     - repeat `3`-passage probe
     - `elapsed_ms: 25.313`

4. Full `read_code_context` on a fresh session id
   - includes semantic query plus shortlist rerank plus shared `read_code` orchestration
   - observed live MCP reads on May 17, 2026:
     - first scoped `_resolve_pattern_anchor` read after server refresh: about `5.66s`
     - later fresh-session scoped reads on the same warm server: about `1.0s`

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
