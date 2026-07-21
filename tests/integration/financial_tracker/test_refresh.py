"""Live PostgreSQL contracts for filing refresh and targeted recalculation."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from financial_tracker.persistence.models import Filing, FinancialFact, QualityState

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "financial_tracker"
    / "persistence"
    / "migrations"
)


def _database_url() -> str:
    """Return the configured live database URL or skip this integration suite."""
    database_url = os.getenv("FINANCIAL_TRACKER_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("set FINANCIAL_TRACKER_TEST_DATABASE_URL to run live PostgreSQL tests")
    return database_url


def _load_psycopg():
    """Load psycopg only when the live refresh contract is enabled."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required when live PostgreSQL tests are enabled") from exc
    return psycopg


@pytest.fixture()
def postgres_connection():
    """Yield a disposable PostgreSQL connection for one refresh scenario."""
    psycopg = _load_psycopg()
    connection: Any
    with psycopg.connect(_database_url(), connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS financial_tracker CASCADE")
            for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                cursor.execute(migration_path.read_text(encoding="utf-8"))
        connection.commit()
        yield connection


def _seed_identity(connection, tenant_id: str) -> tuple[UUID, UUID, UUID]:
    """Create the tenant user, issuer, and fiscal period used by a fixture."""
    user_id = uuid4()
    issuer_id = uuid4()
    period_id = uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO financial_tracker.users (id, tenant_id, subject_id, role, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (user_id, tenant_id, "refresh-test-user", "analyst", datetime.now(timezone.utc)),
        )
        cursor.execute(
            "INSERT INTO financial_tracker.issuers (id, cik, legal_name, created_at) "
            "VALUES (%s, %s, %s, %s)",
            (issuer_id, "0000000001", "Refresh Example Corp", datetime.now(timezone.utc)),
        )
        cursor.execute(
            "INSERT INTO financial_tracker.fiscal_periods "
            "(id, issuer_id, start_date, end_date, fiscal_year, fiscal_quarter, period_kind) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (period_id, issuer_id, date(2025, 1, 1), date(2025, 3, 31), 2025, 1, "quarter"),
        )
    connection.commit()
    return user_id, issuer_id, period_id


def _coordinator(connection):
    """Construct the refresh boundary under test."""
    from financial_tracker.sec.refresh import FilingRefreshCoordinator

    return FilingRefreshCoordinator(connection)


def _filing(
    issuer_id: UUID,
    period_id: UUID,
    accession: str,
    *,
    is_amendment: bool = False,
    supersedes_filing_id: UUID | None = None,
) -> Filing:
    """Build one immutable filing snapshot with an optional lineage link."""
    captured_at = datetime.now(timezone.utc)
    return Filing(
        id=uuid4(),
        issuer_id=issuer_id,
        authority="sec",
        accession=accession,
        form_type="10-Q/A" if is_amendment else "10-Q",
        filed_at=captured_at,
        accepted_at=captured_at,
        fiscal_period_id=period_id,
        is_amendment=is_amendment,
        source_url=f"https://www.sec.gov/Archives/{accession}",
        supersedes_filing_id=supersedes_filing_id,
    )


def _fact(filing: Filing, period_id: UUID, concept: str, value: str) -> FinancialFact:
    """Build one exact-decimal fact tied to a filing snapshot."""
    return FinancialFact(
        id=uuid4(),
        issuer_id=filing.issuer_id,
        filing_id=filing.id,
        fiscal_period_id=period_id,
        concept=concept,
        value=Decimal(value),
        unit="USD",
        quality_state=QualityState.VERIFIED,
    )


def _request(
    tenant_id: str,
    filing: Filing,
    period_id: UUID,
    *,
    source_snapshot_hash: str,
    changed_concepts: tuple[str, ...] = ("revenue",),
    tracked_metric_ids: tuple[str, ...] = ("revenue", "operating_margin", "unrelated_metric"),
    change_kind: str = "new",
) -> Any:
    """Build a refresh request with explicit source and targeting context."""
    from financial_tracker.sec.refresh import FilingRefreshRequest

    return FilingRefreshRequest(
        tenant_id=tenant_id,
        filing=filing,
        facts=(_fact(filing, period_id, "revenue", "100"),),
        source_snapshot_hash=source_snapshot_hash,
        changed_concepts=changed_concepts,
        tracked_metric_ids=tracked_metric_ids,
        metric_dependencies={
            "revenue": (),
            "operating_margin": ("revenue",),
            "unrelated_metric": ("shares_outstanding",),
        },
        change_kind=change_kind,
    )


def test_new_filing_persists_facts_and_targeted_work(postgres_connection) -> None:
    """A new filing is durable and creates work only for affected metrics."""
    tenant_id = "tenant-refresh-new"
    _, issuer_id, period_id = _seed_identity(postgres_connection, tenant_id)
    filing = _filing(issuer_id, period_id, "0000000001-25-000001")

    result = _coordinator(postgres_connection).process(
        _request(tenant_id, filing, period_id, source_snapshot_hash="snapshot-new")
    )

    assert result.status == "queued"
    assert result.filing_id == filing.id
    assert result.enqueued_metric_ids == ("revenue", "operating_margin")
    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM financial_tracker.filings")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM financial_tracker.financial_facts")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM financial_tracker.work_items")
        assert cursor.fetchone()[0] == 2


