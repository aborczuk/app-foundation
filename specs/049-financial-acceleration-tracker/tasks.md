---

description: "Seam-sized implementation tasks for the financial acceleration tracker"
---

# Tasks: financial acceleration tracker

**Input**: Approved design documents from `specs/049-financial-acceleration-tracker/`
**Prerequisites**: `plan.md`, `spec.md`, and `spec.json`

**Tasking contract**: Tasks are implementation seams between the approved plan slices and the implement phase. A task closes one coherent file/dependency seam; routing, validation, and reporting stay together when they share the same closeout boundary. Estimate 5 as one cohesive seam. Estimate 8 or 13 as multi-seam work that must return through breakdown before implementation.

**Task format**: `- [ ] T0NN [P?] [USn?] <action> in <exact path>`

**Implementation stack boundary**: Backend, ingestion, persistence, and analysis code default to Python. Browser-facing seams may use JavaScript or TypeScript and the adopted frontend libraries from `spec.md`, including TanStack Table for sortable/filterable collections and Recharts for metric-history visualizations. SEC seams may use EdgarTools, export seams may use XlsxWriter or gspread, and Arelle remains validation/failure fallback-only. `xang1234/stock-screener` is reusable app-shell pattern input rather than a runtime dependency; adapt only verified patterns and remove unlicensed market-data assumptions. Do not rewrite a browser seam into Python solely to satisfy the backend default; declare the selected package and verify its behavior in the seam's tests.

## Path Conventions

- Python package: `src/financial_tracker/`
- Unit and contract tests: `tests/financial_tracker/`
- Integration tests: `tests/integration/financial_tracker/`
- Operations documentation: `docs/financial-tracker-operations.md`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the isolated Python package and test/runtime configuration required by every design slice.

- [X] T001 Create the financial tracker package boundaries and configuration entry points in `src/financial_tracker/__init__.py`
- [X] T002 Configure migration, fixture, and real-PostgreSQL test harness conventions in `tests/financial_tracker/conftest.py`

**Checkpoint**: The package imports and the real-PostgreSQL test harness can start without application behavior.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement design slice PL-01, Financial Foundation and Provenance. No user-story task can start before these seams are stable.

- [X] T003 Define typed domain entities for users, portfolios, issuers, filings, fiscal periods, facts, and provenance with mappings owned by `src/financial_tracker/persistence/models.py`
- [X] T004 Add migrations and uniqueness, supersession, analysis-run, and work-item constraints in `src/financial_tracker/persistence/migrations/`
- [X] T005 Implement CIK/ticker identity resolution and authorization scope primitives in `src/financial_tracker/identity/resolver.py`
- [X] T006 Implement exact-decimal fixture parsing and normalized fact/provenance writes in `src/financial_tracker/ingestion/fixtures.py`
- [X] T007 Add transactional idempotency and structured audit-event handoff in `src/financial_tracker/ingestion/fixtures.py`
- [X] T008 Implement durable work-item state transitions and coordinator ownership rules in `src/financial_tracker/work/state.py`
- [X] T009 Add real-PostgreSQL identity and provenance tests in `tests/integration/financial_tracker/test_foundation.py`
- [ ] T010 Add real-PostgreSQL idempotent-ingestion and work-transition tests in `tests/integration/financial_tracker/test_foundation.py`

**Checkpoint**: PL-01 is independently verifiable with fixture input, immutable provenance, authorization scope, and durable retry-safe work state.

---

## Phase 3: User Story 1 - Identify Filing-Backed Acceleration (Priority: P1)

**Goal**: Deliver the first trusted filing-backed acceleration result for a company universe, including quarter alignment, quality state, and accession provenance.

**Independent Test**: Run the analysis against fixed filing fixtures in PostgreSQL and verify revenue, operating income, margin, streak, acceleration status, unavailable-period reasons, and source accession provenance.

### Acceptance Criteria

- Quarterly values are derived only when fiscal-period evidence supports the derivation.
- Built-in metric observations are immutable and keyed by source snapshot and calculation version.
- Incomplete, ambiguous, stale, superseded, and failed states are visible rather than collapsed to null.
- The result contract exposes metric values, quality state, freshness, and accession provenance.

### Tests for User Story 1

