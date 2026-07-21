"""Live PostgreSQL coverage for filing-backed analysis projection."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from financial_tracker.calculation.observations import InMemoryObservationStore, MetricObservation
from financial_tracker.identity.resolver import build_authorization_scope
from financial_tracker.persistence.models import Filing, FinancialFact, Portfolio, PortfolioKind, Provenance, QualityState, User
from financial_tracker.query.analysis import read_analysis
from financial_tracker.selectors.periods import select_preferred_fact

MIGRATION_PATH = Path(__file__).resolve().parents[3] / "src" / "financial_tracker" / "persistence" / "migrations" / "001_foundation.sql"


def _require_database_url() -> str:
    """Return the configured live-test database URL or skip explicitly."""
    database_url = os.getenv("FINANCIAL_TRACKER_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("set FINANCIAL_TRACKER_TEST_DATABASE_URL to run live PostgreSQL tests")
    return database_url


def _load_psycopg():
    """Load psycopg and fail clearly when live testing is enabled without it."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required when live PostgreSQL tests are enabled") from exc
    return psycopg


@pytest.fixture()
def postgres_connection():
    """Yield one real PostgreSQL connection for the integration scenario."""
    psycopg = _load_psycopg()
    with psycopg.connect(_require_database_url(), connect_timeout=5) as connection:
        yield connection


def _reset_schema(connection) -> None:
    """Reset the disposable live schema for one integration scenario."""
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA IF EXISTS financial_tracker CASCADE")
        cursor.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
    connection.commit()


def test_filing_backed_analysis_runs_against_live_postgres(postgres_connection) -> None:
    """Stored filing facts and provenance produce an authorized analysis row."""
    _reset_schema(postgres_connection)
    now = datetime(2025, 5, 2, tzinfo=timezone.utc)
    tenant_id = "tenant-live"
    user_id = uuid4()
    issuer_id = uuid4()
    period_id = uuid4()
    filing_id = uuid4()
    fact_id = uuid4()
    provenance_id = uuid4()
    portfolio_id = uuid4()
    analysis_run_id = uuid4()

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO financial_tracker.users (id, tenant_id, subject_id, role, created_at) VALUES (%s, %s, %s, %s, %s)",
            (user_id, tenant_id, "subject-live", "analyst", now),
        )
        cursor.execute(
            "INSERT INTO financial_tracker.portfolios (id, owner_id, name, kind, created_at) VALUES (%s, %s, %s, %s, %s)",
            (portfolio_id, user_id, "Live Growth", PortfolioKind.PORTFOLIO.value, now),
        )
        cursor.execute(
            "INSERT INTO financial_tracker.issuers (id, cik, legal_name, created_at) VALUES (%s, %s, %s, %s)",
            (issuer_id, "0000000001", "Live Issuer", now),
        )
        cursor.execute(
            "INSERT INTO financial_tracker.portfolio_memberships (portfolio_id, issuer_id, added_at) VALUES (%s, %s, %s)",
            (portfolio_id, issuer_id, now),
        )
        cursor.execute(
            "INSERT INTO financial_tracker.fiscal_periods (id, issuer_id, start_date, end_date, fiscal_year, fiscal_quarter, period_kind) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (period_id, issuer_id, date(2025, 1, 1), date(2025, 3, 31), 2025, 1, "quarter"),
        )
        cursor.execute(
            "INSERT INTO financial_tracker.filings (id, issuer_id, authority, accession, form_type, filed_at, accepted_at, fiscal_period_id, is_amendment, source_url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (filing_id, issuer_id, "sec", "000001-25-000001", "10-Q", now, now, period_id, False, "https://www.sec.gov/Archives/000001-25-000001"),
        )
        cursor.execute(
            "INSERT INTO financial_tracker.financial_facts (id, issuer_id, filing_id, fiscal_period_id, concept, value, unit, dimensions, quality_state) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)",
            (fact_id, issuer_id, filing_id, period_id, "Revenues", Decimal("125.00"), "USD", "{}", QualityState.VERIFIED.value),
        )
        cursor.execute(
            "INSERT INTO financial_tracker.provenance (id, filing_id, accession, source_url, selector, captured_at, source_fact_id) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (provenance_id, filing_id, "000001-25-000001", "https://www.sec.gov/Archives/000001-25-000001", "Revenues", now, fact_id),
        )
    postgres_connection.commit()

    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, issuer_id, filing_id, fiscal_period_id, concept, value, unit, dimensions, quality_state FROM financial_tracker.financial_facts WHERE id = %s",
            (fact_id,),
        )
        fact_row = cursor.fetchone()
        cursor.execute(
            "SELECT id, issuer_id, authority, accession, form_type, filed_at, accepted_at, fiscal_period_id, is_amendment, source_url, supersedes_filing_id FROM financial_tracker.filings WHERE id = %s",
            (filing_id,),
        )
        filing_row = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM financial_tracker.provenance WHERE source_fact_id = %s", (fact_id,))
        assert cursor.fetchone()[0] == 1

    fact = FinancialFact(*fact_row[:7], dimensions=fact_row[7], quality_state=QualityState(fact_row[8]))
    filing = Filing(*filing_row)
    selected = select_preferred_fact([fact], filings={filing.id: filing})
    assert selected is not None

    user = User(user_id, tenant_id, "subject-live", "analyst", now)
    portfolio = Portfolio(portfolio_id, user_id, "Live Growth", PortfolioKind.PORTFOLIO, now)
    observation = MetricObservation(
        id=uuid4(),
        tenant_id=tenant_id,
        issuer_id=issuer_id,
        fiscal_period_id=period_id,
        metric_id="revenue_acceleration",
        definition_version="1",
        definition_hash="builtin-v1",
        definition_state="active",
        calculation_version="calc-1",
        source_snapshot_hash="live-snapshot-1",
        analysis_run_id=analysis_run_id,
        value=selected.value,
        quality_state=QualityState.VERIFIED,
        freshness="current",
        provenance=(Provenance(provenance_id, filing_id, filing.accession, filing.source_url, selected.concept, now, fact_id),),
        calculated_at=now,
    )
    store = InMemoryObservationStore()
    store.put(observation)
    scope = build_authorization_scope(user, [portfolio], {portfolio_id: [issuer_id]})

    rows = read_analysis(scope, store.all(), issuer_id=issuer_id, correlation_id="live-correlation")

    assert len(rows) == 1
    assert rows[0].value == Decimal("125.00")
    assert rows[0].source_accessions == ("000001-25-000001",)
    assert rows[0].correlation_id == "live-correlation"
