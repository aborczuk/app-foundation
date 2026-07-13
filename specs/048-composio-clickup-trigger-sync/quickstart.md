# Quickstart

## Deterministic Operator Runbook Notes

### Recovery Delta Validation Notes


<!-- speckit_implement_docs:entry_id=T003:runbook -->
- T003 enriched the mcp_clickup projection model and parser with acceptance criteria, story labels, parallel markers, estimate points, and canonical artifact links.


<!-- speckit_implement_docs:entry_id=T004:runbook -->
- T004 extended the ClickUp sync manifest schema with additive feature and task projection metadata while preserving canonical mapping keys and existing manifest version compatibility.


<!-- speckit_implement_docs:entry_id=T005:runbook -->
- T005 inverted the active mcp_clickup runtime path to a transport seam by wiring SyncEngine and the CLI entrypoints through build_transport instead of inline direct-client construction.

## Decision Log

<!-- speckit_implement_docs:entry_id=T003:decision_log -->
- T003: extended Task and SpecArtifact metadata in place and kept sync-engine compatibility by preserving existing workflow_type/context_ref/execution_policy fields while adding richer parser-derived projection fields.

<!-- speckit_implement_docs:entry_id=T004:decision_log -->
- T004: kept the existing manifest key scheme and version stable, adding only feature_projection_meta and task_projection_meta so later drift/reconciliation work can persist richer repo-owned projection state without introducing a second mapping authority.

<!-- speckit_implement_docs:entry_id=T005:decision_log -->
- T005: kept the current direct ClickUp transport as the default implementation behind build_transport, but renamed the engine seam and runtime construction path to transport-oriented abstractions so later Composio transport work can swap in without a sync-engine rewrite.
