# Financial Acceleration Tracker Quickstart

## Local Preconditions

- Python dependencies are installed through the repository's `uv` workflow.
- A disposable PostgreSQL instance is available for integration verification.
- SEC live tests are opt-in and use an environment-backed User-Agent and rate budget.
- Google Sheets tests use a separately scoped test credential or remain disabled.

## Development Sequence

1. Create the isolated `src/financial_tracker/` package and migrations.
2. Run fixture and real-PostgreSQL foundation tests before calculation work.
3. Run calculation fixtures, then metric-definition dry-run and version-history tests.
4. Run SEC adapter compatibility and outage tests with live scheduling disabled.
5. Run dashboard/API/XLSX/Sheets parity and authorization tests.
6. Enable scheduled discovery only after the PL-05 readiness checks and operator runbook review pass.

## Verification Commands

Use the repository guards rather than raw test or lint commands:

```bash
uv run --no-sync python scripts/speckit_tasks_gate.py validate-format \
  --tasks-file specs/049-financial-acceleration-tracker/tasks.md --json
uv run --no-sync python scripts/speckit_plan_gate.py plan-sections \
  --plan-file specs/049-financial-acceleration-tracker/plan.md \
  --spec-file specs/049-financial-acceleration-tracker/spec.md --json
uv run --no-sync python scripts/speckit_plan_gate.py design-artifacts \
  --feature-dir specs/049-financial-acceleration-tracker --require-contracts --json
uv run --no-sync python scripts/pytest_guard.py run -- tests/financial_tracker
```

Start the disposable PostgreSQL backend before running the live harness:

```bash
docker compose -f docker-compose.financial-tracker.yml up -d --wait
export FINANCIAL_TRACKER_TEST_DATABASE_URL=postgresql://financial_tracker:financial_tracker_dev@localhost:55432/financial_tracker
uv run --no-sync python scripts/pytest_guard.py run -- tests/financial_tracker/test_harness.py
docker compose -f docker-compose.financial-tracker.yml down -v
```

Live SEC and Google Sheets verification must be explicit test selections and must not run as an implicit default. The live path must prove User-Agent, timeout, rate budget, bounded retry, outage degradation, duplicate delivery, lease recovery, and credential scoping.

## Rollout Flags

Keep `SEC_SCHEDULE_ENABLED=false` and `GOOGLE_SHEETS_DELIVERY_ENABLED=false` until migrations, real-backend tests, authorization tests, parity tests, observability, and rollback instructions are verified. A failed readiness check leaves the feature in fixture/manual-refresh mode and does not expose partial external delivery.

## Operator Checks

Before enabling scheduled refresh, confirm PostgreSQL migration status, worker readiness, queue age, SEC rate/error metrics, alert routing, and correlation IDs. During an outage, preserve the last successful observation with freshness and quality state, stop unbounded retries, and resume only from recoverable work items.

## Deterministic Operator Runbook Notes

### Recovery Delta Validation Notes




<!-- speckit_implement_docs:entry_id=T001-5dbd832:runbook -->
- Closed T001: scaffolded the financial_tracker package boundary, exported package metadata, and registered the package for wheel builds; import and Ruff checks passed.


<!-- speckit_implement_docs:entry_id=T002-e5f0546:runbook -->
- Closed T002: added the real PostgreSQL harness, disposable Compose service with healthcheck, and SELECT 1 live-backend verification.


<!-- speckit_implement_docs:entry_id=T003-615bea6:runbook -->
- Closed T003: added frozen typed entities and explicit PostgreSQL table mappings for identity, portfolios, filings, periods, facts, and provenance; model tests and Ruff passed.


<!-- speckit_implement_docs:entry_id=T004-01637b1:runbook -->
- Closed T004: added the foundation PostgreSQL migration and live constraint smoke coverage; code-scope QA passed.


<!-- speckit_implement_docs:entry_id=T005-5202ea1:runbook -->
- Closed T005: added normalized CIK/ticker resolution, historical ticker aliases, and owner-derived authorization scopes; unit QA passed.


<!-- speckit_implement_docs:entry_id=T006-f2c8fb2:runbook -->
- Closed T006: added exact-decimal fixture normalization and immutable fact/provenance callback writes; unit QA passed.


<!-- speckit_implement_docs:entry_id=T007-994ff02:runbook -->
- Closed T007: added transactional idempotency and structured audit handoff for normalized fixture ingestion; unit QA passed.


<!-- speckit_implement_docs:entry_id=T008-c9a5b89:runbook -->
- Closed T008: added durable work-item transitions and coordinator lease ownership; unit QA passed.


<!-- speckit_implement_docs:entry_id=T009-1248955:runbook -->
- Closed T009: added live PostgreSQL identity and provenance constraint coverage; the guarded test passed against the disposable local service.


<!-- speckit_implement_docs:entry_id=T010-c0e11e3:runbook -->
- Closed T010: added live PostgreSQL idempotent-ingestion and durable work-transition coverage; the guarded suite passed with 2 tests.


<!-- speckit_implement_docs:entry_id=T011-4c079c8:runbook -->
- Closed T011: added red fixture coverage for standalone, cumulative, and annual fiscal-period classification/derivation, approved default concept selection, and amendment precedence. The guarded pytest run intentionally remains red at collection until T013 adds selectors/periods.py; Ruff passed.


<!-- speckit_implement_docs:entry_id=T012-080fa18:runbook -->
- Closed T012: added red fixture coverage for exact-decimal operating margin, trailing improvement streak, second-difference materiality, and one-to-one finite quality-state mappings. The guarded pytest run intentionally remains red at collection until T014/T015 add acceleration.py; Ruff passed.


