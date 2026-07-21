"""Company-history view data that preserves gaps, outliers, and provenance."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from financial_tracker.persistence.models import QualityState
from financial_tracker.query.company_history import CompanyHistoryPoint


@dataclass(frozen=True, slots=True)
class CompanyHistoryChartPoint:
    """Chart-ready point whose missing value remains an explicit gap."""

    quarter_label: str
    value: Decimal | None
    is_gap: bool
    is_outlier: bool
    quality_state: QualityState
    calculation_status: str


@dataclass(frozen=True, slots=True)
class CompanyHistoryRow:
    """Table-ready point with visible status and filing provenance."""

    quarter_label: str
    value: Decimal | None
    status_label: str
    source_accessions: tuple[str, ...]
    definition_version: str


@dataclass(frozen=True, slots=True)
class CompanyHistoryView:
    """Complete company detail payload for chart and table rendering."""

    title: str
    metric_label: str
    chart_points: tuple[CompanyHistoryChartPoint, ...]
    rows: tuple[CompanyHistoryRow, ...]
    empty_state: str | None


def render_company_history(
    history: tuple[CompanyHistoryPoint, ...] | list[CompanyHistoryPoint],
    *,
    company_name: str,
    metric_label: str,
) -> CompanyHistoryView:
    """Build a browser-facing view without interpolation or hidden quality states."""
    points = tuple(history)
    return CompanyHistoryView(
        title=company_name,
        metric_label=metric_label,
        chart_points=tuple(_chart_point(point) for point in points),
        rows=tuple(_table_row(point) for point in points),
        empty_state="No quarter history available" if not points else None,
    )


def _chart_point(point: CompanyHistoryPoint) -> CompanyHistoryChartPoint:
    """Project one history point without smoothing a gap or outlier."""
    return CompanyHistoryChartPoint(
        quarter_label=point.quarter_label,
        value=point.value,
        is_gap=point.is_gap,
        is_outlier=point.is_outlier,
        quality_state=point.quality_state,
        calculation_status=point.calculation_status,
    )


def _table_row(point: CompanyHistoryPoint) -> CompanyHistoryRow:
    """Project visible status markers and source accessions for one quarter."""
    return CompanyHistoryRow(
        quarter_label=point.quarter_label,
        value=point.value,
        status_label=_status_label(point),
        source_accessions=point.source_accessions,
        definition_version=point.definition_version,
    )


def _status_label(point: CompanyHistoryPoint) -> str:
    """Compose bounded status labels without hiding amendment or outlier markers."""
    labels: list[str] = []
    if point.is_amendment:
        labels.append("amended")
    if point.is_restated:
        labels.append("restated")
    if point.is_outlier:
        labels.append("outlier")
    if point.calculation_status != "available":
        labels.append(point.calculation_status)
    if not labels and point.quality_state != QualityState.VERIFIED:
        labels.append(str(point.quality_state))
    return "; ".join(labels) if labels else "verified"
