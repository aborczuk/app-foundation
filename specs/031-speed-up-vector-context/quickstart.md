# Quickstart

## Deterministic Operator Runbook Notes

### Recovery Delta Validation Notes


<!-- speckit_implement_docs:entry_id=T000:runbook -->
- Locked the accepted scoped, broad, markdown, and escalation benchmark corpus in tasks.md so later routing changes validate against a stable contract.


<!-- speckit_implement_docs:entry_id=T001:runbook -->
- Added early scoped-versus-broad context classification in read_code.py before refresh and anchor resolution, with context routing tests guarding call order.


<!-- speckit_implement_docs:entry_id=T002:runbook -->
- T002 introduced request-scoped trust evaluation so read preflight can reuse trusted scoped vector state before the heavyweight refresh path, while preserving the existing hard failure for missing or probe-failed vector states.

## Decision Log

<!-- speckit_implement_docs:entry_id=T000:decision_log -->
- T000 locked the benchmark corpus and validation expectations in tasks.md and plan.md without changing routing logic or the measured baseline timings.

<!-- speckit_implement_docs:entry_id=T001:decision_log -->
- T001 introduced a local scope-classification contract for read_code_context and threaded it forward without changing visible context output yet.

<!-- speckit_implement_docs:entry_id=T002:decision_log -->
- T002: added a scoped vector trust helper in scripts/read_code_health.py and threaded request scope from scripts/read_code.py so read preflight can bypass the global status probe for trusted scoped reads; broad and failure paths remain on the existing hard-gate contract.
