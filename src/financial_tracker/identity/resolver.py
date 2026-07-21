"""Stable issuer identity resolution and owner-derived authorization scopes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping
from uuid import UUID

from financial_tracker.persistence.models import Issuer, Portfolio, User

CIK_PATTERN = re.compile(r"^\d{1,10}$")
TICKER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.-]{0,9}$")


class IdentityResolutionError(ValueError):
    """Raised when an issuer identifier is missing, invalid, or unresolved."""


class AuthorizationError(PermissionError):
    """Raised when a principal attempts to access an out-of-scope entity."""


@dataclass(frozen=True, slots=True)
class IssuerTickerAlias:
    """Ticker history entry that resolves to one stable issuer identity."""

    issuer_id: UUID
    ticker: str
    valid_from: date
    valid_to: date | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationScope:
    """Server-derived tenant, portfolio, and issuer access scope."""

    user_id: UUID
    tenant_id: str
    subject_id: str
    portfolio_ids: frozenset[UUID]
    issuer_ids: frozenset[UUID]


def normalize_cik(value: str) -> str:
    """Normalize a SEC CIK to its canonical ten-digit representation."""
    candidate = value.strip()
    if not CIK_PATTERN.fullmatch(candidate):
        raise IdentityResolutionError("CIK must contain one to ten digits")
    return candidate.zfill(10)


def normalize_ticker(value: str) -> str:
    """Normalize and validate a ticker symbol for lookup."""
    candidate = value.strip().upper()
    if not TICKER_PATTERN.fullmatch(candidate):
        raise IdentityResolutionError("ticker contains unsupported characters")
    return candidate


def resolve_issuer(
    identifier: str,
    issuers_by_cik: Mapping[str, Issuer],
    ticker_aliases: Iterable[IssuerTickerAlias],
    *,
    as_of: date | None = None,
) -> Issuer:
    """Resolve a CIK or date-valid ticker alias to a stable issuer record."""
    candidate = identifier.strip()
    if CIK_PATTERN.fullmatch(candidate):
        issuer = issuers_by_cik.get(normalize_cik(candidate))
        if issuer is None:
            raise IdentityResolutionError("issuer CIK was not found")
        return issuer

    ticker = normalize_ticker(candidate)
    effective_date = as_of or date.today()
    matches = [
        alias
        for alias in ticker_aliases
        if normalize_ticker(alias.ticker) == ticker
        and alias.valid_from <= effective_date
        and (alias.valid_to is None or effective_date <= alias.valid_to)
    ]
    if not matches:
        raise IdentityResolutionError("issuer ticker was not found for the requested date")
    if len(matches) > 1:
        raise IdentityResolutionError("issuer ticker history is ambiguous for the requested date")
    issuer = next((item for item in issuers_by_cik.values() if item.id == matches[0].issuer_id), None)
    if issuer is None:
        raise IdentityResolutionError("ticker alias points to an unknown issuer")
    return issuer


def build_authorization_scope(
    principal: User,
    portfolios: Iterable[Portfolio],
    memberships: Mapping[UUID, Iterable[UUID]],
) -> AuthorizationScope:
    """Derive access from the authenticated principal and server-owned memberships."""
    owned_portfolios = [portfolio for portfolio in portfolios if portfolio.owner_id == principal.id]
    portfolio_ids = frozenset(portfolio.id for portfolio in owned_portfolios)
    issuer_ids = frozenset(
        issuer_id
        for portfolio_id in portfolio_ids
        for issuer_id in memberships.get(portfolio_id, ())
    )
    return AuthorizationScope(
        user_id=principal.id,
        tenant_id=principal.tenant_id,
        subject_id=principal.subject_id,
        portfolio_ids=portfolio_ids,
        issuer_ids=issuer_ids,
    )


def require_portfolio_access(scope: AuthorizationScope, portfolio_id: UUID) -> None:
    """Raise when a portfolio is not included in the principal's derived scope."""
    if portfolio_id not in scope.portfolio_ids:
        raise AuthorizationError("portfolio is outside the authenticated user's scope")


def require_issuer_access(scope: AuthorizationScope, issuer_id: UUID) -> None:
    """Raise when an issuer is not reachable through an owned portfolio."""
    if issuer_id not in scope.issuer_ids:
        raise AuthorizationError("issuer is outside the authenticated user's scope")
