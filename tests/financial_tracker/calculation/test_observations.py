"""Red fixture coverage for immutable metric observations."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_tracker.calculation.observations import (
    InMemoryObservationStore,
    MetricObservation,
    ObservationConflictError,
)
from financial_tracker.persistence.models import Provenance, QualityState


def _observation(*, value: str | None = "125.00", quality_state: QualityState = QualityState.VERIFIED) -> MetricObservation:
    """Build a provenance-complete observation fixture."""
    filing_id = uuid4()
    return MetricObservation(
        id=uuid4(),
        tenant_id="tenant-a",
        issuer_id=uuid4(),
        fiscal_period_id=uuid4(),
        metric_id="revenue_acceleration",
        definition_version="3",
        definition_hash="definition-v3",
        calculation_version="calc-1",
        source_snapshot_hash="snapshot-1",
        analysis_run_id=uuid4(),
        value=None if value is None else Decimal(value),
        quality_state=quality_state,
        freshness="current",
        provenance=(
            Provenance(
                id=uuid4(),
                filing_id=filing_id,
                accession="000001-25-000001",
                source_url="https://www.sec.gov/Archives/000001-25-000001",
                selector="RevenueFromContractWithCustomerExcludingAssessedTax",
                captured_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
            ),
        ),
        calculated_at=datetime(2025, 5, 2, tzinfo=timezone.utc),
    )


def test_observation_identity_is_idempotent_and_provenance_complete() -> None:
    """Retrying the same calculation identity returns one immutable observation."""
    store = InMemoryObservationStore()
    observation = _observation()
    retry_candidate = replace(observation, id=uuid4(), calculated_at=datetime(2025, 5, 3, tzinfo=timezone.utc))

    first = store.put(observation)
    retry = store.put(retry_candidate)

    assert retry is first
    assert store.all() == (observation,)
    assert first.provenance[0].accession == "000001-25-000001"


def test_observation_identity_rejects_mutation_and_preserves_history() -> None:
    """A changed result for one identity raises instead of overwriting history."""
    store = InMemoryObservationStore()
    original = _observation()
    changed = original.with_value(Decimal("130.00"))

    store.put(original)

    with pytest.raises(ObservationConflictError):
        store.put(changed)
    assert store.all() == (original,)


def test_unavailable_observation_is_stored_with_quality_and_provenance() -> None:
    """Unavailable results remain auditable rather than collapsing to a missing row."""
    store = InMemoryObservationStore()
    observation = _observation(value=None, quality_state=QualityState.INCOMPLETE)

    stored = store.put(observation)

    assert stored.value is None
    assert stored.quality_state is QualityState.INCOMPLETE
    assert stored.provenance
