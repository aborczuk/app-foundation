"""Immutable metric observation domain and idempotent write boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from financial_tracker.persistence.models import Provenance, QualityState


class ObservationConflictError(ValueError):
    """Raised when a calculation identity is reused with different content."""


@dataclass(frozen=True, slots=True)
class MetricObservation:
    """Immutable calculated or unavailable result pinned to source and definition versions."""

    id: UUID
    tenant_id: str
    issuer_id: UUID
    fiscal_period_id: UUID
    metric_id: str
    definition_version: str
    definition_hash: str
    definition_state: str
    calculation_version: str
    source_snapshot_hash: str
    analysis_run_id: UUID
    value: Decimal | None
    quality_state: QualityState
    freshness: str
    provenance: tuple[Provenance, ...]
    calculated_at: datetime

    def __post_init__(self) -> None:
        """Reject observations that cannot be reproduced or safely displayed."""
        required_text = (
            self.tenant_id,
            self.metric_id,
            self.definition_version,
            self.definition_hash,
            self.definition_state,
            self.calculation_version,
            self.source_snapshot_hash,
            self.freshness,
        )
        if any(not value.strip() for value in required_text):
            raise ValueError("observation identity and freshness fields must be non-empty")
        if self.value is not None and not self.value.is_finite():
            raise ValueError("observation value must be finite")
        if not self.provenance:
            raise ValueError("observation requires filing provenance")
        if any(
            not provenance.accession.strip()
            or not provenance.source_url.strip()
            or not provenance.selector.strip()
            or not isinstance(provenance.captured_at, datetime)
            or provenance.captured_at.tzinfo is None
            for provenance in self.provenance
        ):
            raise ValueError("observation provenance fields must be complete")

    @property
    def identity_key(self) -> tuple[object, ...]:
        """Return the immutable key used for idempotent observation writes."""
        return (
            self.tenant_id,
            self.issuer_id,
            self.fiscal_period_id,
            self.metric_id,
            self.definition_version,
            self.definition_hash,
            self.calculation_version,
            self.source_snapshot_hash,
            self.analysis_run_id,
        )

    @property
    def content_key(self) -> tuple[object, ...]:
        """Return semantic content used to compare idempotent retries."""
        provenance_key = tuple(
            (
                provenance.filing_id,
                provenance.accession,
                provenance.source_url,
                provenance.selector,
                provenance.captured_at,
                provenance.source_fact_id,
            )
            for provenance in self.provenance
        )
        return (self.value, self.quality_state, self.freshness, self.definition_state, provenance_key)

    def with_value(self, value: Decimal | None) -> Self:
        """Return a new observation candidate with the same calculation identity."""
        return replace(self, value=value)


class InMemoryObservationStore:
    """Small append-only reference store for calculation and contract tests."""

    def __init__(self) -> None:
        """Create an empty observation store."""
        self._observations: dict[tuple[object, ...], MetricObservation] = {}

    def put(self, observation: MetricObservation) -> MetricObservation:
        """Insert an observation once or reject a changed retry for the same identity."""
        existing = self._observations.get(observation.identity_key)
        if existing is not None:
            if existing.content_key != observation.content_key:
                raise ObservationConflictError("observation identity already has different content")
            return existing
        self._observations[observation.identity_key] = observation
        return observation

    def all(self) -> tuple[MetricObservation, ...]:
        """Return observations in insertion order without exposing mutable storage."""
        return tuple(self._observations.values())
