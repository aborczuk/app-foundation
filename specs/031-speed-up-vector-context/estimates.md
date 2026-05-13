# Effort Estimate: speed up vector context

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T000 | 1 | Define the accepted scoped, broad, and markdown benchmark corpus in specs/031-speed-up-vector-context/tasks.md and specs/031-speed-up-vector-context/plan.md | Bounded artifact update that reuses the already collected latency research. |
| T001 | 3 | Introduce early query-scope classification helpers for scoped versus broad `read_code context` requests in scripts/read_code.py — `scripts/read_code.py:read_code_context` | Single-file control-flow change in an established seam with clear downstream consumers. |
| T002 | 3 | Introduce request-scoped trust evaluation and fast-path freshness helpers in scripts/read_code_health.py — `scripts/read_code_health.py:_refresh_indexes_for_read` | One health module seam with existing cache/probe patterns to extend rather than invent. |
| T003 | 3 | Wire the new query-scope and trust helpers into the existing preflight contract in scripts/read_code.py and scripts/read_code_health.py — `scripts/read_code.py:_resolve_pattern_anchor` | Integration task across two known seams with moderate contract pressure but no new subsystem. |
| T004 | 3 | Add scoped fast-path regression coverage for exact-symbol and file-local context reads in tests/unit/test_read_code_shortlist.py and tests/unit/test_read_code_index_refresh.py — `tests/unit/test_read_code_shortlist.py:_query_semantic_anchor_candidate` | Test task spans two focused suites and asserts new routing behavior against existing helper contracts. |
| T005 | 3 | Restrict scoped code queries so irrelevant markdown retrieval is skipped in scripts/read_code.py — `scripts/read_code.py:_query_semantic_anchor_candidate` | Localized retrieval-branch change in one function with straightforward ranking consequences. |
| T006 | 5 | Apply scope-local or session-trusted freshness shortcuts for scoped reads in scripts/read_code_health.py — `scripts/read_code_health.py:vector_refresh_by_state` | Highest-risk logic change because it alters when the expensive vector freshness proof is skipped while preserving safe invalidation semantics. |
| T007 | 3 | Update `read_code context` output and inline behavior to preserve current seam selection while using the scoped fast path in scripts/read_code.py — `scripts/read_code.py:read_code_context` | Moderate user-visible contract work in a single entrypoint after the routing helpers exist. |
| T008 | 3 | Add broad discovery and mixed code-plus-markdown coverage in tests/unit/test_read_code_shortlist.py and tests/integration/test_codebase_vector_index.py — `tests/integration/test_codebase_vector_index.py:test_code_symbol_lookup_returns_metadata` | Focused regression expansion across one unit and one integration suite using existing vector-index coverage patterns. |
| T009 | 5 | Rework broad-query routing so healthy-session trust can satisfy normal discovery reads in scripts/read_code.py and scripts/read_code_health.py — `scripts/read_code.py:_resolve_pattern_anchor` | Cross-file behavior change that must preserve markdown usefulness while introducing conditional trust reuse. |
| T010 | 3 | Make broad fallback and recovery conditional on empty, weak, stale, or conflicting outcomes in scripts/read_code.py — `scripts/read_code.py:_resolve_pattern_anchor` | Medium control-flow refinement in an existing fallback seam with clear trigger conditions from the plan. |
| T011 | 3 | Add stale-trust, invalidation, and escalation observability coverage in tests/unit/test_read_code_index_refresh.py and tests/integration/test_codebase_vector_index_performance.py — `tests/unit/test_read_code_index_refresh.py:_refresh_indexes_for_read` | Test task extends two existing suites that already cover freshness and performance boundaries. |
| T012 | 3 | Implement explicit trust invalidation and escalation-state signaling in scripts/read_code_health.py and scripts/read_code.py — `scripts/read_code_health.py:vector_index_probe` | Medium integration between health state and user-facing read behavior with existing runtime-note mechanisms to reuse. |
| T013 | 2 | Update read-code help text or command documentation to describe the new broad-versus-scoped trust behavior in scripts/read_code.py and specs/031-speed-up-vector-context/plan.md — `scripts/read_code.py:module:docstring` | Small documentation update built on already-settled behavior and benchmark language. |
| T014 | 2 | Capture the post-change benchmark evidence and accepted validation commands in specs/031-speed-up-vector-context/tasks.md and tests/integration/test_codebase_vector_index_performance.py — `tests/integration/test_codebase_vector_index_performance.py:module` | Small closeout task that records measured evidence using existing performance coverage. |

