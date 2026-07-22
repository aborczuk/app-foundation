"""Authorized dashboard collection read model and server-rendered states."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from financial_tracker.identity.resolver import AuthorizationScope
from financial_tracker.persistence.models import QualityState

TABLE_ADAPTER: Final = "tanstack-table"
CHART_ADAPTER: Final = "recharts"
MAX_ERROR_MESSAGE_LENGTH: Final = 200
SORT_FIELDS: Final = frozenset(
    {
        "company_name",
        "ticker",
        "metric_id",
        "fiscal_period",
        "value",
        "acceleration",
        "improvement_streak",
        "quality_state",
        "freshness",
    }
)
NUMERIC_SORT_FIELDS: Final = frozenset(
    {"value", "acceleration", "improvement_streak"}
)


class DashboardState(StrEnum):
    """Finite states a server-rendered dashboard can expose."""

    LOADING = "loading"
    EMPTY = "empty"
    ERROR = "error"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class DashboardRecord:
    """Server-side dashboard input with visible analysis and provenance fields."""

    tenant_id: str
    issuer_id: UUID
    portfolio_id: UUID
    company_name: str
    ticker: str
    metric_id: str
    fiscal_period: str
    value: Decimal | None
    acceleration: Decimal | None
    improvement_streak: int | None
    quality_state: QualityState
    freshness: str
    source_accessions: tuple[str, ...]
    definition_version: str
    definition_hash: str
    definition_state: str
    analysis_run_id: UUID
    source_fact_selectors: tuple[str, ...]
    calculated_at: datetime
    correlation_id: str | None
    history: tuple[Decimal | None, ...]


@dataclass(frozen=True, slots=True)
class DashboardRow:
    """Browser-table row preserving status, provenance, and sparkline values."""

    issuer_id: UUID
    portfolio_id: UUID
    company_name: str
    ticker: str
    metric_id: str
    fiscal_period: str
    value: Decimal | None
    acceleration: Decimal | None
    improvement_streak: int | None
    quality_state: QualityState
    freshness: str
    source_accessions: tuple[str, ...]
    definition_version: str
    definition_hash: str
    definition_state: str
    analysis_run_id: UUID
    source_fact_selectors: tuple[str, ...]
    calculated_at: datetime
    correlation_id: str | None
    sparkline: tuple[Decimal | None, ...]


@dataclass(frozen=True, slots=True)
class DashboardView:
    """Complete collection payload for server and browser rendering."""

    state: DashboardState
    rows: tuple[DashboardRow, ...]
    empty_message: str | None
    error_message: str | None
    table_adapter: str
    chart_adapter: str


def render_dashboard(
    scope: AuthorizationScope,
    records: Iterable[DashboardRecord],
    *,
    search: str = "",
    quality_states: frozenset[QualityState] | set[QualityState] | None = None,
    portfolio_ids: frozenset[UUID] | set[UUID] | None = None,
    metric_ids: frozenset[str] | set[str] | None = None,
    fiscal_periods: frozenset[str] | set[str] | None = None,
    acceleration_min: Decimal | None = None,
    acceleration_max: Decimal | None = None,
    streak_min: int | None = None,
    streak_max: int | None = None,
    sort_by: str = "company_name",
    descending: bool = False,
    state: DashboardState = DashboardState.READY,
    error_message: str | None = None,
) -> DashboardView:
    """Build an authorized, sortable, filterable dashboard collection view."""
    if sort_by not in SORT_FIELDS:
        raise ValueError(f"unsupported dashboard sort field: {sort_by}")

    if state is DashboardState.LOADING:
        return _state_view(DashboardState.LOADING)
    if state is DashboardState.ERROR:
        return _state_view(DashboardState.ERROR, error_message=error_message)

    requested_quality = None if quality_states is None else frozenset(quality_states)
    requested_portfolios = None if portfolio_ids is None else frozenset(portfolio_ids)
    requested_metrics = None if metric_ids is None else frozenset(metric_ids)
    requested_periods = None if fiscal_periods is None else frozenset(fiscal_periods)
    normalized_search = search.strip().casefold()
    visible = [
        record
        for record in records
        if _is_authorized(scope, record)
        and _matches_search(record, normalized_search)
        and (requested_quality is None or record.quality_state in requested_quality)
        and (requested_portfolios is None or record.portfolio_id in requested_portfolios)
        and (requested_metrics is None or record.metric_id in requested_metrics)
        and (requested_periods is None or record.fiscal_period in requested_periods)
        and _within_bounds(record.acceleration, acceleration_min, acceleration_max)
        and _within_bounds(record.improvement_streak, streak_min, streak_max)
    ]
    visible.sort(key=lambda record: _sort_key(record, sort_by), reverse=descending)
    rows = tuple(_row(record) for record in visible)
    if not rows:
        return _state_view(DashboardState.EMPTY)
    return DashboardView(
        state=DashboardState.READY,
        rows=rows,
        empty_message=None,
        error_message=None,
        table_adapter=TABLE_ADAPTER,
        chart_adapter=CHART_ADAPTER,
    )


def _is_authorized(scope: AuthorizationScope, record: DashboardRecord) -> bool:
    """Apply tenant, issuer, and server-derived portfolio boundaries."""
    return (
        record.tenant_id == scope.tenant_id
        and record.issuer_id in scope.issuer_ids
        and record.portfolio_id in scope.portfolio_ids
    )


def _matches_search(record: DashboardRecord, query: str) -> bool:
    """Match the bounded collection search against user-visible identifiers."""
    if not query:
        return True
    return query in " ".join(
        (record.company_name, record.ticker, record.metric_id, record.fiscal_period)
    ).casefold()


def _sort_key(record: DashboardRecord, field: str) -> tuple[object, ...]:
    """Return a deterministic null-safe sort key for an allowed field."""
    value = getattr(record, field)
    if field in NUMERIC_SORT_FIELDS:
        normalized = Decimal("0") if value is None else value
    else:
        normalized = "" if value is None else str(value).casefold()
    return (
        value is not None,
        normalized,
        record.company_name.casefold(),
        record.ticker.casefold(),
        record.metric_id.casefold(),
        record.fiscal_period.casefold(),
        record.portfolio_id.hex,
        record.issuer_id.hex,
        record.definition_version,
        record.definition_hash,
        record.analysis_run_id.hex,
        record.source_accessions,
    )


def _within_bounds(
    value: Decimal | int | None,
    lower: Decimal | int | None,
    upper: Decimal | int | None,
) -> bool:
    """Apply inclusive numeric bounds while excluding unavailable values."""
    if value is None:
        return lower is None and upper is None
    return (lower is None or value >= lower) and (upper is None or value <= upper)


def _row(record: DashboardRecord) -> DashboardRow:
    """Project one authorized record without dropping quality or provenance."""
    return DashboardRow(
        issuer_id=record.issuer_id,
        portfolio_id=record.portfolio_id,
        company_name=record.company_name,
        ticker=record.ticker,
        metric_id=record.metric_id,
        fiscal_period=record.fiscal_period,
        value=record.value,
        acceleration=record.acceleration,
        improvement_streak=record.improvement_streak,
        quality_state=record.quality_state,
        freshness=record.freshness,
        source_accessions=record.source_accessions,
        definition_version=record.definition_version,
        definition_hash=record.definition_hash,
        definition_state=record.definition_state,
        analysis_run_id=record.analysis_run_id,
        source_fact_selectors=record.source_fact_selectors,
        calculated_at=record.calculated_at,
        correlation_id=record.correlation_id,
        sparkline=record.history,
    )


def _state_view(
    state: DashboardState,
    *,
    error_message: str | None = None,
) -> DashboardView:
    """Build a state-only view with bounded operator-facing messages."""
    normalized_error = _bounded_error_message(error_message) if state is DashboardState.ERROR else None
    return DashboardView(
        state=state,
        rows=(),
        empty_message="No authorized results" if state is DashboardState.EMPTY else None,
        error_message=normalized_error,
        table_adapter=TABLE_ADAPTER,
        chart_adapter=CHART_ADAPTER,
    )


def _bounded_error_message(message: str | None) -> str:
    """Collapse and bound operational errors before exposing them to clients."""
    normalized = " ".join((message or "Dashboard unavailable").split())
    return normalized[:MAX_ERROR_MESSAGE_LENGTH] or "Dashboard unavailable"
