"""Live PostgreSQL coverage for foundation identity and provenance constraints."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from financial_tracker.ingestion.fixtures import ingest_fixture_batch, parse_fixture_records
from financial_tracker.work import (
    CoordinatorOwnershipError,
    WorkItem,
    WorkState,
    dead_letter_work_item,
    lease_work_item,
    retry_work_item,
    start_work_item,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "financial_tracker"
    / "persistence"
    / "migrations"
    / "001_foundation.sql"
)


def _require_database_url() -> str:
    """Return the configured live-test database URL or skip the test."""
    database_url = os.getenv("FINANCIAL_TRACKER_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("set FINANCIAL_TRACKER_TEST_DATABASE_URL to run live PostgreSQL tests")
    return database_url


def _apply_migration(connection) -> None:
    """Reset and apply the foundation migration on the live test connection."""
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA IF EXISTS financial_tracker CASCADE")
        cursor.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
    connection.commit()


def _load_psycopg():
    """Load psycopg for live tests and fail if the test environment is incomplete."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required when live PostgreSQL tests are enabled") from exc
    return psycopg


def _assert_unique_violation(connection, statement: str, values: tuple[object, ...], psycopg) -> None:
    """Assert a duplicate identity write fails and restore the transaction."""
    with pytest.raises(psycopg.errors.UniqueViolation):
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(statement, values)


