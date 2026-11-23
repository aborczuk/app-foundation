"""Authorized filing-analysis projection and response contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationScope, require_issuer_access
from financial_tracker.persistence.models import QualityState


@dataclass(frozen=True, slots=True)
class AnalysisRow:
    """Safe observation projection shared by API, dashboard, and export adapters."""

    issuer_id: UUID
    fiscal_period_id: UUID
    metric_id: str
    definition_version: str
    definition_hash: str
    definition_state: str
    value: Decimal | None
    quality_state: QualityState
    analysis_run_id: UUID
    freshness: str
    source_accessions: tuple[str, ...]
    source_fact_selectors: tuple[str, ...]
    calculated_at: datetime
    correlation_id: str | None


def read_analysis(
    scope: AuthorizationScope,
    observations: tuple[MetricObservation, ...] | list[MetricObservation],
    *,
    issuer_id: UUID,
    correlation_id: str | None = None,
) -> tuple[AnalysisRow, ...]:
    """Return only tenant-owned observations for an issuer in the server-derived scope."""
    require_issuer_access(scope, issuer_id)
    return tuple(
        _project_observation(observation, correlation_id=correlation_id)
        for observation in observations
        if observation.tenant_id == scope.tenant_id and observation.issuer_id == issuer_id
    )


def _project_observation(observation: MetricObservation, *, correlation_id: str | None) -> AnalysisRow:
    """Project an observation without exposing internal provider payloads or stack details."""
    return AnalysisRow(
        issuer_id=observation.issuer_id,
        fiscal_period_id=observation.fiscal_period_id,
        metric_id=observation.metric_id,
        definition_version=observation.definition_version,
        definition_hash=observation.definition_hash,
        definition_state=observation.definition_state,
        value=observation.value,
        quality_state=observation.quality_state,
        analysis_run_id=observation.analysis_run_id,
        freshness=observation.freshness,
        source_accessions=tuple(item.accession for item in observation.provenance),
        source_fact_selectors=tuple(item.selector for item in observation.provenance),
        calculated_at=observation.calculated_at,
        correlation_id=correlation_id,
    )
