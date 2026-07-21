"""Authenticated company, watchlist, and portfolio query boundary."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from uuid import UUID

from financial_tracker.identity.resolver import (
    AuthorizationError,
    AuthorizationScope,
    require_issuer_access,
    require_portfolio_access,
)
from financial_tracker.persistence.models import Issuer, Portfolio, PortfolioKind


class AuthorizedQueryService:
    """Serve tenant-scoped company and user-owned universe queries."""

    def __init__(
        self,
        *,
        issuers: Iterable[Issuer],
        portfolios: Iterable[Portfolio],
        memberships: Mapping[UUID, Iterable[UUID]],
    ) -> None:
        """Bind stable resources and server-owned portfolio memberships."""
        self._issuers = tuple(issuers)
        self._issuer_by_id = {issuer.id: issuer for issuer in self._issuers}
        self._portfolios = tuple(portfolios)
        self._portfolio_by_id = {portfolio.id: portfolio for portfolio in self._portfolios}
        self._memberships = {
            portfolio_id: tuple(issuer_ids)
            for portfolio_id, issuer_ids in memberships.items()
        }

    def list_companies(
        self,
        scope: AuthorizationScope,
        *,
        issuer_ids: Iterable[UUID] | None = None,
    ) -> tuple[Issuer, ...]:
        """Return only companies included in the authenticated issuer scope."""
        requested = set(issuer_ids) if issuer_ids is not None else None
        return tuple(
            issuer
            for issuer in self._issuers
            if issuer.id in scope.issuer_ids
            and (requested is None or issuer.id in requested)
        )

    def get_company(self, scope: AuthorizationScope, issuer_id: UUID) -> Issuer:
        """Return one company only after server-derived issuer authorization."""
        require_issuer_access(scope, issuer_id)
        try:
            return self._issuer_by_id[issuer_id]
        except KeyError as exc:
            raise KeyError(f"issuer {issuer_id} does not exist") from exc

    def list_portfolios(
        self,
        scope: AuthorizationScope,
        *,
        kind: PortfolioKind | None = None,
    ) -> tuple[Portfolio, ...]:
        """Return only portfolios owned by the authenticated principal."""
        return tuple(
            portfolio
            for portfolio in self._portfolios
            if portfolio.id in scope.portfolio_ids
            and portfolio.owner_id == scope.user_id
            and (kind is None or portfolio.kind is kind)
        )

    def list_portfolio_companies(
        self,
        scope: AuthorizationScope,
        portfolio_id: UUID,
    ) -> tuple[Issuer, ...]:
        """Return authorized issuer memberships for one owned portfolio."""
        require_portfolio_access(scope, portfolio_id)
        portfolio = self._portfolio_by_id.get(portfolio_id)
        if portfolio is None or portfolio.owner_id != scope.user_id:
            raise AuthorizationError("portfolio is outside the authenticated user's scope")
        return tuple(
            self._issuer_by_id[issuer_id]
            for issuer_id in self._memberships.get(portfolio_id, ())
            if issuer_id in scope.issuer_ids and issuer_id in self._issuer_by_id
        )