---

### T000 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T001 — Solution Sketch

**Modify**: `scripts/read_code.py:read_code_context` — introduce a scoped-versus-broad classification helper before preflight selection  
**Create**: `scripts/read_code.py:_classify_context_request` or equivalent local helper  
**Reuse**: existing argument parsing and symbol normalization in `scripts/read_code.py`  
**Composition**: parse request, classify shape, then route preflight/retrieval decisions from that classification  
**Failing test assertion**: a path-scoped symbol query is classified as scoped and does not take the broad discovery branch  
**Domains touched**: `code patterns`, `testing`

### T002 — Solution Sketch

**Modify**: `scripts/read_code_health.py:_refresh_indexes_for_read` — allow request-aware trust checks instead of unconditional global proof  
**Create**: local helper(s) for scope-local trust evaluation in `scripts/read_code_health.py`  
**Reuse**: existing session cache, probe cache, and runtime-note helpers in `scripts/read_code_health.py`  
**Composition**: take a classified request, consult session/scope trust first, and escalate to the heavier probe only when required  
**Failing test assertion**: a healthy repeated scoped read reuses trust instead of re-running the heavyweight vector status path  
**Domains touched**: `caching`, `resilience`, `testing`

### T003 — Solution Sketch

**Modify**: `scripts/read_code.py:_resolve_pattern_anchor`, `scripts/read_code_health.py:_refresh_indexes_for_read` — wire the new classification and trust contracts together  
**Create**: none  
**Reuse**: existing anchor resolution flow and vector/codegraph preflight entrypoints  
**Composition**: pass request classification into preflight, then preserve existing resolution behavior after the selected trust path returns  
**Failing test assertion**: the entrypoint returns the same seam as before while using the newly selected scoped or broad trust branch  
**Domains touched**: `code patterns`, `resilience`, `testing`

### T004 — Solution Sketch

**Modify**: `tests/unit/test_read_code_shortlist.py`, `tests/unit/test_read_code_index_refresh.py` — add scoped fast-path assertions  
**Create**: none  
**Reuse**: existing helper-level tests around shortlist selection and read-code preflight behavior  
**Composition**: assert markdown skipping, scoped trust reuse, and unchanged seam selection on exact-symbol and file-local queries  
**Failing test assertion**: a scoped Python-file query no longer invokes irrelevant markdown retrieval while still returning the original candidate  
**Domains touched**: `testing`

### T005 — Solution Sketch

**Modify**: `scripts/read_code.py:_query_semantic_anchor_candidate` — gate code-versus-markdown retrieval by request shape or declared content type  
**Create**: none  
**Reuse**: `_matches_context_content_type` and current candidate ranking helpers  
**Composition**: choose the relevant retrieval scopes before issuing index queries, then preserve current ranking and selection logic  
**Failing test assertion**: a scoped code query only requests code candidates and still returns the expected match  
**Domains touched**: `code patterns`, `testing`

### T006 — Solution Sketch

**Modify**: `scripts/read_code_health.py:vector_refresh_by_state`, `scripts/read_code_health.py:vector_index_probe` — support scope-local or session-trusted fast paths for scoped reads  
**Create**: local trust-state helper(s) and invalidation checks in `scripts/read_code_health.py`  
**Reuse**: existing session ID, probe cache, and stale-drift concepts already present in the health module  
**Composition**: decide whether a scoped request is trusted enough to skip the full probe, fall back to the current heavy status path when trust is unknown or stale, and preserve runtime-note/error behavior  
**Failing test assertion**: a scoped healthy read avoids the heavy status probe, while a stale or changed scope still escalates to the validated path  
**Domains touched**: `caching`, `resilience`, `testing`

### T007 — Solution Sketch

**Modify**: `scripts/read_code.py:read_code_context` — keep compact output and inline-body behavior stable after the scoped fast path is added  
**Create**: none  
**Reuse**: current compact match rendering and inline window logic  
**Composition**: ensure the new routing path returns the same renderable match object and downstream output contract  
**Failing test assertion**: a scoped query with `--inline-body` still prints the same seam window while using the fast path  
**Domains touched**: `code patterns`, `testing`

