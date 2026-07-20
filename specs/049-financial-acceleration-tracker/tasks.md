---

description: "Seam-sized implementation tasks for the financial acceleration tracker"
---

# Tasks: financial acceleration tracker

**Input**: Approved design documents from `specs/049-financial-acceleration-tracker/`
**Prerequisites**: `plan.md`, `spec.md`, and `spec.json`

**Tasking contract**: Tasks are implementation seams between the approved plan slices and the implement phase. A task closes one coherent file/dependency seam; routing, validation, and reporting stay together when they share the same closeout boundary. Estimate 5 as one cohesive seam. Estimate 8 or 13 as multi-seam work that must return through breakdown before implementation.

**Task format**: `- [ ] T0NN [P?] [USn?] <action> in <exact path>`

## Path Conventions

- Python package: `src/financial_tracker/`
- Unit and contract tests: `tests/financial_tracker/`
- Integration tests: `tests/integration/financial_tracker/`
- Operations documentation: `docs/financial-tracker-operations.md`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the isolated Python package and test/runtime configuration required by every design slice.

- [ ] T001 Create the financial tracker package boundaries and configuration entry points in `src/financial_tracker/__init__.py`
- [ ] T002 Configure migration, fixture, and real-PostgreSQL test harness conventions in `tests/financial_tracker/conftest.py`

**Checkpoint**: The package imports and the real-PostgreSQL test harness can start without application behavior.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implement design slice PL-01, Financial Foundation and Provenance. No user-story task can start before these seams are stable.

- [ ] T003 Create typed domain entities, migrations, and uniqueness constraints for issuers, filings, fiscal periods, facts, provenance, analysis runs, and work items in `src/financial_tracker/domain/models.py`
- [ ] T004 Implement CIK/ticker identity resolution and authorization scope primitives in `src/financial_tracker/identity/resolver.py`
- [ ] T005 Implement exact-decimal fixture ingestion with transactional idempotency and structured audit events in `src/financial_tracker/ingestion/fixtures.py`
- [ ] T006 Implement durable work-item state transitions and coordinator ownership rules in `src/financial_tracker/work/state.py`
- [ ] T007 Add real-PostgreSQL foundation tests for identity, provenance, idempotent ingestion, and work transitions in `tests/integration/financial_tracker/test_foundation.py`

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

- [ ] T008 [P] [US1] Write red fixture tests for fiscal-period derivation, selectors, and amended filing behavior in `tests/financial_tracker/calculation/test_periods.py`
- [ ] T009 [P] [US1] Write red fixture tests for exact-decimal margin, streak, acceleration, and finite quality states in `tests/financial_tracker/calculation/test_acceleration.py`

### Implementation for User Story 1

- [ ] T010 [US1] Implement approved fact selectors and fiscal-period classification/derivation in `src/financial_tracker/selectors/periods.py`
- [ ] T011 [US1] Implement built-in revenue, operating income, margin, streak, and acceleration calculations with finite quality states in `src/financial_tracker/calculation/acceleration.py`
- [ ] T012 [US1] Persist immutable metric observations with source snapshot, calculation version, and complete provenance in `src/financial_tracker/calculation/observations.py`
- [ ] T013 [US1] Implement the authorized filing-analysis read model and response contract in `src/financial_tracker/query/analysis.py`
- [ ] T014 [US1] Add the filing-backed analysis integration test against real PostgreSQL fixtures in `tests/integration/financial_tracker/test_analysis.py`

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

- [ ] T015 [P] [US2] Write red tests for expression parsing, unit checks, unsafe operations, and dependency cycles in `tests/financial_tracker/metrics/test_expression.py`
- [ ] T016 [P] [US2] Write red tests for version activation, retirement, authorization, and historical observation selection in `tests/financial_tracker/metrics/test_registry.py`

### Implementation for User Story 2

- [ ] T017 [US2] Implement the restricted typed metric expression parser and validator in `src/financial_tracker/metrics/expression.py`
- [ ] T018 [US2] Implement immutable metric definition/version persistence and scope authorization in `src/financial_tracker/metrics/registry.py`
- [ ] T019 [US2] Implement dry-run, activation, retirement, and validation-report orchestration in `src/financial_tracker/metrics/service.py`
- [ ] T020 [US2] Implement dependency-aware targeted recalculation enqueueing and versioned history selection in `src/financial_tracker/recalculation/metric_runs.py`
- [ ] T021 [US2] Add metric-definition API contract tests for validation, authorization, dry run, and version history in `tests/financial_tracker/metrics/test_api.py`

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

