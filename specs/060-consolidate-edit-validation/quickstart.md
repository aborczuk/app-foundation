# Quickstart

## Deterministic Operator Runbook Notes

### Recovery Delta Validation Notes


<!-- speckit_implement_docs:entry_id=060-T001-T016:runbook -->
- Delivered Feature 060 (T001-T016): non-blocking PostToolUse edit tracking, unified unskippable edit_code validate/sync with evidence reuse, on-demand authoritative-read freshness, evidence-aware git hooks, healthy-skip bootstrap_session with failure aggregation, and repo-local CGC/HOME isolation. Verified with 117 passing unit+live tests.

## Decision Log

<!-- speckit_implement_docs:entry_id=060-T001-T016:decision_log -->
- Consolidated edit validation and discovery freshness under scripts/workflow_evidence.py (.codegraphcontext/workflow-state/); removed sync skip bypasses; isolated CodeGraph/discovery subprocess HOME/XDG_* inside .codegraphcontext/; dropped benchmarking to feature 062.