### T008 — Solution Sketch

**Modify**: `tests/unit/test_read_code_shortlist.py`, `tests/integration/test_codebase_vector_index.py` — add broad and mixed-scope discovery cases  
**Create**: none  
**Reuse**: current vector-index integration tests and shortlist ranking fixtures  
**Composition**: exercise broad natural-language queries that should consult markdown, code, or both, and assert relevant seam selection survives the routing split  
**Failing test assertion**: a broad behavior query still surfaces the expected seam even when scoped fast paths exist  
**Domains touched**: `testing`

### T009 — Solution Sketch

**Modify**: `scripts/read_code.py:_resolve_pattern_anchor`, `scripts/read_code_health.py:_refresh_indexes_for_read` — let healthy session trust satisfy ordinary broad discovery reads  
**Create**: none or a narrow broad-trust helper if needed  
**Reuse**: existing session cache and background codegraph preflight patterns  
**Composition**: classify broad requests, consult session-level trust, run markdown-aware discovery when appropriate, and reserve heavyweight validation for stale or ambiguous cases  
**Failing test assertion**: a healthy broad discovery query returns the relevant seam without blocking on the heavyweight vector status probe every time  
**Domains touched**: `caching`, `resilience`, `testing`

### T010 — Solution Sketch

**Modify**: `scripts/read_code.py:_resolve_pattern_anchor` — trigger fallback/recovery only on explicit failure or ambiguity conditions  
**Create**: none  
**Reuse**: existing fallback notice and codegraph discovery seams  
**Composition**: define a conditional escalation gate around the current recovery path instead of treating recovery work as the default next step  
**Failing test assertion**: a healthy broad query does not run recovery work, while an empty or weak result still escalates  
**Domains touched**: `resilience`, `code patterns`, `testing`

### T011 — Solution Sketch

**Modify**: `tests/unit/test_read_code_index_refresh.py`, `tests/integration/test_codebase_vector_index_performance.py` — add invalidation and observability assertions  
**Create**: none  
**Reuse**: existing refresh and performance benchmark test structure  
**Composition**: verify stale-state invalidation, escalation signaling, and measurable performance improvement on the accepted benchmark corpus  
**Failing test assertion**: stale trust forces the slower path and emits the expected observable signal while healthy trust avoids it  
**Domains touched**: `testing`, `resilience`

### T012 — Solution Sketch

**Modify**: `scripts/read_code_health.py:vector_index_probe`, `scripts/read_code.py:read_code_context` — expose explicit invalidation and escalation-state behavior  
**Create**: none  
**Reuse**: existing runtime note, session cache, and warning emission helpers  
**Composition**: invalidate trusted state when relevant edits occur, carry escalation state forward, and render a stable observable signal when recovery is used  
**Failing test assertion**: after a relevant edit or stale state, the fast path is bypassed and the user can distinguish the escalation path from a normal read  
**Domains touched**: `caching`, `resilience`, `testing`

### T013 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

### T014 — sketch: trivial

[For 1-2 point tasks: no detailed sketch required]

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup (Shared Infrastructure) | 1 | 1 | 0 |
| Phase 2: Foundational (Blocking Prerequisites) | 9 | 3 | 2 |
| Phase 3: User Story 1 - Fast Scoped Context Reads (Priority: P1) 🎯 MVP | 14 | 4 | 1 |
| Phase 4: User Story 2 - Efficient Broad Discovery (Priority: P2) | 11 | 3 | 1 |
| Phase 5: User Story 3 - Clear Freshness Escalation (Priority: P3) | 8 | 3 | 2 |
| Phase 6: Polish & Cross-Cutting Concerns | 2 | 1 | 0 |
| **Total** | **45** | **15** | **6** |

---

## Warnings

- No 8/13-point tasks detected; `/speckit.breakdown` is not required if the final estimate review agrees with these scores.
- The highest-uncertainty tasks are T006 and T009 because they change when trust is reused versus when the heavyweight vector proof still runs.
- Phase 1 and Phase 6 have no parallel opportunities because each contains a single bounded artifact task.
- Async lifecycle guard coverage gaps: none identified for this feature.
- State-safety coverage gaps: verify trust invalidation after relevant local edits while implementing T011 and T012.
- Transaction-integrity coverage gaps: none identified because this feature does not mutate application data stores.
