"""Authorized dashboard collection read model and server-rendered states."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
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
    normalized_search = search.strip().casefold()
    visible = [
        record
        for record in records
        if _is_authorized(scope, record)
        and _matches_search(record, normalized_search)
        and (requested_quality is None or record.quality_state in requested_quality)
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


def _sort_key(record: DashboardRecord, field: str) -> tuple[object, str]:
    """Return a deterministic null-safe sort key for an allowed field."""
    value = getattr(record, field)
    if value is None:
        return (0, str(record.issuer_id))
    if isinstance(value, (Decimal, int)):
        return (value, str(record.issuer_id))
    return (str(value).casefold(), str(record.issuer_id))


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
