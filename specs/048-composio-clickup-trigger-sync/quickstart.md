# Quickstart

## Deterministic Operator Runbook Notes

### Recovery Delta Validation Notes


<!-- speckit_implement_docs:entry_id=T003:runbook -->
- T003 enriched the mcp_clickup projection model and parser with acceptance criteria, story labels, parallel markers, estimate points, and canonical artifact links.


<!-- speckit_implement_docs:entry_id=T004:runbook -->
- T004 extended the ClickUp sync manifest schema with additive feature and task projection metadata while preserving canonical mapping keys and existing manifest version compatibility.

## Decision Log

<!-- speckit_implement_docs:entry_id=T003:decision_log -->
- T003: extended Task and SpecArtifact metadata in place and kept sync-engine compatibility by preserving existing workflow_type/context_ref/execution_policy fields while adding richer parser-derived projection fields.

<!-- speckit_implement_docs:entry_id=T004:decision_log -->
- T004: kept the existing manifest key scheme and version stable, adding only feature_projection_meta and task_projection_meta so later drift/reconciliation work can persist richer repo-owned projection state without introducing a second mapping authority.
