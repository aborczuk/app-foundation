# Combined Plan - 031-speed-up-vector-context

_Feature: `031-speed-up-vector-context`_
_Source Spec: `spec.md`_
_Artifact: `plan.md`_

[This template documents every section the combined `speckit.plan` step may keep. `scripts/speckit_plan_step.py` prunes unused sections after triage so the emitted `plan.md` contains only the sections required by strategy.]

## Triage

- duplicate: false
- t_shirt_size: l
- risk_level: high
- reason: Existing specs cover vector indexing and intent anchoring, but none define the persistent reranker transport and sandbox-safe daemon boundary now needed to preserve first-query quality without regressing `read_code context`.

## Strategy Contract

```json
{
  "domains": {
    "reasoning": {
      "caching": "The plan still depends on scratchpad and trust reuse for rereads, and the reranker daemon must not disturb those cached fast paths.",
      "code patterns": "The main remaining work is a transport-boundary refactor: keep lifecycle and transport concerns out of the synchronous read path while preserving one scoring contract.",
      "observability": "The daemon needs bounded health, failure, and result-source signals so transport failures degrade cleanly and remain diagnosable in history and status surfaces.",
      "resilience": "The plan must preserve safe heuristic fallback when the daemon is unavailable, slow, or mismatched instead of making `context` depend on daemon success.",
      "testing": "Live verification must prove normal `context` queries actually consume daemon scores in this environment, while regression coverage proves fallback remains safe."
    },
    "relevant": [
      "caching",
      "resilience",
      "testing",
      "code patterns",
      "observability"
    ]
  },
  "risk": {
    "external_dependency_uncertainty": "medium",
    "human_operator_dependency": "medium",
    "overall": "high",
    "repo_uncertainty": "medium",
    "requirement_clarity": "medium",
    "runtime_side_effect_risk": "high",
    "state_data_migration_risk": "low"
  },
  "strategy": {
    "architecture_diagram": false,
    "architecture_strategy": true,
    "expanded_design_notes": true,
    "external_research": false,
    "net_new_surface": false,
    "strategy_reason": "The original latency-routing plan still stands, but the remaining unsolved problem is now the persistent reranker transport and lifecycle boundary. That needs an additive architecture update and verification slices without discarding the earlier scoped/broad trust work."
  },
  "triage": {
    "duplicate": false,
    "duplicate_matches": [
      "specs/020-codebase-vector-index/spec.md",
      "specs/025-intent-anchor-routing/spec.md"
    ],
    "duplicate_reason": "Existing specs cover vector indexing and intent anchoring, but none define the persistent reranker transport and sandbox-safe daemon boundary now needed to preserve first-query quality without regressing `read_code context`.",
    "risk_level": "high",
    "tshirt_size": "l"
  }
}
```

## Internal Discovery

### Term: specification

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/validate_catalog.py`

### Term: faster

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/README.md`

### Term: read_code

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/read_code.py`

### Term: context

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/speckit_build_offline_qa_payload.py`