- [ ] T011 [P] [US1] Write red fixture tests for fiscal-period derivation, selectors, and amended filing behavior in `tests/financial_tracker/calculation/test_periods.py`
- [ ] T012 [P] [US1] Write red fixture tests for exact-decimal margin, streak, acceleration, and finite quality states in `tests/financial_tracker/calculation/test_acceleration.py`

### Implementation for User Story 1

- [ ] T013 [US1] Implement approved fact selectors and fiscal-period classification/derivation in `src/financial_tracker/selectors/periods.py`
- [ ] T014 [US1] Implement built-in exact-decimal revenue, operating income, and margin calculations in `src/financial_tracker/calculation/acceleration.py`
- [ ] T015 [US1] Implement streak, acceleration classification, and finite quality-state calculations in `src/financial_tracker/calculation/acceleration.py`
- [ ] T016 [US1] Persist immutable metric observations with source snapshot, calculation version, and complete provenance in `src/financial_tracker/calculation/observations.py`
- [ ] T017 [US1] Implement the authorized filing-analysis read model and response contract in `src/financial_tracker/query/analysis.py`
- [ ] T018 [US1] Add the filing-backed analysis integration test against real PostgreSQL fixtures in `tests/integration/financial_tracker/test_analysis.py`

**Checkpoint**: US1 is independently demonstrable from fixture ingestion through a provenance-complete acceleration result.

---

## Phase 4: User Story 2 - Define Trackable Metrics (Priority: P2)

**Goal**: Let an authorized analyst define additional filing-backed metrics over time while preserving immutable definition versions and historical observations.

**Independent Test**: Define a metric from approved facts and existing metrics, dry-run it across fixed quarters, activate a new version, and verify that prior observations retain their original version and provenance.

### Acceptance Criteria

- Only the restricted typed expression language and approved selectors are accepted.
- Definitions are authorized, versioned, content-hashed, and isolated by tenant and portfolio scope.
- Dry runs expose resolved inputs, dependency graph, result or bounded validation errors, and the version to be activated.
- Activation, retirement, and targeted recalculation preserve historical version identity.

### Tests for User Story 2

- [ ] T019 [P] [US2] Write red tests for expression parsing, unit checks, unsafe operations, and dependency cycles in `tests/financial_tracker/metrics/test_expression.py`
- [ ] T020 [P] [US2] Write red tests for version activation, retirement, authorization, and historical observation selection in `tests/financial_tracker/metrics/test_registry.py`

### Implementation for User Story 2

- [ ] T021 [US2] Implement the restricted typed metric expression parser and validator in `src/financial_tracker/metrics/expression.py`
- [ ] T022 [US2] Implement immutable metric definition/version persistence and scope authorization in `src/financial_tracker/metrics/registry.py`
- [ ] T023 [US2] Implement metric dry-run validation and bounded validation-report orchestration in `src/financial_tracker/metrics/service.py`
- [ ] T024 [US2] Implement metric activation and retirement lifecycle orchestration in `src/financial_tracker/metrics/service.py`
- [ ] T025 [US2] Implement dependency-aware targeted recalculation enqueueing in `src/financial_tracker/recalculation/metric_runs.py`
- [ ] T026 [US2] Implement versioned historical observation selection in `src/financial_tracker/recalculation/metric_runs.py`
- [ ] T027 [US2] Add metric-definition API contract tests for validation, authorization, dry run, and version history in `tests/financial_tracker/metrics/test_api.py`

**Checkpoint**: US2 is independently demonstrable with a user-authored metric definition that can evolve without rewriting history.

---

## Phase 5: User Story 3 - Refresh Watchlists and Portfolios from New Filings (Priority: P2)

**Goal**: Refresh affected tracked companies from new filings, amendments, and restatements while preserving prior observations and visible failure state.

**Independent Test**: Deliver new, amended, malformed, duplicate, and rate-limited filing fixtures and verify targeted refresh, unchanged history, bounded quality states, and retry-safe work recovery.

### Acceptance Criteria

- New filings and amendments trigger only affected metric recalculation.
- Prior observations remain queryable with original provenance and freshness metadata.
- Missing, ambiguous, invalid, and zero-denominator inputs produce explicit quality states.
- SEC failures, duplicate delivery, queue recovery, and export retry remain observable and bounded.

### Tests for User Story 3