- [ ] T022 [P] [US3] Write red refresh tests for new filings, amendments, restatements, duplicate delivery, and targeted recalculation in `tests/integration/financial_tracker/test_refresh.py`

### Implementation for User Story 3

- [ ] T023 [US3] Implement the SEC filing discovery adapter with User-Agent, timeout, retry, rate-budget, and circuit policy in `src/financial_tracker/sec/adapter.py`
- [ ] T024 [US3] Implement amendment detection and targeted refresh orchestration in `src/financial_tracker/sec/refresh.py`
- [ ] T025 [US3] Implement worker leasing, retry-wait, dead-letter, and recovery behavior in `src/financial_tracker/work/coordinator.py`
- [ ] T026 [US3] Add refresh metrics, structured failure artifacts, and operator continuity guidance in `docs/financial-tracker-operations.md`
- [ ] T027 [US3] Add the bounded live-SEC compatibility and outage-path integration tests in `tests/integration/financial_tracker/test_live_sec.py`

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

- [ ] T028 [P] [US4] Write red API/export parity and authorization tests in `tests/financial_tracker/api/test_exports.py`

### Implementation for User Story 4

- [ ] T029 [US4] Implement authenticated company, watchlist, portfolio, and metric-history query endpoints in `src/financial_tracker/api/queries.py`
- [ ] T030 [US4] Implement deterministic XLSX generation and immutable export manifests in `src/financial_tracker/exports/xlsx.py`
- [ ] T031 [US4] Implement the separately authorized Google Sheets delivery adapter in `src/financial_tracker/exports/google_sheets.py`

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

- [ ] T032 [P] [US5] Write red company-history tests for gaps, outliers, amendments, and provenance labels in `tests/financial_tracker/web/test_company_history.py`

### Implementation for User Story 5

- [ ] T033 [US5] Implement the company history query with freshness and provenance state in `src/financial_tracker/query/company_history.py`
- [ ] T034 [US5] Implement the server-rendered company detail and trend visualization preserving gaps and outliers in `src/financial_tracker/web/company_history.py`

**Checkpoint**: US5 is independently demonstrable from historical query through trustworthy company detail rendering.

---

## Phase 8: Polish and Cross-Cutting Validation

**Purpose**: Verify the complete slice-to-task contract without introducing a second implementation seam.

- [ ] T035 Run the real-PostgreSQL, live-SEC, API-parity, and metric-version acceptance suites in `tests/financial_tracker/test_feature_acceptance.py`
- [ ] T036 Document migration, rollback, feature-flag rollout, freshness states, and operator recovery checks in `docs/financial-tracker-operations.md`

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
8. Phase 8 runs after the task graph is complete.

### Parallel Opportunities

- T008 and T009 can run in parallel before the US1 implementation seams.
- T015 and T016 can run in parallel before the US2 implementation seams.
- T028 and T032 can run in parallel after the shared read model is available.

## Plan Design Slice Index

| Plan slice | Task range | Closed seams |
|---|---|---|
| PL-01 Financial Foundation and Provenance | T001-T007 | Package, domain persistence, identity, fixture ingestion, authorization, work state, and PostgreSQL evidence |
| PL-02 Calculation and Built-In Metric Observations | T008-T014 | Selectors, fiscal periods, calculations, quality states, immutable observations, and analysis read model |
| PL-03 Versioned User-Defined Metric Registry | T015-T021 | Restricted parser, validation, version persistence, authorization, dry run, lifecycle, recalculation, and API contract |
| PL-05 SEC Refresh, Operations, and Continuity | T022-T027 | SEC adapter, amendment refresh, worker recovery, observability, runbook, and bounded live compatibility |
| PL-04 Authorized Dashboard, API, and Deterministic Exports | T028-T031 | Authorized query contract, XLSX manifest, Google Sheets adapter, and parity tests |
| Company-level history contract | T032-T034 | Historical query and visualization for gaps, outliers, amendments, and provenance |