### Term: retrieval

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/specs/025-intent-anchor-routing/huds/T002.md`

## Relevant Domains

- `caching`: Session and scope trust reuse remain the primary reread latency lever, and daemon scoring must layer on top without invalidating scratchpad-based fast paths.
- `resilience`: The reranker daemon can improve first-query ordering only if transport or lifecycle failures degrade to heuristic ranking without breaking `context`.
- `testing`: The remaining problem is no longer theoretical architecture; it requires live proof that `context` actually records `rerank_source: daemon` under the accepted benchmark queries.
- `code patterns`: The main refactor is separating transport/lifecycle management from synchronous query execution while preserving one rerank contract.
- `observability`: Health, cooldown, result-source, and failure-marker behavior have to stay explicit so the daemon remains operable and diagnosable.

## Summary

Split `read_code context` into scoped and broad request paths, make vector freshness proof conditional instead of mandatory, and remove avoidable sequential code-plus-markdown work for scoped code queries. Keep markdown-aware broad discovery for “how does this work?” questions, but only pay broader trust and mixed-scope costs when the query shape or result quality requires them.

Add a persistent reranker-service layer on top of that faster base path. The daemon remains reranker-only, but it must expose a transport and lifecycle model that works both for host-shell reads and for sandboxed agent reads, without putting startup, repair, or transport failure handling on the synchronous `context` path.

## Internal Research

- The original exact-symbol scoped benchmark measured about `8.65s` total in-process for `_vector_anchor_rank` against [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py).
- Preflight consumed about `5.75s`, while semantic query work consumed about `2.90s`.
- The expensive preflight seam was vector freshness, not codegraph availability: `vector_index_probe()` took about `5.63s`, while `_ensure_codegraph_session_available()` was effectively `0.003s`.
- Scoped query work previously ran both `_vector_find_candidates(..., "code")` and `_vector_find_candidates(..., "markdown")` from [`_query_semantic_anchor_candidate`](/Users/andreborczuk/app-foundation/scripts/read_code.py:707), even for a Python-file exact symbol query.
- The current reread path has already been repaired with scratchpad reuse: accepted repeated queries now drop from about `3.0s` first-read backend time to about `15ms-16ms` rereads in the same session.
- The remaining user-visible pain is first-query cost and first-query ordering quality, not repeated-read latency.
- The host-managed reranker daemon can stay healthy over a Unix socket, but sandboxed agent reads cannot connect to Unix sockets or loopback TCP in this environment; direct connect attempts fail with `operation not permitted`.
- A shared-files request/response channel is therefore the only currently viable transport between the sandboxed `read_code` client and the long-lived host daemon.
- Manual file-RPC requests succeed for small score batches, but live `context` still needs bounded shortlist-sized rerank requests and proof that the normal query path records `rerank_source: daemon`.
- Verification commands for the settled daemon path:
  - `uv run --no-sync python scripts/read_code.py daemon status`
  - `SPECKIT_RUN_LIVE_RERANKER_DAEMON_TESTS=1 uv run --no-sync python scripts/pytest_guard.py run -- tests/integration/test_codebase_vector_index_performance.py::test_live_read_code_context_records_daemon_rerank_source_without_restarting_daemon`
  - `READ_CODE_SESSION_ID=daemon-live-check-1 uv run --no-sync python scripts/read_code.py context "_vector_trust_decision" --path scripts/read_code_health.py`
  - `READ_CODE_SESSION_ID=daemon-live-check-2 uv run --no-sync python scripts/read_code.py context "_vector_trust_decision" --path scripts/read_code_health.py`
- Verified daemon outcome: the two fresh-session live queries both recorded `rerank_source: daemon`, and the live integration test proved the daemon `started_at` value remained stable across separate first-search requests.

## Architecture Strategy

Keep the earlier two-path `read_code context` architecture:

- Scoped path:
  - classify symbol-shaped, path-scoped, or file-local requests before global vector freshness proof
  - use scope-local trust or healthy session trust first
  - skip markdown retrieval unless content type, file type, or query shape requires it
  - escalate to heavier freshness proof or fallback only after a miss, weak result, stale trust state, or conflicting candidates
- Broad path:
  - preserve markdown-aware semantic discovery for behavior questions
  - allow healthy session trust to satisfy normal repeated reads
  - run the slower trust or recovery path only when broad discovery is empty, weak, stale, or ambiguous

Layer the reranker on top of that architecture as a transport-neutral post-retrieval scorer:

- The synchronous read path may only do:
  - health probe
  - bounded score request over the active transport
  - heuristic fallback if anything fails or times out
- The synchronous read path must not do:
  - daemon startup
  - PID/socket cleanup
  - launch-service management
  - blocking repair loops
- Transport policy:
  - host-shell path can use Unix-socket HTTP
  - sandboxed agent path must use the shared-files RPC transport under current policy
  - both transports must satisfy the same score request/response contract so rerank behavior does not fork by transport

This split is necessary because the remaining latency problem is not trust routing anymore; it is keeping a warm reranker model available without making ordinary `context` reads depend on socket permissions or daemon lifecycle work.

## Expanded Design Notes

The daemon is now a quality and warm-model optimization, not a prerequisite for the base query path. The implementation therefore has to treat reranking as strictly best-effort. If transport setup, health probing, or scoring fails, the command must keep the heuristic shortlist and continue. That contract is more important than maximizing daemon usage because `context` is a primary discovery tool.

Transport needs to be explicit rather than incidental. The same daemon may be reachable through Unix-socket HTTP for host-managed reads and through shared-file RPC for sandboxed reads. The client should not infer behavior from the environment ad hoc; it should use one transport-neutral scoring interface with two concrete transports and a bounded fallback order.

The scoring window also needs a clear product boundary. The reread problem is already solved by scratchpads, so the daemon’s remaining job is only to rerank the shortlist window presented to the user. The plan should therefore limit scoring to the shortlist-sized candidate window that can materially affect top-rank ordering, rather than rescoring a much larger retrieval set and paying a large first-query penalty for little product value.

Observability remains part of the feature. Status surfaces, failure markers, result-source metadata, and cooldown state are necessary because the transport now differs by execution domain. Without those signals, regressions will look like “context is slow again” or “daemon is healthy but unused” with no bounded seam to inspect.

## Design Slices

### Slice PL-01 - Scoped Trust Fast Path

- Estimate: medium
- Implementation Directive: Refactor scoped `read_code context` requests to classify early, avoid global vector freshness proof by default, skip markdown retrieval when it is irrelevant, and preserve current seam selection for the accepted scoped benchmark corpus.

### Slice PL-02 - Broad Discovery and Conditional Escalation

- Estimate: medium
- Implementation Directive: Rework broad discovery so scoped exact-symbol and file-local reads use scoped trust, while broad reads use session-level trust for healthy cases, preserve markdown-aware behavior questions, and make heavyweight freshness and fallback work conditional on stale, empty, weak, or ambiguous outcomes.
- Ranking Note: regular broad discovery should de-prioritize test-file candidates unless the request is explicitly scoped to tests.

### Slice PL-03 - Benchmark and Regression Coverage

- Estimate: medium
- Implementation Directive: Add validation coverage and benchmark cases for scoped code queries, broad code-plus-markdown discovery, markdown-oriented reads, and stale-trust escalation so latency improvements are measured and correctness regressions are caught.
- Benchmark Corpus: keep the accepted corpus aligned with `tasks.md` across scoped exact-symbol/file-local reads, broad code-plus-markdown discovery, markdown-first reads, and stale-trust escalation cases.
- Validation Expectation: preserve the measured timings in `## Internal Research` and treat `uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file specs/031-speed-up-vector-context/tasks.md --json` as the task-file format check for this benchmark contract.

