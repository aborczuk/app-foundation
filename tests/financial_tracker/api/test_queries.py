"""Red contracts for authorized company, watchlist, and portfolio queries."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.persistence.models import (
    Issuer,
    Portfolio,
    PortfolioKind,
    Provenance,
    QualityState,
)


def test_authorized_query_facade_filters_companies_and_universes_by_scope() -> None:
    """Company and portfolio queries return only server-authorized resources."""
    from financial_tracker.api.queries import AuthorizedQueryService

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    user_id = uuid4()
    issuer = Issuer(uuid4(), "0000320193", "Example Corp", now)
    second_issuer = Issuer(uuid4(), "0000789018", "Another Corp", now)
    foreign_issuer = Issuer(uuid4(), "0000789019", "Foreign Corp", now)
    portfolio = Portfolio(uuid4(), user_id, "Core", PortfolioKind.PORTFOLIO, now)
    secondary_portfolio = Portfolio(uuid4(), user_id, "Growth", PortfolioKind.WATCHLIST, now)
    foreign_portfolio = Portfolio(uuid4(), uuid4(), "Other", PortfolioKind.WATCHLIST, now)
    scope = AuthorizationScope(
        user_id=user_id,
        tenant_id="tenant-a",
        subject_id="subject-a",
        portfolio_ids=frozenset({portfolio.id, secondary_portfolio.id}),
        issuer_ids=frozenset({issuer.id, second_issuer.id}),
    )
    service = AuthorizedQueryService(
        issuers=(issuer, foreign_issuer, second_issuer),
        portfolios=(portfolio, foreign_portfolio, secondary_portfolio),
        memberships={
            portfolio.id: (issuer.id, foreign_issuer.id, second_issuer.id),
            secondary_portfolio.id: (second_issuer.id,),
        },
    )

    assert service.list_companies(scope) == (second_issuer, issuer)
    assert service.list_portfolios(scope) == (portfolio, secondary_portfolio)
    assert service.list_portfolio_companies(scope, portfolio.id) == (second_issuer, issuer)


def test_authorized_query_facade_denies_foreign_portfolio_access() -> None:
    """A caller cannot use a foreign portfolio identifier to expand scope."""
    from financial_tracker.api.queries import AuthorizedQueryService

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    user_id = uuid4()
    issuer = Issuer(uuid4(), "0000320193", "Example Corp", now)
    foreign_portfolio = Portfolio(uuid4(), uuid4(), "Other", PortfolioKind.PORTFOLIO, now)
    scope = AuthorizationScope(
        user_id=user_id,
        tenant_id="tenant-a",
        subject_id="subject-a",
        portfolio_ids=frozenset(),
        issuer_ids=frozenset(),
    )
    service = AuthorizedQueryService(
        issuers=(issuer,),
        portfolios=(foreign_portfolio,),
        memberships={foreign_portfolio.id: (issuer.id,)},
    )

    with pytest.raises(AuthorizationError):
        service.list_portfolio_companies(scope, foreign_portfolio.id)


def test_metric_history_filters_definition_version_and_preserves_authorized_state() -> None:
    """History queries select immutable metric versions without leaking other issuers."""
    from financial_tracker.api.queries import AuthorizedQueryService

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    issuer_id = uuid4()
    scope = AuthorizationScope(
        user_id=uuid4(),
        tenant_id="tenant-a",
        subject_id="subject-a",
        portfolio_ids=frozenset(),
        issuer_ids=frozenset({issuer_id}),
    )
    issuer = Issuer(issuer_id, "0000320193", "Example Corp", now)
    service = AuthorizedQueryService(issuers=(issuer,), portfolios=(), memberships={})
    version_one = _history_observation(issuer_id, "1", now)
    version_two = _history_observation(
        issuer_id,
        "2",
        now.replace(day=2),
        quality_state=QualityState.STALE,
        freshness="recalculation-pending",
    )

    selected = service.list_metric_history(
        scope,
        (version_one, version_two),
        issuer_id=issuer_id,
        metric_id="revenue_acceleration",
        definition_version="2",
        correlation_id="history-1",
    )

    assert len(selected) == 1
    assert selected[0].definition_version == "2"
    assert selected[0].quality_state is QualityState.STALE
    assert selected[0].freshness == "recalculation-pending"
    assert selected[0].correlation_id == "history-1"


def _history_observation(
    issuer_id,
    definition_version: str,
    calculated_at: datetime,
    *,
    quality_state: QualityState = QualityState.VERIFIED,
    freshness: str = "fresh",
) -> MetricObservation:
    """Build one versioned observation for metric-history query tests."""
    return MetricObservation(
        id=uuid4(),
        tenant_id="tenant-a",
        issuer_id=issuer_id,
        fiscal_period_id=uuid4(),
        metric_id="revenue_acceleration",
        definition_version=definition_version,
        definition_hash=f"hash-v{definition_version}",
        definition_state="active",
        calculation_version="calc-v1",
        source_snapshot_hash=f"snapshot-{definition_version}",
        analysis_run_id=uuid4(),
        value=Decimal("12.50"),
        quality_state=quality_state,
        freshness=freshness,
        provenance=(
            Provenance(
                id=uuid4(),
                filing_id=uuid4(),
                accession=f"0000320193-25-00000{definition_version}",
                source_url="https://www.sec.gov/Archives/edgar/data/example",
                selector="Revenue",
                captured_at=calculated_at,
            ),
        ),
        calculated_at=calculated_at,
    )
