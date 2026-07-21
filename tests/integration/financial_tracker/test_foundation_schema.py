"""Live verification for the foundation migration constraints."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

MIGRATION_PATH = Path(__file__).resolve().parents[3] / "src" / "financial_tracker" / "persistence" / "migrations" / "001_foundation.sql"


def test_foundation_migration_enforces_identity_constraints() -> None:
    """Apply the real migration and verify duplicate filing identity is rejected."""
    database_url = os.getenv("FINANCIAL_TRACKER_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("set FINANCIAL_TRACKER_TEST_DATABASE_URL to run live PostgreSQL tests")
    psycopg = pytest.importorskip("psycopg")

    with psycopg.connect(database_url, connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS financial_tracker CASCADE")
            cursor.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
            issuer_id = uuid4()
            user_id = uuid4()
            cursor.execute(
                "INSERT INTO financial_tracker.users (id, tenant_id, subject_id, role, created_at) VALUES (%s, %s, %s, %s, now())",
                (user_id, "tenant-a", "analyst-a", "analyst"),
            )
            cursor.execute(
                "INSERT INTO financial_tracker.issuers (id, cik, legal_name, created_at) VALUES (%s, %s, %s, now())",
                (issuer_id, "0000000001", "Example Corp",),
            )
            filing_values = (uuid4(), issuer_id, "sec", "0000000001-25-000001", "10-Q", False, "https://example.test/filing")
            cursor.execute(
                "INSERT INTO financial_tracker.filings (id, issuer_id, authority, accession, form_type, filed_at, is_amendment, source_url) VALUES (%s, %s, %s, %s, %s, now(), %s, %s)",
                filing_values,
            )
            with pytest.raises(psycopg.errors.UniqueViolation):
                cursor.execute(
                    "INSERT INTO financial_tracker.filings (id, issuer_id, authority, accession, form_type, filed_at, is_amendment, source_url) VALUES (%s, %s, %s, %s, %s, now(), %s, %s)",
                    (uuid4(), *filing_values[1:]),
                )
