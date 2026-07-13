# Quickstart

## Deterministic Operator Runbook Notes

### Recovery Delta Validation Notes


<!-- speckit_implement_docs:entry_id=T003:runbook -->
- T003 enriched the mcp_clickup projection model and parser with acceptance criteria, story labels, parallel markers, estimate points, and canonical artifact links.


<!-- speckit_implement_docs:entry_id=T004:runbook -->
- T004 extended the ClickUp sync manifest schema with additive feature and task projection metadata while preserving canonical mapping keys and existing manifest version compatibility.


<!-- speckit_implement_docs:entry_id=T005:runbook -->
- T005 inverted the active mcp_clickup runtime path to a transport seam by wiring SyncEngine and the CLI entrypoints through build_transport instead of inline direct-client construction.


<!-- speckit_implement_docs:entry_id=T006:runbook -->
- T006 exposed non-mutating explicit task-start eligibility helpers in the task ledger and implement-step layers so future ClickUp-triggered requests can query repo startability without mutating ledger state.


<!-- speckit_implement_docs:entry_id=T007:runbook -->
- T007 added regression coverage for parser acceptance fallback and manifest round-trip/default handling so the enriched projection metadata stays stable across both discovery and persistence paths.


<!-- speckit_implement_docs:entry_id=T008:runbook -->
- T008 tightened sync-engine idempotence coverage and broadened Composio adapter scaffold coverage so reruns stay non-duplicating and transport contract failures remain explicit per operation.


<!-- speckit_implement_docs:entry_id=T009:runbook -->
- T009 introduced canonical FeatureProjection and TaskProjection models plus projection builders so stabilized repo artifacts now emit one repo-owned feature projection and task set before mapping or transport work begins.

## Decision Log

<!-- speckit_implement_docs:entry_id=T003:decision_log -->
- T003: extended Task and SpecArtifact metadata in place and kept sync-engine compatibility by preserving existing workflow_type/context_ref/execution_policy fields while adding richer parser-derived projection fields.

<!-- speckit_implement_docs:entry_id=T004:decision_log -->
- T004: kept the existing manifest key scheme and version stable, adding only feature_projection_meta and task_projection_meta so later drift/reconciliation work can persist richer repo-owned projection state without introducing a second mapping authority.

<!-- speckit_implement_docs:entry_id=T005:decision_log -->
- T005: kept the current direct ClickUp transport as the default implementation behind build_transport, but renamed the engine seam and runtime construction path to transport-oriented abstractions so later Composio transport work can swap in without a sync-engine rewrite.

<!-- speckit_implement_docs:entry_id=T006:decision_log -->
- T006: separated explicit task gate evaluation from task start mutation by adding pure helper surfaces in task_ledger.py and speckit_implement_step.py, so later trigger work can reuse the existing ledger rules without cloning or bypassing them.

<!-- speckit_implement_docs:entry_id=T007:decision_log -->
- T007: covered the remaining projection-regression gaps by testing the parser's Independent Test fallback branch and the manifest's additive metadata preservation/defaulting behavior instead of broadening runtime logic.

<!-- speckit_implement_docs:entry_id=T008:decision_log -->
- T008: pinned the current transport seam with strict non-duplication assertions in sync_engine and operation-specific scaffold errors in the Composio adapter tests before later runtime wiring tasks land.

<!-- speckit_implement_docs:entry_id=T009:decision_log -->
- T009: split raw artifact parsing from canonical projection extraction by adding explicit projection dataclasses and builders, so later mapping and Composio transport tasks can consume a stable repo-owned contract instead of re-deriving metadata ad hoc.