<!-- speckit_implement_docs:entry_id=T013-2c13f0b:runbook -->
- Closed T013: implemented explicit fiscal-period classification, evidence-gated cumulative/annual standalone derivation, approved concept priority, issuer/quality filtering, and accepted-filing amendment precedence. Focused selector fixtures passed 5 tests; Ruff passed.


<!-- speckit_implement_docs:entry_id=T014-1a6fd47:runbook -->
- Closed T014: implemented exact-decimal operating margin, trailing improvement streak, second-difference acceleration with materiality, and finite quality-state mapping. Focused calculation and period suite passed 10 tests; Ruff passed.


<!-- speckit_implement_docs:entry_id=T015-66d3c2d:runbook -->
- Closed T015: added explicit accelerating, decelerating, stable, and unavailable classifications with equality-as-material threshold semantics and invalid-input handling. Focused acceleration suite passed 11 tests; Ruff passed.


<!-- speckit_implement_docs:entry_id=T016-82b22f9:runbook -->
- Closed T016: added frozen metric observations with source/definition/calculation identity, finite-value and complete-provenance validation, idempotent retry semantics, and conflict-on-mutation behavior. Focused observation suite passed 3 tests; Ruff passed. PostgreSQL durability remains assigned to later integration coverage.


<!-- speckit_implement_docs:entry_id=T017-7c52ef7:runbook -->
- Closed T017: added tenant- and issuer-authorized analysis projections carrying company/period identity, metric definition version/hash/state, value or finite quality, analysis run, freshness, accessions, selectors, calculated timestamp, and correlation ID. Focused query/observation suite passed 5 tests; Ruff passed.

## Decision Log


<!-- speckit_implement_docs:entry_id=T001-5dbd832:decision_log -->
- T001 package boundary is intentionally metadata-only; domain behavior begins in later foundational tasks.

<!-- speckit_implement_docs:entry_id=T002-e5f0546:decision_log -->
- T002 uses PostgreSQL Compose only as disposable local infrastructure; the application contract remains an environment-configured PostgreSQL URL.

<!-- speckit_implement_docs:entry_id=T003-615bea6:decision_log -->
- T003 keeps domain entities as immutable dataclasses and leaves database constraints to the migration seam in T004.

<!-- speckit_implement_docs:entry_id=T004-01637b1:decision_log -->
- Foundation constraints keep immutable filing/fact provenance, analysis-run identities, and retry-safe work-item identities in PostgreSQL.

<!-- speckit_implement_docs:entry_id=T005-5202ea1:decision_log -->
- Identity resolution returns stable issuer IDs across ticker history, while authorization is derived from authenticated ownership and server-side memberships.

<!-- speckit_implement_docs:entry_id=T006-f2c8fb2:decision_log -->
- Fixture ingestion rejects binary floats and non-finite values, preserving exact numeric representation and explicit quality states.

<!-- speckit_implement_docs:entry_id=T007-994ff02:decision_log -->
- Idempotency keys are normalized before transaction checks, and audit events are emitted only after normalized fact/provenance writes succeed.

<!-- speckit_implement_docs:entry_id=T008-c9a5b89:decision_log -->
- Work ownership is enforced by unexpired coordinator leases; expired work returns to retry_wait for recovery.

<!-- speckit_implement_docs:entry_id=T009-1248955:decision_log -->
- Live foundation verification requires an explicit FINANCIAL_TRACKER_TEST_DATABASE_URL and fails setup when psycopg is unavailable; missing URL is the only skip condition.

<!-- speckit_implement_docs:entry_id=T010-c0e11e3:decision_log -->
- Integration tests use a minimal PostgreSQL-backed fixture store to exercise the existing ingestion coordinator while keeping production storage adapters out of scope for the foundation seam.

<!-- speckit_implement_docs:entry_id=T011-4c079c8:decision_log -->
- Red fixture tasks are closed on explicit expected-failure evidence plus lint and QA review; the generic closeout tests_passed ledger event does not mean the pre-implementation behavioral tests are green.

<!-- speckit_implement_docs:entry_id=T012-080fa18:decision_log -->
- Red arithmetic fixtures are kept separate from implementation so T013-T015 must prove the same contract green; expected red collection failures are recorded explicitly rather than counted as runtime verification.

<!-- speckit_implement_docs:entry_id=T013-2c13f0b:decision_log -->
- Selector precedence is newest accepted filing snapshot first, then approved concept rank within that snapshot; this preserves amendment semantics when taxonomy changes between filings.

<!-- speckit_implement_docs:entry_id=T014-1a6fd47:decision_log -->
- Non-finite Decimal inputs are rejected at each numeric calculation boundary and map to FAILED quality rather than allowing NaN or infinity into metric observations.

<!-- speckit_implement_docs:entry_id=T015-66d3c2d:decision_log -->
- Acceleration materiality equality is treated as material consistently by raw calculation and display classification; negative or non-finite thresholds are unavailable.

<!-- speckit_implement_docs:entry_id=T016-82b22f9:decision_log -->
- Observation identity excludes generated record ID and calculated timestamp for retry comparison, while semantic value, quality, freshness, and provenance content remain immutable and conflict-checked.

<!-- speckit_implement_docs:entry_id=T017-7c52ef7:decision_log -->
- Authorization is enforced before projection and tenant filtering occurs before output; the shared AnalysisRow remains provider-payload-free for API, dashboard, and export reuse.
