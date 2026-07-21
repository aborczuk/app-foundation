"""Authenticated company, watchlist, and portfolio query boundary."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from uuid import UUID

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import (
    AuthorizationError,
    AuthorizationScope,
    require_issuer_access,
    require_portfolio_access,
)
from financial_tracker.persistence.models import Issuer, Portfolio, PortfolioKind
from financial_tracker.query.analysis import AnalysisRow, read_analysis


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
        self._issuers = tuple(sorted(issuers, key=lambda issuer: (issuer.legal_name, str(issuer.id))))
        self._issuer_by_id = {issuer.id: issuer for issuer in self._issuers}
        self._portfolios = tuple(sorted(portfolios, key=lambda portfolio: (portfolio.name, str(portfolio.id))))
        self._portfolio_by_id = {portfolio.id: portfolio for portfolio in self._portfolios}
        self._memberships = {
            portfolio_id: tuple(sorted(issuer_ids, key=str))
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
        companies = (
            self._issuer_by_id[issuer_id]
            for issuer_id in self._memberships.get(portfolio_id, ())
            if issuer_id in scope.issuer_ids and issuer_id in self._issuer_by_id
        )
        return tuple(sorted(companies, key=lambda issuer: (issuer.legal_name, str(issuer.id))))

    def list_metric_history(
        self,
        scope: AuthorizationScope,
        observations: Iterable[MetricObservation],
        *,
        issuer_id: UUID,
        metric_id: str,
        definition_version: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[AnalysisRow, ...]:
        """Return an authorized metric history with an optional version filter."""
        require_issuer_access(scope, issuer_id)
        normalized_metric = metric_id.strip()
        if not normalized_metric:
            raise ValueError("metric_id must be non-empty")
        normalized_version = (
            definition_version.strip() if definition_version is not None else None
        )
        if definition_version is not None and not normalized_version:
            raise ValueError("definition_version must be non-empty when provided")
        matching = tuple(
            observation
            for observation in observations
            if observation.tenant_id == scope.tenant_id
            and observation.issuer_id == issuer_id
            and observation.metric_id == normalized_metric
            and (
                normalized_version is None
                or observation.definition_version == normalized_version
            )
        )
        rows = read_analysis(
            scope,
            matching,
            issuer_id=issuer_id,
            correlation_id=correlation_id,
        )
        return tuple(
            sorted(
                rows,
                key=lambda row: (
                    row.calculated_at,
                    row.fiscal_period_id,
                    row.definition_version,
                    row.analysis_run_id,
                ),
            )
        )
