## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| A-001 | Readiness | CRITICAL | `spec.md:186-209`; `plan.md:345-355` | The feature exposes browser/API and spreadsheet ingress, but the plan has no explicit external-ingress and runtime-readiness gate covering boundary authentication, readiness checks, degraded behavior, and safe enablement. | Add a dedicated ingress/readiness section with endpoint classes, identity and secret boundaries, health/readiness checks, disabled/degraded behavior, and the evidence required before scheduled refresh or spreadsheet delivery is enabled. |
| A-002 | Governance | HIGH | `plan.md:16-296`; `speckit_plan_gate.py plan-sections` | The plan's strategy JSON does not include the routing contract required by the deterministic plan gate. | Regenerate or amend the plan through the canonical plan workflow so its routing block records the selected domains, risk, and downstream phase routing. |
| A-003 | Governance | HIGH | `specs/049-financial-acceleration-tracker/`; `speckit_plan_gate.py design-artifacts --require-contracts` | Required phase-1 design artifacts `data-model.md` and `quickstart.md` are absent, so the design-artifact gate fails even though the plan contains narrative versions of both topics. | Create the required artifacts from the plan and make them the implementation-facing contracts for schema invariants, local setup, real-PostgreSQL verification, and external integration prerequisites. |
| A-004 | Coverage | HIGH | `spec.md:186`; `tasks.md:26-44,163-166` | FR-001 requires maintaining watchlists and portfolios, but tasks define entities and query access without an explicit authorized create/update/delete seam. | Add a task for authorized watchlist/portfolio lifecycle operations, including ownership, membership validation, and persistence tests. |
| A-005 | Coverage | HIGH | `spec.md:200`; `plan.md:434-438`; `tasks.md:163-166,190-191` | FR-015 promises sortable/filterable dashboard views across companies, watchlists, portfolios, metrics, and quality state, while tasks only name API query endpoints and a company detail page. | Add a dashboard-list/read-model and rendering task that owns filters, sorting, pagination, loading, stale, partial-quality, and recalculation-pending states. |
| A-006 | Ambiguity | MEDIUM | `spec.md:198,232`; `plan.md:351-355,440-444`; `tasks.md:132-138,201-205` | Scheduled SEC refresh is promised, but no task explicitly owns scheduler registration, cadence, feature-flag enforcement, or the boundary between scheduled discovery and manual refresh. | Name the scheduler/trigger seam, configuration and feature-flag owner, cadence contract, and acceptance evidence for the next scheduled processing cycle. |
| A-007 | Coverage | MEDIUM | `plan.md:428-432`; `tasks.md:101-107` | The plan names `src/financial_tracker/api/metric_definitions.py` as a public seam, but the task graph only names metric services and API contract tests; no implementation task owns that endpoint boundary. | Add or explicitly assign a metric-definition API implementation task covering request validation, authorization, dry-run responses, lifecycle operations, and version selection. |
| A-008 | Coverage | MEDIUM | `plan.md:440-444`; `tasks.md:137,201-205` | The plan requires structured observability metrics, logs, and alerts, but the task graph assigns T034 to documentation and refresh metrics without an implementation seam for the observability package or alert delivery. | Add an observability implementation task with event/metric names, correlation fields, alert thresholds, and a verification path; keep T034/T048 focused on the operator runbook. |
| A-009 | Consistency | LOW | `plan.md:416-420`; `tasks.md:37-44` | The plan separates `domain`, `persistence`, and migrations, while T003-T004 place persistence mappings and migrations in `domain/models.py`, leaving the storage seam unclear. | Align task paths with the plan's package boundaries and name the migration location and persistence ownership explicitly before implementation. |

## Coverage Summary Table

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|
| FR-001 | Partial | T003, T005, T017 | Entity/query coverage exists; authorized watchlist/portfolio lifecycle mutation is not explicit. |
| FR-002 | Yes | T005 | Identity resolution is assigned. |
| FR-003 | Yes | T029, T031 | Discovery and amendment refresh are assigned. |
| FR-004 | Yes | T003, T006, T016 | Filing provenance and immutable observations are assigned. |
| FR-005 | Yes | T006, T013, T014, T021 | Fact ingestion, selectors, calculations, and approved metric inputs are assigned. |
| FR-006 | Yes | T013 | Fiscal-period classification is assigned. |
| FR-007 | Yes | T013 | Standalone-quarter derivation is assigned. |
| FR-008 | Yes | T013, T014 | Revenue and operating-income selectors are assigned. |
| FR-009 | Yes | T014 | Margin calculation is assigned. |
| FR-010 | Yes | T015 | Improvement streak calculation is assigned. |
| FR-011 | Yes | T015 | Acceleration and materiality thresholds are assigned. |
| FR-012 | Yes | T015, T016 | Quality-state calculation and observation persistence are assigned. |
| FR-013 | Yes | T025, T031 | Targeted recalculation and refresh orchestration are assigned. |
| FR-014 | Yes | T016, T026 | Immutable and versioned historical observations are assigned. |
| FR-015 | Partial | T037, T038, T043 | API/detail coverage exists; the sortable/filterable dashboard collection is not explicit. |
| FR-016 | Yes | T042, T043 | Company history query and rendering are assigned. |
| FR-017 | Yes | T037, T038 | Authorized query endpoints are assigned. |
| FR-018 | Yes | T039 | Deterministic XLSX export is assigned. |
| FR-019 | Yes | T040 | Authorized Google Sheets delivery is assigned. |
| FR-020 | Yes | T005, T022, T037, T040 | Authorization seams are distributed across identity, registry, API, and export work. |
| FR-021 | Yes | T030, T034, T035, T048 | Bounded failure handling and operational evidence are assigned. |
| FR-022 | Yes | T021 | Restricted declarative metric language is assigned. |
| FR-023 | Yes | T022, T023, T024 | Validation, versioning, and lifecycle are assigned. |
| FR-024 | Yes | T025, T026 | Version-pinned observations and recalculation are assigned. |

## Constitution Alignment Issues

- The intended architecture identifies trust boundaries and secret isolation in `plan.md:345-380`, which aligns with Constitution I-a through I-f. The missing explicit ingress/readiness gate in A-001 prevents that alignment from being operationally verifiable before external surfaces are enabled.
- The plan includes real-PostgreSQL and live-SEC verification in `plan.md:408-444` and `tasks.md:201-205`, which aligns with the test-driven verification requirement. The missing design artifacts in A-003 still block a complete deterministic entry contract.

## Unmapped Tasks

No task is wholly unmapped to the feature. T001-T002 and T044-T048 are cross-cutting setup and acceptance tasks; A-004 through A-008 identify seams that are promised by the spec or plan but are only partially represented in the current task graph.

## Metrics

- Total Requirements: 24 functional requirements
- Total Tasks: 48 tasks
- Coverage: 91.7% direct task coverage; 2 requirements are partial
- Ambiguity Count: 3
- Duplication Count: 0
- Critical Issues Count: 1
- High Issues Count: 4

## Next Actions

1. Resolve A-001 through A-003 before implementation entry: add the readiness/routing contracts and required design artifacts, then rerun the deterministic plan gates.
2. Resolve A-004 and A-005 in tasking so watchlist/portfolio lifecycle and dashboard collection behavior are owned by explicit seams.
3. Resolve A-006 through A-009 during the next tasking/estimate cycle; keep the estimate/breakdown loop focused on seam ownership rather than creating implementation fragments.
4. Do not register or synchronize ClickUp tasks as part of analyze. External task publication remains a separate agent-owned integration step.