- [ ] T028 [P] [US3] Write red refresh tests for new filings, amendments, restatements, duplicate delivery, and targeted recalculation in `tests/integration/financial_tracker/test_refresh.py`

### Implementation for User Story 3

- [ ] T029 [US3] Implement the SEC filing discovery adapter with a reviewed EdgarTools integration seam, direct SEC transport, User-Agent, timeout, and rate-budget policy in `src/financial_tracker/sec/adapter.py`
- [ ] T030 [US3] Add classified retry and circuit-open behavior around the direct and EdgarTools SEC adapter paths in `src/financial_tracker/sec/adapter.py`
- [ ] T031 [US3] Implement amendment detection and targeted refresh orchestration in `src/financial_tracker/sec/refresh.py`
- [ ] T032 [US3] Implement worker leasing and coordinator-owned running state in `src/financial_tracker/work/coordinator.py`
- [ ] T033 [US3] Implement retry-wait, dead-letter, and expired-lease recovery in `src/financial_tracker/work/coordinator.py`
- [ ] T034 [US3] Add refresh metrics, structured failure artifacts, and operator continuity guidance in `docs/financial-tracker-operations.md`
- [ ] T035 [US3] Add bounded live-SEC compatibility and outage-path integration tests for direct SEC and EdgarTools extraction, keeping Arelle validation fallback-only, in `tests/integration/financial_tracker/test_live_sec.py`

**Checkpoint**: US3 is independently demonstrable with safe refresh, amendment history, retry recovery, and operator-visible degradation.

---

## Phase 6: User Story 4 - Export and Integrate Results (Priority: P3)

**Goal**: Deliver one authorized read contract to browser users, API clients, XLSX, and the separately tested Google Sheets adapter.

**Independent Test**: Filter a known result set and verify that API, XLSX, and Google Sheets outputs contain matching values, quality states, filters, provenance, schema version, and source identifiers.

### Acceptance Criteria

- Dashboard and API responses use the same authorized read model and expose stale or recalculation-pending state.
- XLSX exports are deterministic and include filters, provenance, source identifiers, schema version, and content hash.
- Google Sheets delivery is an explicit adapter and never broadens credential or destination scope.
- Unauthorized portfolio/company access is rejected without financial-result leakage.

### Tests for User Story 4

- [ ] T036 [P] [US4] Write red API/export parity and authorization tests in `tests/financial_tracker/api/test_exports.py`

### Implementation for User Story 4

- [ ] T037 [US4] Implement authenticated company, watchlist, and portfolio query endpoints in `src/financial_tracker/api/queries.py`
- [ ] T038 [US4] Implement authenticated metric-history query endpoints and version filters in `src/financial_tracker/api/queries.py`
- [ ] T039 [US4] Implement deterministic XLSX generation with XlsxWriter and immutable export manifests in `src/financial_tracker/exports/xlsx.py`
- [ ] T040 [US4] Implement the separately authorized Google Sheets delivery adapter with gspread in `src/financial_tracker/exports/google_sheets.py`

**Checkpoint**: US4 is independently demonstrable with parity across dashboard/API/export read contracts and authorization boundaries.

---

## Phase 7: User Story 5 - Inspect Company-Level Trend History (Priority: P4)

**Goal**: Let an analyst inspect quarter-aligned company history without smoothing away gaps, outliers, amendments, or calculation status.

**Independent Test**: Load a company fixture with complete, missing, invalid, outlier, and restated quarters and verify the detail view and sparkline preserve each distinction.

### Acceptance Criteria

- Company history includes quarter labels, metric-definition version, filing accessions, amendment/restatement status, and calculation status.
- Missing and invalid quarters remain explicit gaps.
- Outliers remain marked and are not smoothed or interpolated.

### Tests for User Story 5

- [ ] T041 [P] [US5] Write red company-history tests for gaps, outliers, amendments, and provenance labels in `tests/financial_tracker/web/test_company_history.py`

### Implementation for User Story 5

- [ ] T042 [US5] Implement the company history query with freshness and provenance state in `src/financial_tracker/query/company_history.py`
- [ ] T043 [US5] Implement the company detail and trend visualization, using Recharts where the browser surface requires it, while preserving gaps and outliers in `src/financial_tracker/web/company_history.py`