def test_amendment_preserves_prior_filing_and_links_lineage(postgres_connection) -> None:
    """An amendment adds a snapshot and points at the filing it supersedes."""
    tenant_id = "tenant-refresh-amendment"
    _, issuer_id, period_id = _seed_identity(postgres_connection, tenant_id)
    coordinator = _coordinator(postgres_connection)
    original = _filing(issuer_id, period_id, "0000000001-25-000002")
    coordinator.process(
        _request(tenant_id, original, period_id, source_snapshot_hash="snapshot-original")
    )
    amendment = _filing(
        issuer_id,
        period_id,
        "0000000001-25-000003",
        is_amendment=True,
        supersedes_filing_id=original.id,
    )

    result = coordinator.process(
        _request(
            tenant_id,
            amendment,
            period_id,
            source_snapshot_hash="snapshot-amendment",
            change_kind="amendment",
        )
    )

    assert result.status == "queued"
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT is_amendment, supersedes_filing_id FROM financial_tracker.filings "
            "WHERE id = %s",
            (amendment.id,),
        )
        assert cursor.fetchone() == (True, original.id)
        cursor.execute("SELECT COUNT(*) FROM financial_tracker.filings")
        assert cursor.fetchone()[0] == 2


def test_restatement_preserves_original_observation_inputs(postgres_connection) -> None:
    """A restatement is additive and does not erase the original filing facts."""
    tenant_id = "tenant-refresh-restatement"
    _, issuer_id, period_id = _seed_identity(postgres_connection, tenant_id)
    coordinator = _coordinator(postgres_connection)
    original = _filing(issuer_id, period_id, "0000000001-25-000004")
    coordinator.process(
        _request(tenant_id, original, period_id, source_snapshot_hash="snapshot-restated-v1")
    )
    restatement = _filing(
        issuer_id,
        period_id,
        "0000000001-25-000005",
        is_amendment=True,
        supersedes_filing_id=original.id,
    )

    result = coordinator.process(
        _request(
            tenant_id,
            restatement,
            period_id,
            source_snapshot_hash="snapshot-restated-v2",
            change_kind="restatement",
        )
    )

    assert result.status == "queued"
    assert result.change_kind == "restatement"
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "SELECT filing_id, value FROM financial_tracker.financial_facts "
            "ORDER BY filing_id"
        )
        assert len(cursor.fetchall()) == 2


def test_duplicate_delivery_is_idempotent(postgres_connection) -> None:
    """Delivering the same accession twice does not duplicate facts or work."""
    tenant_id = "tenant-refresh-duplicate"
    _, issuer_id, period_id = _seed_identity(postgres_connection, tenant_id)
    filing = _filing(issuer_id, period_id, "0000000001-25-000006")
    request = _request(tenant_id, filing, period_id, source_snapshot_hash="snapshot-duplicate")
    coordinator = _coordinator(postgres_connection)
    reconstructed_filing = _filing(issuer_id, period_id, filing.accession)

    first = coordinator.process(request)
    second = coordinator.process(
        _request(
            tenant_id,
            reconstructed_filing,
            period_id,
            source_snapshot_hash="snapshot-duplicate",
        )
    )

    assert first.status == "queued"
    assert second.status == "duplicate"
    assert second.work_item_ids == first.work_item_ids
    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM financial_tracker.filings")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM financial_tracker.financial_facts")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT COUNT(*) FROM financial_tracker.work_items")
        assert cursor.fetchone()[0] == 2


def test_refresh_rejects_cross_issuer_fact_identity(postgres_connection) -> None:
    """A fact from another issuer cannot be attached to the filing transaction."""
    tenant_id = "tenant-refresh-identity"
    _, issuer_id, period_id = _seed_identity(postgres_connection, tenant_id)
    filing = _filing(issuer_id, period_id, "0000000001-25-000008")
    request = _request(tenant_id, filing, period_id, source_snapshot_hash="snapshot-identity")
    request = replace(
        request,
        facts=(
            FinancialFact(
                id=uuid4(),
                issuer_id=uuid4(),
                filing_id=filing.id,
                fiscal_period_id=period_id,
                concept="revenue",
                value=Decimal("100"),
                unit="USD",
                quality_state=QualityState.VERIFIED,
            ),
        ),
    )

    with pytest.raises(ValueError, match="issuer_id"):
        _coordinator(postgres_connection).process(request)


def test_refresh_rejects_missing_superseded_filing(postgres_connection) -> None:
    """An amendment cannot claim lineage from a filing absent from PostgreSQL."""
    tenant_id = "tenant-refresh-lineage"
    _, issuer_id, period_id = _seed_identity(postgres_connection, tenant_id)
    amendment = _filing(
        issuer_id,
        period_id,
        "0000000001-25-000009",
        is_amendment=True,
        supersedes_filing_id=uuid4(),
    )

    with pytest.raises(ValueError, match="superseded filing"):
        _coordinator(postgres_connection).process(
            _request(
                tenant_id,
                amendment,
                period_id,
                source_snapshot_hash="snapshot-lineage",
                change_kind="amendment",
            )
        )


def test_targeted_recalculation_excludes_unrelated_metric(postgres_connection) -> None:
    """A revenue change queues its dependent margin but not unrelated metrics."""
    tenant_id = "tenant-refresh-targeted"
    _, issuer_id, period_id = _seed_identity(postgres_connection, tenant_id)
    filing = _filing(issuer_id, period_id, "0000000001-25-000007")

    result = _coordinator(postgres_connection).process(
        _request(
            tenant_id,
            filing,
            period_id,
            source_snapshot_hash="snapshot-targeted",
            changed_concepts=("revenue",),
        )
    )

    assert "revenue" in result.enqueued_metric_ids
    assert "operating_margin" in result.enqueued_metric_ids
    assert "unrelated_metric" not in result.enqueued_metric_ids
