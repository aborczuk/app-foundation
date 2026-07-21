"""Red contracts for authorized company, watchlist, and portfolio queries."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.persistence.models import Issuer, Portfolio, PortfolioKind


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
