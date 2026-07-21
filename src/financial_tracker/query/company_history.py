"""Authorized quarter-aligned company history projections."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationScope, require_issuer_access
from financial_tracker.persistence.models import Filing, FiscalPeriod, QualityState


@dataclass(frozen=True, slots=True)
class CompanyHistoryPoint:
    """One quarter of metric history with visible quality and provenance state."""

    issuer_id: UUID
    fiscal_period_id: UUID
    quarter_label: str
    metric_id: str
    definition_version: str
    value: Decimal | None
    quality_state: QualityState
    freshness: str
    source_accessions: tuple[str, ...]
    is_amendment: bool
    is_restated: bool
    is_outlier: bool
    is_gap: bool
    calculation_status: str


def read_company_history(
    scope: AuthorizationScope,
    periods: Iterable[FiscalPeriod],
    observations: Iterable[MetricObservation],
    filings: Iterable[Filing],
    *,
    issuer_id: UUID,
    metric_id: str,
    outlier_period_ids: frozenset[UUID] = frozenset(),
) -> tuple[CompanyHistoryPoint, ...]:
    """Return an authorized, quarter-complete history without smoothing data states."""
    require_issuer_access(scope, issuer_id)
    issuer_periods = sorted(
        (period for period in periods if period.issuer_id == issuer_id),
        key=lambda period: (period.end_date, period.id.hex),
    )
    issuer_filings = {
        filing.id: filing
        for filing in filings
        if filing.issuer_id == issuer_id
    }
    selected = _select_observations(observations, scope.tenant_id, issuer_id, metric_id)
    return tuple(
        _project_point(
            period,
            selected.get(period.id),
            issuer_filings,
            metric_id=metric_id,
            is_outlier=period.id in outlier_period_ids,
        )
        for period in issuer_periods
    )


def _select_observations(
    observations: Iterable[MetricObservation],
    tenant_id: str,
    issuer_id: UUID,
    metric_id: str,
) -> dict[UUID, MetricObservation]:
    """Select one deterministic observation per authorized quarter."""
    selected: dict[UUID, MetricObservation] = {}
    for observation in observations:
        if (
            observation.tenant_id != tenant_id
            or observation.issuer_id != issuer_id
            or observation.metric_id != metric_id
        ):
            continue
        current = selected.get(observation.fiscal_period_id)
        if current is None or _observation_key(observation) > _observation_key(current):
            selected[observation.fiscal_period_id] = observation
    return selected


def _observation_key(observation: MetricObservation) -> tuple[object, str]:
    """Return a stable recency key for duplicate quarter observations."""
    return observation.calculated_at, observation.analysis_run_id.hex


def _project_point(
    period: FiscalPeriod,
    observation: MetricObservation | None,
    filings: dict[UUID, Filing],
    *,
    metric_id: str,
    is_outlier: bool,
) -> CompanyHistoryPoint:
    """Project one period while retaining explicit missing and filing lineage state."""
    quarter_label = _quarter_label(period)
    if observation is None:
        return CompanyHistoryPoint(
            issuer_id=period.issuer_id,
            fiscal_period_id=period.id,
            quarter_label=quarter_label,
            metric_id=metric_id,
            definition_version="",
            value=None,
            quality_state=QualityState.INCOMPLETE,
            freshness="missing",
            source_accessions=(),
            is_amendment=False,
            is_restated=False,
            is_outlier=is_outlier,
            is_gap=True,
            calculation_status="missing",
        )

    linked_filings = tuple(
        filings[provenance.filing_id]
        for provenance in observation.provenance
        if provenance.filing_id in filings
    )
    return CompanyHistoryPoint(
        issuer_id=observation.issuer_id,
        fiscal_period_id=observation.fiscal_period_id,
        quarter_label=quarter_label,
        metric_id=observation.metric_id,
        definition_version=observation.definition_version,
        value=observation.value,
        quality_state=observation.quality_state,
        freshness=observation.freshness,
        source_accessions=tuple(item.accession for item in observation.provenance),
        is_amendment=any(filing.is_amendment for filing in linked_filings),
        is_restated=any(filing.supersedes_filing_id is not None for filing in linked_filings),
        is_outlier=is_outlier,
        is_gap=False,
        calculation_status=_calculation_status(observation),
    )


def _quarter_label(period: FiscalPeriod) -> str:
    """Format a fiscal period as a stable human-readable quarter label."""
    if period.fiscal_quarter is None:
        return str(period.end_date)
    return f"{period.fiscal_year} Q{period.fiscal_quarter}"


def _calculation_status(observation: MetricObservation) -> str:
    """Map observation quality and freshness into a bounded display status."""
    if observation.quality_state in {
        QualityState.AMBIGUOUS,
        QualityState.FAILED,
        QualityState.INCOMPLETE,
    }:
        return "invalid"
    if observation.freshness in {"recalculation-pending", "stale"}:
        return "pending"
    return "available"
