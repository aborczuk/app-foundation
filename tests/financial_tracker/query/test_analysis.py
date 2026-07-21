"""Red fixture coverage for authorized analysis projections."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationError, build_authorization_scope
from financial_tracker.persistence.models import Portfolio, PortfolioKind, Provenance, QualityState, User
from financial_tracker.query.analysis import read_analysis


def _observation(*, tenant_id: str, issuer_id) -> MetricObservation:
    """Build a compact provenance-complete observation for projection tests."""
    filing_id = uuid4()
    return MetricObservation(
        id=uuid4(),
        tenant_id=tenant_id,
        issuer_id=issuer_id,
        fiscal_period_id=uuid4(),
        metric_id="revenue_acceleration",
        definition_version="3",
        definition_hash="definition-v3",
        calculation_version="calc-1",
        source_snapshot_hash="snapshot-1",
        analysis_run_id=uuid4(),
        value=Decimal("25.00"),
        quality_state=QualityState.VERIFIED,
        freshness="current",
        provenance=(
            Provenance(
                id=uuid4(),
                filing_id=filing_id,
                accession="000001-25-000001",
                source_url="https://www.sec.gov/Archives/000001-25-000001",
                selector="RevenueFromContractWithCustomerExcludingAssessedTax",
                captured_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
            ),
        ),
        calculated_at=datetime(2025, 5, 2, tzinfo=timezone.utc),
    )


def test_authorized_analysis_projection_exposes_provenance_contract() -> None:
    """An in-scope issuer projects metric state, freshness, run, and accession metadata."""
    user_id = uuid4()
    issuer_id = uuid4()
    portfolio = Portfolio(uuid4(), user_id, "Growth", PortfolioKind.PORTFOLIO, datetime.now(timezone.utc))
    user = User(user_id, "tenant-a", "subject-a", "analyst", datetime.now(timezone.utc))
    scope = build_authorization_scope(user, [portfolio], {portfolio.id: [issuer_id]})

    rows = read_analysis(scope, [_observation(tenant_id="tenant-a", issuer_id=issuer_id)], issuer_id=issuer_id, correlation_id="corr-1")

    assert len(rows) == 1
    row = rows[0]
    assert row.metric_id == "revenue_acceleration"
    assert row.definition_version == "3"
    assert row.value == Decimal("25.00")
    assert row.quality_state is QualityState.VERIFIED
    assert row.freshness == "current"
    assert row.correlation_id == "corr-1"
    assert row.source_accessions == ("000001-25-000001",)
    assert row.source_fact_selectors == ("RevenueFromContractWithCustomerExcludingAssessedTax",)


def test_analysis_rejects_issuer_outside_server_derived_scope() -> None:
    """Client requests cannot bypass the server-derived issuer authorization scope."""
    user_id = uuid4()
    allowed_issuer_id = uuid4()
    forbidden_issuer_id = uuid4()
    portfolio = Portfolio(uuid4(), user_id, "Growth", PortfolioKind.PORTFOLIO, datetime.now(timezone.utc))
    user = User(user_id, "tenant-a", "subject-a", "analyst", datetime.now(timezone.utc))
    scope = build_authorization_scope(user, [portfolio], {portfolio.id: [allowed_issuer_id]})

    with pytest.raises(AuthorizationError):
        read_analysis(scope, [_observation(tenant_id="tenant-a", issuer_id=forbidden_issuer_id)], issuer_id=forbidden_issuer_id)