class _PostgresFixtureStore:
    """Minimal real-PostgreSQL adapter for the transactional fixture contract."""

    def __init__(self, connection) -> None:
        """Bind the adapter to one disposable test connection."""
        self._connection = connection

    @contextmanager
    def transaction(self):
        """Commit successful fixture writes and roll back failed batches."""
        try:
            yield self
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def has_ingestion(self, tenant_id: str, idempotency_key: str) -> bool:
        """Check the durable completion audit event for an idempotency key."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM financial_tracker.audit_events "
                "WHERE tenant_id = %s AND event_type = %s AND idempotency_key = %s",
                (tenant_id, "fixture_ingestion_completed", idempotency_key),
            )
            return cursor.fetchone() is not None

    def write_fact(self, fact) -> None:
        """Persist one normalized fact in the live foundation schema."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO financial_tracker.financial_facts "
                "(id, issuer_id, filing_id, fiscal_period_id, concept, value, unit, dimensions, quality_state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
                (
                    fact.id,
                    fact.issuer_id,
                    fact.filing_id,
                    fact.fiscal_period_id,
                    fact.concept,
                    fact.value,
                    fact.unit,
                    json.dumps(dict(fact.dimensions)),
                    fact.quality_state.value,
                ),
            )

    def write_provenance(self, provenance) -> None:
        """Persist one immutable provenance record in the live schema."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO financial_tracker.provenance "
                "(id, filing_id, accession, source_url, selector, captured_at, source_fact_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    provenance.id,
                    provenance.filing_id,
                    provenance.accession,
                    provenance.source_url,
                    provenance.selector,
                    provenance.captured_at,
                    provenance.source_fact_id,
                ),
            )

    def write_audit_event(self, event) -> None:
        """Persist the structured completion event used for idempotency checks."""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO financial_tracker.audit_events "
                "(id, tenant_id, event_type, idempotency_key, payload, created_at) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s)",
                (
                    event.id,
                    event.tenant_id,
                    event.event_type,
                    event.idempotency_key,
                    json.dumps(dict(event.payload)),
                    event.created_at,
                ),
            )


def test_foundation_identity_and_provenance_constraints() -> None:
    """Real PostgreSQL rejects duplicate identities and provenance observations."""
    database_url = _require_database_url()
    psycopg = _load_psycopg()
    user_id = uuid4()
    issuer_id = uuid4()
    filing_id = uuid4()
    fact_id = uuid4()

    with psycopg.connect(database_url, connect_timeout=5) as connection:
        _apply_migration(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO financial_tracker.users "
                "(id, tenant_id, subject_id, role, created_at) "
                "VALUES (%s, %s, %s, %s, now())",
                (user_id, "tenant-a", "subject-a", "analyst"),
            )
        _assert_unique_violation(
            connection,
            "INSERT INTO financial_tracker.users "
            "(id, tenant_id, subject_id, role, created_at) "
            "VALUES (%s, %s, %s, %s, now())",
            (uuid4(), "tenant-a", "subject-a", "analyst"),
            psycopg,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO financial_tracker.issuers "
                "(id, cik, legal_name, created_at) VALUES (%s, %s, %s, now())",
                (issuer_id, "0000000001", "Example Corp"),
            )
            cursor.execute(
                "INSERT INTO financial_tracker.filings "
                "(id, issuer_id, authority, accession, form_type, filed_at, "
                "is_amendment, source_url) "
                "VALUES (%s, %s, %s, %s, %s, now(), %s, %s)",
                (filing_id, issuer_id, "sec", "0000000001-25-000001", "10-Q", False, "https://example.test/filing"),
            )
            cursor.execute(
                "INSERT INTO financial_tracker.financial_facts "
                "(id, issuer_id, filing_id, concept, value, unit, quality_state) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (fact_id, issuer_id, filing_id, "Revenue", "100.00", "USD", "verified"),
            )
            cursor.execute(
                "INSERT INTO financial_tracker.provenance "
                "(id, filing_id, accession, source_url, selector, captured_at, source_fact_id) "
                "VALUES (%s, %s, %s, %s, %s, now(), %s)",
                (uuid4(), filing_id, "0000000001-25-000001", "https://example.test/filing", "Revenue", fact_id),
            )
        _assert_unique_violation(
            connection,
            "INSERT INTO financial_tracker.provenance "
            "(id, filing_id, accession, source_url, selector, captured_at, source_fact_id) "
            "VALUES (%s, %s, %s, %s, %s, now(), %s)",
            (uuid4(), filing_id, "0000000001-25-000001", "https://example.test/filing", "Revenue", fact_id),
            psycopg,
        )


def test_idempotent_ingestion_and_work_transitions() -> None:
    """Real PostgreSQL preserves ingestion idempotency and durable work state."""
    database_url = _require_database_url()
    psycopg = _load_psycopg()
    issuer_id = uuid4()
    filing_id = uuid4()
    fact_id = uuid4()
    work_id = uuid4()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with psycopg.connect(database_url, connect_timeout=5) as connection:
        _apply_migration(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO financial_tracker.issuers "
                "(id, cik, legal_name, created_at) VALUES (%s, %s, %s, now())",
                (issuer_id, "0000000002", "Fixture Corp"),
            )
            cursor.execute(
                "INSERT INTO financial_tracker.filings "
                "(id, issuer_id, authority, accession, form_type, filed_at, "
                "is_amendment, source_url) VALUES (%s, %s, %s, %s, %s, now(), %s, %s)",
                (filing_id, issuer_id, "sec", "0000000002-25-000001", "10-Q", False, "https://example.test/filing"),
            )
        records = parse_fixture_records(
            [
                {
                    "fact_id": str(fact_id),
                    "issuer_id": str(issuer_id),
                    "filing_id": str(filing_id),
                    "accession": "0000000002-25-000001",
                    "source_url": "https://example.test/filing",
                    "selector": "Revenue",
                    "concept": "Revenue",
                    "value": "125.50",
                    "unit": "USD",
                }
            ]
        )
        store = _PostgresFixtureStore(connection)
        first = ingest_fixture_batch(records, tenant_id="tenant-a", idempotency_key="batch-1", store=store)
        second = ingest_fixture_batch(records, tenant_id=" tenant-a ", idempotency_key=" batch-1 ", store=store)
        assert first.fact_count == 1
        assert first.duplicate is False
        assert second.duplicate is True
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM financial_tracker.financial_facts")
            fact_count = cursor.fetchone()
            assert fact_count is not None
            assert fact_count[0] == 1
            cursor.execute("SELECT count(*) FROM financial_tracker.audit_events")
            audit_count = cursor.fetchone()
            assert audit_count is not None
            assert audit_count[0] == 1

        item = WorkItem(work_id, "tenant-a", "work-1", "refresh")
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO financial_tracker.work_items "
                "(id, tenant_id, idempotency_key, kind, state, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (item.id, item.tenant_id, item.idempotency_key, item.kind, item.state.value, now),
            )
        lease_work_item(item, "worker-a", now=now, lease_seconds=30)
        start_work_item(item, "worker-a", now=now)
        with pytest.raises(CoordinatorOwnershipError):
            retry_work_item(item, "worker-b", now=now)
        retry_work_item(item, "worker-a", now=now)
        lease_work_item(item, "worker-b", now=now + timedelta(seconds=1))
        start_work_item(item, "worker-b", now=now + timedelta(seconds=1))
        dead_letter_work_item(item, "worker-b", now=now + timedelta(seconds=1))
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE financial_tracker.work_items SET state = %s, lease_owner = %s, "
                "lease_expires_at = %s, attempts = %s WHERE id = %s",
                (item.state.value, item.lease_owner, item.lease_expires_at, item.attempts, item.id),
            )
            connection.commit()
            cursor.execute(
                "SELECT state, attempts FROM financial_tracker.work_items WHERE id = %s",
                (item.id,),
            )
            assert cursor.fetchone() == (WorkState.DEAD_LETTER.value, 2)


def test_postgres_coordinator_owns_lease_and_running_state() -> None:
    """Live coordinator leasing enforces ownership at the database boundary."""
    database_url = _require_database_url()
    psycopg = _load_psycopg()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    work_id = uuid4()

    from financial_tracker.work.coordinator import PostgresWorkCoordinator

    with psycopg.connect(database_url, connect_timeout=5) as connection:
        _apply_migration(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO financial_tracker.work_items "
                "(id, tenant_id, idempotency_key, kind, state, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (work_id, "tenant-coordinator", "work-coordinator-1", "refresh", "queued", now),
            )
        owner = PostgresWorkCoordinator(connection, "worker-a")
        contender = PostgresWorkCoordinator(connection, "worker-b")

        leased = owner.lease_next("tenant-coordinator", now=now, lease_seconds=30)
        assert leased is not None
        assert leased.id == work_id
        assert leased.state is WorkState.LEASED
        assert contender.lease_next("tenant-coordinator", now=now) is None

        started = owner.start(work_id, now=now)
        assert started.state is WorkState.RUNNING
        with pytest.raises(CoordinatorOwnershipError):
            contender.complete(work_id, now=now)

        completed = owner.complete(work_id, now=now)
        assert completed.state is WorkState.SUCCEEDED
        assert completed.lease_owner is None
        assert completed.lease_expires_at is None


def test_postgres_coordinator_recovers_failed_and_expired_work() -> None:
    """Live coordinator recovery handles retry, terminal failure, and expiry."""
    database_url = _require_database_url()
    psycopg = _load_psycopg()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    retry_id = uuid4()
    dead_letter_id = uuid4()
    expired_id = uuid4()

    from financial_tracker.work.coordinator import PostgresWorkCoordinator

    with psycopg.connect(database_url, connect_timeout=5) as connection:
        _apply_migration(connection)
        with connection.cursor() as cursor:
            for work_id, tenant_id, idempotency_key in (
                (retry_id, "tenant-retry", "work-retry-1"),
                (dead_letter_id, "tenant-dead-letter", "work-dead-letter-1"),
                (expired_id, "tenant-expired", "work-expired-1"),
            ):
                cursor.execute(
                    "INSERT INTO financial_tracker.work_items "
                    "(id, tenant_id, idempotency_key, kind, state, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (work_id, tenant_id, idempotency_key, "refresh", "queued", now),
                )
        owner = PostgresWorkCoordinator(connection, "worker-a")
        recovery_worker = PostgresWorkCoordinator(connection, "worker-b")

        retry_lease = owner.lease_next("tenant-retry", now=now, lease_seconds=30)
        assert retry_lease is not None
        assert retry_lease.id == retry_id
        assert owner.start(retry_id, now=now).state is WorkState.RUNNING
        retried = owner.retry(retry_id, now=now)
        assert retried.state is WorkState.RETRY_WAIT
        assert retried.lease_owner is None
        assert retried.lease_expires_at is None

        dead_letter_lease = owner.lease_next("tenant-dead-letter", now=now, lease_seconds=30)
        assert dead_letter_lease is not None
        assert dead_letter_lease.id == dead_letter_id
        assert owner.start(dead_letter_id, now=now).state is WorkState.RUNNING
        dead_lettered = owner.dead_letter(dead_letter_id, now=now)
        assert dead_lettered.state is WorkState.DEAD_LETTER
        assert dead_lettered.lease_owner is None
        assert dead_lettered.lease_expires_at is None

        expired_lease = owner.lease_next("tenant-expired", now=now, lease_seconds=30)
        assert expired_lease is not None
        assert expired_lease.id == expired_id
        recovered = recovery_worker.recover_expired_lease(expired_id, now=now + timedelta(seconds=31))
        assert recovered.state is WorkState.RETRY_WAIT
        assert recovered.lease_owner is None
        assert recovered.lease_expires_at is None
