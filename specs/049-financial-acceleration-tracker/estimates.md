# Effort Estimate: Financial Acceleration Tracker

**Date**: 2026-07-20 | **Total Points**: 252 | **T-shirt Size**: XL (high risk)
**Estimated by**: AI (speckit.estimate) - calibrated from the approved plan slices and current task seams

## Estimate Contract

Each row closes one implementation seam. A score of 5 is one cohesive seam that can be closed out with its focused validation. No current task is scored 8 or 13. The original multi-seam rows were broken down before this estimate was finalized.

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---|---:|---|---|
| T001 | 2 | Create package boundaries and configuration entry points | Single new package seam with no external integration beyond import/config wiring. |
| T002 | 5 | Configure migration, fixture, and real-PostgreSQL test harness conventions | One test/runtime seam, but it crosses migration, fixture, and live database setup. |
| T003 | 5 | Define typed domain entities and persistence mappings | One domain-model seam across the foundation entities; integrates with PostgreSQL mappings. |
| T004 | 5 | Add migrations and foundation constraints | One persistence-integrity seam covering uniqueness, supersession, analysis-run, and work-item constraints. |
| T005 | 5 | Implement CIK/ticker identity resolution and authorization scope primitives | One identity boundary integrating issuer lookup with tenant and portfolio authorization. |
| T006 | 5 | Parse exact-decimal fixtures and write normalized facts/provenance | One ingestion write seam integrating decimal normalization with immutable source records. |
| T007 | 5 | Add ingestion idempotency and audit-event handoff | One transactional retry-safety seam integrating uniqueness checks and structured audit output. |
| T008 | 5 | Implement durable work-item transitions and ownership rules | One state-machine seam integrating legal transitions with coordinator ownership. |
| T009 | 3 | Add real-PostgreSQL identity and provenance tests | Focused integration coverage over existing foundation seams with one live database boundary. |
| T010 | 5 | Add real-PostgreSQL ingestion and work-transition tests | One integration-test seam covering transactional ingestion and durable state behavior. |
| T011 | 3 | Write red fiscal-period and selector tests | Focused fixture test seam with bounded period and amended-filing cases. |
| T012 | 3 | Write red calculation and quality-state tests | Focused numeric fixture test seam for expected values and finite quality outcomes. |
| T013 | 5 | Implement fact selectors and fiscal-period derivation | One calculation-input seam integrating approved selectors with quarter classification. |
| T014 | 5 | Implement revenue, operating income, and margin calculations | One exact-decimal calculation seam over the selected fiscal facts. |
| T015 | 5 | Implement streak, acceleration, and quality-state calculations | One derived-status seam integrating sequential periods with finite quality classification. |
| T016 | 5 | Persist immutable metric observations and provenance | One observation-write seam keyed by source snapshot and calculation version. |
| T017 | 5 | Implement authorized filing-analysis read model and response contract | One read-model seam integrating authorization, observation state, freshness, and provenance. |
| T018 | 5 | Add filing-backed analysis integration test | One end-to-end fixture seam from stored facts through the authorized analysis result. |
| T019 | 3 | Write red metric-expression validation tests | Focused parser/validator test seam for typed expressions, units, unsafe operations, and cycles. |
| T020 | 3 | Write red metric-registry lifecycle tests | Focused persistence test seam for activation, retirement, authorization, and history selection. |
| T021 | 5 | Implement restricted typed metric expression parser and validator | One language-boundary seam integrating AST restrictions, types, units, and dependency checks. |
| T022 | 5 | Implement immutable metric definition/version persistence and authorization | One registry seam integrating version identity, content hash, scope, and tenant authorization. |
| T023 | 5 | Implement metric dry-run validation and reports | One service seam integrating evaluation, dependency resolution, and bounded validation output. |
| T024 | 5 | Implement metric activation and retirement lifecycle | One transactional lifecycle seam preserving historical definition identity. |
| T025 | 5 | Implement dependency-aware targeted recalculation enqueueing | One work-enqueue seam integrating dependency impact analysis with durable recalculation requests. |
| T026 | 5 | Implement versioned historical observation selection | One history-read seam selecting observations by metric version and analysis context. |
| T027 | 5 | Add metric-definition API contract tests | One API contract seam covering validation, authorization, dry run, and version history. |
| T028 | 5 | Write red refresh and duplicate-delivery tests | One integration-test seam covering new, amended, restated, duplicate, and targeted-refresh fixtures. |
| T029 | 5 | Implement SEC discovery adapter request policy | One external-request seam covering User-Agent, timeout, and rate-budget behavior. |
| T030 | 5 | Add SEC retry and circuit-open behavior | One failure-policy seam integrating classified retries, rate limiting, and degraded state. |
| T031 | 5 | Implement amendment detection and targeted refresh | One refresh-orchestration seam connecting filing relationships to affected recalculation work. |
| T032 | 5 | Implement worker leasing and running-state ownership | One coordinator lifecycle seam integrating leases with the legal work-item state machine. |
| T033 | 5 | Implement retry-wait, dead-letter, and lease recovery | One recovery seam covering bounded retries, terminal failure, and expired-worker ownership. |
| T034 | 5 | Add refresh metrics, failure artifacts, and operator guidance | One operational observability seam covering measurable outcomes and bounded diagnostics. |
| T035 | 5 | Add bounded live-SEC compatibility and outage tests | One external compatibility seam covering live fetch and representative failure paths. |
| T036 | 5 | Write red API/export parity and authorization tests | One contract-test seam spanning the shared authorized read model and output boundaries. |
| T037 | 5 | Implement authenticated company, watchlist, and portfolio query endpoints | One authorized query seam over the primary tracked-entity resources. |
| T038 | 5 | Implement authenticated metric-history endpoints and version filters | One history-query seam integrating metric version and provenance filters. |
| T039 | 5 | Implement deterministic XLSX generation and export manifests | One export seam integrating the shared read model with immutable manifest metadata. |
| T040 | 5 | Implement separately authorized Google Sheets delivery | One external-delivery seam with destination and credential scope controls. |
| T041 | 5 | Write red company-history tests | One UI/query contract seam covering gaps, outliers, amendments, and provenance labels. |
| T042 | 5 | Implement company history query with freshness and provenance | One historical read-model seam preserving explicit calculation state. |
| T043 | 5 | Implement server-rendered company detail and trend visualization | One presentation seam consuming the history contract without smoothing gaps or outliers. |
| T044 | 5 | Implement authorized metric-definition API boundary | One API implementation seam covering validation, dry run, lifecycle, authorization, and version selection. |
| T045 | 5 | Implement scheduled discovery registration and feature flags | One scheduler seam covering cadence, trigger ownership, enablement, and safe disablement. |
| T046 | 5 | Implement refresh and delivery observability runtime | One observability seam covering structured events, metrics, correlation, and alert policy. |
| T047 | 5 | Implement authorized watchlist and portfolio lifecycle operations | One universe-management seam covering ownership, membership validation, and mutation authorization. |
| T048 | 5 | Implement dashboard collection read model and rendering states | One dashboard seam covering filters, sorting, pagination, and explicit runtime states. |
| T049 | 5 | Run PostgreSQL foundation and analysis acceptance coverage | One acceptance seam validating the authoritative database path and first user story. |
| T050 | 5 | Run live-SEC refresh, outage, and recovery acceptance coverage | One acceptance seam validating external source continuity and worker recovery. |
| T051 | 5 | Run API, XLSX, and Google Sheets parity acceptance coverage | One delivery acceptance seam validating shared values, status, provenance, and authorization. |
| T052 | 5 | Run metric-definition and version-history acceptance coverage | One metric lifecycle acceptance seam validating reproducibility and historical identity. |
| T053 | 5 | Document migration, rollback, rollout, freshness, and recovery checks | One operational-readiness seam covering release and incident procedures. |

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|---|---:|---:|---:|
| Phase 1: Setup | 7 | 2 | 0 |
| Phase 2: Foundational | 38 | 8 | 0 |
| Phase 3: User Story 1 | 36 | 8 | 2 |
| Phase 4: User Story 2 | 41 | 9 | 2 |
| Phase 5: User Story 3 | 40 | 8 | 1 |
| Phase 6: User Story 4 | 25 | 5 | 1 |
| Phase 7: User Story 5 | 15 | 3 | 1 |
| Phase 8: Polish and Cross-Cutting Validation | 50 | 10 | 2 |
| **Total** | **252** | **53** | **9** |

## Warnings

- No tasks scored 8 or 13 after breakdown.
- High uncertainty remains for the greenfield real-PostgreSQL harness, live SEC compatibility path, and separately authorized Google Sheets delivery; these are bounded by dedicated tasks and acceptance coverage.
- No async lifecycle, state-safety, or transaction-integrity coverage gap was identified in the settled graph; worker recovery, live refresh, and transactional ingestion each have dedicated seams and tests.