### Slice PL-04 - Persistent Reranker Transport Boundary

- Estimate: medium
- Implementation Directive: Introduce a transport-neutral reranker client contract and keep daemon lifecycle concerns out of the synchronous `context` path. Support both host-side Unix-socket HTTP and sandbox-safe shared-file RPC behind the same `health -> score -> fallback` call pattern, and cap rerank requests to the shortlist-sized candidate window that can actually change user-visible ordering.

### Slice PL-05 - Daemon Lifecycle, Observability, and Live Proof

- Estimate: medium
- Implementation Directive: Keep the managed daemon startup/status/install logic outside the read path, preserve bounded failure markers and cooldown behavior, and add live verification that a normal `read_code context` query records `rerank_source: daemon` when the daemon is healthy and the active transport is available. Also preserve regression coverage proving heuristic fallback remains safe when daemon transport is blocked or slow.

### Slice PL-06 - Daemon-Backed Semantic Retrieval

- Estimate: large
- Implementation Directive: Extend the existing long-lived read-code daemon so it owns the warm semantic query service in addition to reranking, expose a transport-neutral `query` capability over the same UDS-or-file-RPC boundary, and keep `read_code.py` as the orchestrator for classification, scratchpad/history, and final rendering. The synchronous client path must remain `health -> query -> fallback`, and live verification must prove first-search queries avoid per-request vector-query startup when the daemon is healthy.

### Slice PL-07 - Daemon-Owned Remaining First-Search Startup

- Estimate: large
- Implementation Directive: Move the remaining expensive first-search runtime starts that still occur on the `read_code` side into the existing long-lived daemon instead of creating a second service. That includes warm ownership of the semantic query service, any per-query vector backend initialization still triggered from `read_code.py`, and the metadata needed to prove whether a given first-search result came from daemon-owned startup or local fallback. The synchronous client path must stay minimal: `health -> daemon query -> fallback`, with daemon lifecycle work and heavyweight initialization remaining outside the normal read path.

### Slice PL-08 - MCP-Native Agent Read Surface

- Estimate: large
- Implementation Directive: Stop treating fresh `uv run ... scripts/read_code.py ...` subprocesses as the agent path. Expose bounded `read_code` operations (`context`, `find`, `analyze`, and `window`) directly on the project-local MCP server so the agent can call one persistent in-sandbox process across turns. Reuse the existing `read_code.py` orchestration logic as shared library code where possible, preserve scratchpad/history behavior and first-read `--inline-body` gating, and keep the CLI as a compatibility wrapper rather than the primary warm path. Live verification must prove the platform-owned MCP server keeps the same `pid` and `started_at` across agent turns while returning parity-equivalent read results.

## Plan Completion Summary

Kept the original latency-routing plan intact and migrated the active warm backend path onto the project-local MCP server. That migration is now complete for the in-process `read_code` query and rerank path, and the live proofs pass for:

- direct backend server identity, health, query, and score
- same-process rerank reuse
- same-process semantic query reuse

The remaining open gap is cross-invocation persistence for fresh standalone CLI calls. The current probe commands:

- `uv run --no-sync python scripts/probe_read_code_worker_persistence.py --reset`
- `uv run --no-sync python scripts/probe_read_code_worker_persistence.py`

showed a backend `pid` change from `47366` to `47540` on May 17, 2026, with `same_pid: false` and `same_started_at: false`. So the active path is MCP-backed but still per-invocation for standalone `uv run ... scripts/read_code.py ...` usage. That means the standalone-CLI persistence branch is not the accepted solve for the sandboxed-agent goal. The next accepted phase is `PL-08`: move the agent read surface itself onto the persistent MCP server and treat the CLI as compatibility-only.
