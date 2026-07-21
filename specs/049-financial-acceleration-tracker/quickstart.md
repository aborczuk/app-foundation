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

## Decision Log


<!-- speckit_implement_docs:entry_id=T001-5dbd832:decision_log -->
- T001 package boundary is intentionally metadata-only; domain behavior begins in later foundational tasks.

<!-- speckit_implement_docs:entry_id=T002-e5f0546:decision_log -->
- T002 uses PostgreSQL Compose only as disposable local infrastructure; the application contract remains an environment-configured PostgreSQL URL.

<!-- speckit_implement_docs:entry_id=T003-615bea6:decision_log -->
- T003 keeps domain entities as immutable dataclasses and leaves database constraints to the migration seam in T004.
