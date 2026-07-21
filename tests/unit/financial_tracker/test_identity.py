"""Unit coverage for stable issuer identity and authorization scope rules."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from financial_tracker.identity import (
    AuthorizationError,
    IssuerTickerAlias,
    build_authorization_scope,
    normalize_cik,
    normalize_ticker,
    require_issuer_access,
    require_portfolio_access,
    resolve_issuer,
)
from financial_tracker.persistence.models import Issuer, Portfolio, PortfolioKind, User


def test_normalizes_cik_and_ticker() -> None:
    """Canonical lookup keys are stable across user input formatting."""
    assert normalize_cik("123") == "0000000123"
    assert normalize_ticker(" brk.b ") == "BRK.B"


def test_resolves_historical_ticker_to_stable_issuer() -> None:
    """Ticker changes preserve lookup through the issuer's stable identity."""
    issuer = Issuer(uuid4(), "0000000123", "Example Corp", datetime.now(timezone.utc))
    alias = IssuerTickerAlias(issuer.id, "EXM", date(2020, 1, 1), date(2023, 12, 31))
    assert resolve_issuer("EXM", {issuer.cik: issuer}, [alias], as_of=date(2022, 6, 1)) == issuer


def test_scope_is_derived_from_owned_portfolios() -> None:
    """A caller cannot grant itself access by supplying another owner's ID."""
    principal = User(uuid4(), "tenant-a", "subject-a", "analyst", datetime.now(timezone.utc))
    owned = Portfolio(uuid4(), principal.id, "Owned", PortfolioKind.WATCHLIST, datetime.now(timezone.utc))
    foreign = Portfolio(uuid4(), uuid4(), "Foreign", PortfolioKind.PORTFOLIO, datetime.now(timezone.utc))
    issuer_id = uuid4()
    foreign_issuer_id = uuid4()
    scope = build_authorization_scope(principal, [owned, foreign], {owned.id: [issuer_id], foreign.id: [foreign_issuer_id]})

    require_issuer_access(scope, issuer_id)
    with pytest.raises(AuthorizationError):
        require_issuer_access(scope, foreign_issuer_id)
    with pytest.raises(AuthorizationError):
        require_portfolio_access(scope, foreign.id)
