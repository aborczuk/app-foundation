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
