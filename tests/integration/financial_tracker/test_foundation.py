"""Live PostgreSQL coverage for foundation identity and provenance constraints."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

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
