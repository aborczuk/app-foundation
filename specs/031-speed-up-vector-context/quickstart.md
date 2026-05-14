# Quickstart

## Deterministic Operator Runbook Notes

### Recovery Delta Validation Notes


<!-- speckit_implement_docs:entry_id=T000:runbook -->
- Locked the accepted scoped, broad, markdown, and escalation benchmark corpus in tasks.md so later routing changes validate against a stable contract.


<!-- speckit_implement_docs:entry_id=T001:runbook -->
- Added early scoped-versus-broad context classification in read_code.py before refresh and anchor resolution, with context routing tests guarding call order.


<!-- speckit_implement_docs:entry_id=T002:runbook -->
- T002 introduced request-scoped trust evaluation so read preflight can reuse trusted scoped vector state before the heavyweight refresh path, while preserving the existing hard failure for missing or probe-failed vector states.


<!-- speckit_implement_docs:entry_id=T003:runbook -->
- T003 threaded the explicit request-scope decision through read_code context preflight and anchor resolution, so later tasks can branch trust and retrieval behavior without reclassifying the request.


<!-- speckit_implement_docs:entry_id=T004:runbook -->
- T004 added unit regression coverage for exact-symbol and file-local scoped reads, including scoped trust routing assertions in the shortlist and index-refresh test modules.


<!-- speckit_implement_docs:entry_id=T005:runbook -->
- T005 taught scoped non-markdown context queries to skip the markdown candidate branch while preserving mixed code-plus-markdown retrieval for broad and markdown-oriented requests.


<!-- speckit_implement_docs:entry_id=T006:runbook -->
- T006 let scoped reads reuse trusted freshness in vector_refresh_by_state so narrow requests can bypass the global probe while stale, broad, and failure states still use the existing escalation path.


<!-- speckit_implement_docs:entry_id=T007:runbook -->
- T007 stabilized the visible read_code context path by preserving compact output and inline-body rendering while the scoped fast path now runs underneath it.


<!-- speckit_implement_docs:entry_id=T008:runbook -->
- T008 added broad-discovery regression coverage so mixed code-plus-markdown queries and the offline vector index both preserve markdown-aware behavior before the broad-routing changes land.


<!-- speckit_implement_docs:entry_id=T009:runbook -->
- T009 let healthy broad discovery reads stay on the trusted mixed retrieval path by default, while preserving escalation for exceptional outcomes and keeping markdown-aware behavior intact.


<!-- speckit_implement_docs:entry_id=T010:runbook -->
- T010 made broad-read fallback explicit so recovery now runs only for empty, weak, stale, or conflicting outcomes while satisfactory broad results return directly.


<!-- speckit_implement_docs:entry_id=T011:runbook -->
- T011 added stale-trust, invalidation, and escalation regression coverage in both the unit refresh suite and the vector-index performance harness before the explicit signaling work lands.


<!-- speckit_implement_docs:entry_id=T012:runbook -->
- T012 made trust invalidation and escalation state explicit through probe labels, runtime-note propagation, and bounded fallback notices so maintainers can tell when fast-path trust was reused versus escalated.


<!-- speckit_implement_docs:entry_id=T013:runbook -->
- T013 documented the settled scoped-versus-broad trust policy in read_code help text and the feature plan so maintainers can tell when markdown-aware broad discovery or escalation still applies.

## Decision Log

<!-- speckit_implement_docs:entry_id=T000:decision_log -->
- T000 locked the benchmark corpus and validation expectations in tasks.md and plan.md without changing routing logic or the measured baseline timings.

<!-- speckit_implement_docs:entry_id=T001:decision_log -->
- T001 introduced a local scope-classification contract for read_code_context and threaded it forward without changing visible context output yet.

<!-- speckit_implement_docs:entry_id=T002:decision_log -->
- T002: added a scoped vector trust helper in scripts/read_code_health.py and threaded request scope from scripts/read_code.py so read preflight can bypass the global status probe for trusted scoped reads; broad and failure paths remain on the existing hard-gate contract.

<!-- speckit_implement_docs:entry_id=T003:decision_log -->
- T003: wired the request scope from read_code_context into _resolve_pattern_anchor and downstream semantic anchor lookup so scoped versus broad routing now shares one explicit internal contract without changing the CLI surface.

<!-- speckit_implement_docs:entry_id=T004:decision_log -->
- T004: locked in the scoped fast-path regression harness in tests/unit/test_read_code_shortlist.py and tests/unit/test_read_code_index_refresh.py so later scoped retrieval and trust changes have explicit unit guards before behavior shifts.

<!-- speckit_implement_docs:entry_id=T005:decision_log -->
- T005: narrowed _query_semantic_anchor_candidate to conditionally skip markdown retrieval for scoped code queries using the routed scope signal, while keeping the mixed candidate path for broad discovery intact.

<!-- speckit_implement_docs:entry_id=T006:decision_log -->
- T006: applied the T002 trust contract inside vector_refresh_by_state so trusted scoped reads return early before vector_index_probe(REPO_ROOT), while broad and stale flows continue through the existing dispatch logic.

<!-- speckit_implement_docs:entry_id=T007:decision_log -->
- T007: extracted the inline-body rendering branch in read_code_context so the scoped fast-path changes keep the same visible seam selection and window behavior for accepted scoped queries.

<!-- speckit_implement_docs:entry_id=T008:decision_log -->
- T008: expanded unit and integration regression coverage for broad discovery, including code-scope plus markdown-scope retrieval in the offline index harness and a broad markdown-aware shortlist case.

<!-- speckit_implement_docs:entry_id=T009:decision_log -->
- T009: routed the healthy broad-read happy path through trusted mixed retrieval in _resolve_pattern_anchor so ordinary broad discovery avoids unnecessary escalation while keeping the code-plus-markdown candidate path.

<!-- speckit_implement_docs:entry_id=T010:decision_log -->
- T010: added explicit broad-outcome evaluation around _resolve_pattern_anchor so codegraph recovery is reserved for bad broad results instead of being an implicit default path.

<!-- speckit_implement_docs:entry_id=T011:decision_log -->
- T011: locked in stale/invalidation coverage for the trust helpers and refresh path, plus an integration invalidation regression in the vector-index performance suite so later signaling changes stay observable.

<!-- speckit_implement_docs:entry_id=T012:decision_log -->
- T012: surfaced explicit trust and escalation state in the health contract and existing notice channels without changing the compact read_code context result payload.

<!-- speckit_implement_docs:entry_id=T013:decision_log -->
- T013: aligned the local read_code help text and feature plan with the implemented routing contract for scoped trust reuse, mixed broad discovery, and conditional escalation.