**Checkpoint**: US5 is independently demonstrable from historical query through trustworthy company detail rendering.

---

## Phase 8: Polish and Cross-Cutting Validation

**Purpose**: Close the remaining cross-cutting implementation seams, then verify the complete slice-to-task contract.

### Remediation Seams

- [ ] T044 [US2] Implement the authorized metric-definition API boundary for validation, dry run, lifecycle, and version selection in `src/financial_tracker/api/metric_definitions.py`
- [ ] T045 [US3] Implement scheduled discovery registration, cadence, and feature-flag enforcement in `src/financial_tracker/work/scheduler.py`
- [ ] T046 [US3] Implement refresh and delivery observability events, metrics, correlation fields, and alert policy in `src/financial_tracker/observability/runtime.py`
- [ ] T047 [US4] Implement authorized watchlist and portfolio lifecycle operations with membership validation in `src/financial_tracker/api/universes.py`
- [ ] T048 [US4] Implement the sortable and filterable dashboard collection read model and server-rendered states, using TanStack Table and Recharts where the browser surface requires them, in `src/financial_tracker/web/dashboard.py`

### Acceptance and Rollout

- [ ] T049 Run real-PostgreSQL foundation and analysis acceptance coverage in `tests/financial_tracker/test_feature_acceptance.py`
- [ ] T050 Run live-SEC refresh, outage, and recovery acceptance coverage in `tests/financial_tracker/test_feature_acceptance.py`
- [ ] T051 Run API, XLSX, and Google Sheets parity acceptance coverage in `tests/financial_tracker/test_feature_acceptance.py`
- [ ] T052 Run metric-definition and version-history acceptance coverage in `tests/financial_tracker/test_feature_acceptance.py`
- [ ] T053 Document migration, rollback, feature-flag rollout, freshness states, and operator recovery checks in `docs/financial-tracker-operations.md`

**Checkpoint**: All required red/green acceptance evidence is recorded, operational docs are usable, and no task remains a placeholder.

## Dependencies and Execution Order

### Phase Dependencies

1. Phase 1 establishes the package and test harness.
2. Phase 2 implements PL-01 and blocks all user stories.
3. Phase 3 implements PL-02 and delivers the P1 MVP.
4. Phase 4 implements PL-03 and depends on the PL-02 observation contract.
5. Phase 5 implements PL-05 refresh behavior and depends on PL-01, PL-02, and PL-03 version selection.
6. Phase 6 implements PL-04 delivery and depends on the authorized read model from Phases 3-5.
7. Phase 7 consumes the same read model and may proceed after Phase 3, with metric-version and refresh states from Phases 4-5.
8. Phase 8 first closes the five remediation seams, then runs cross-cutting acceptance and rollout checks.

### Parallel Opportunities

- T011 and T012 can run in parallel before the US1 implementation seams.
- T019 and T020 can run in parallel before the US2 implementation seams.
- T036 and T041 can run in parallel after the shared read model is available.
- T047 and T048 can run in parallel after the authorized read model and identity boundaries are stable.

## Plan Design Slice Index

| Plan slice | Task range | Closed seams |
|---|---|---|
| PL-01 Financial Foundation and Provenance | T001-T010 | Package, domain persistence, identity, fixture ingestion, authorization, work state, and PostgreSQL evidence |
| PL-02 Calculation and Built-In Metric Observations | T011-T018 | Selectors, fiscal periods, calculations, quality states, immutable observations, and analysis read model |
| PL-03 Versioned User-Defined Metric Registry | T019-T027, T044 | Restricted parser, validation, version persistence, authorization, dry run, lifecycle, recalculation, and API boundary |
| PL-05 SEC Refresh, Operations, and Continuity | T028-T035, T045-T046 | SEC adapter, scheduled discovery, amendment refresh, worker recovery, observability, runbook, and bounded live compatibility |
| PL-04 Authorized Dashboard, API, and Deterministic Exports | T036-T040, T047-T048 | Universe lifecycle, authorized query contract, dashboard collection, XLSX manifest, Google Sheets adapter, and parity tests |
| Company-level history contract | T041-T043 | Historical query and visualization for gaps, outliers, amendments, and provenance |
| Cross-cutting acceptance and rollout | T049-T053 | Real-backend acceptance evidence and operational readiness documentation |
