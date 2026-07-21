"""Red parity and authorization contracts for API and XLSX projections."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

import pytest

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.persistence.models import Provenance, QualityState
from financial_tracker.query.analysis import read_analysis


def _scope(issuer_id) -> AuthorizationScope:
    """Build a server-derived scope for one tenant-owned issuer."""
    return AuthorizationScope(
        user_id=uuid4(),
        tenant_id="tenant-a",
        subject_id="subject-a",
        portfolio_ids=frozenset({uuid4()}),
        issuer_ids=frozenset({issuer_id}),
    )


def _observation(issuer_id, *, quality_state: QualityState, freshness: str) -> MetricObservation:
    """Build one deterministic observation containing visible provenance."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    filing_id = uuid4()
    return MetricObservation(
        id=uuid4(),
        tenant_id="tenant-a",
        issuer_id=issuer_id,
        fiscal_period_id=uuid4(),
        metric_id="revenue_acceleration",
        definition_version="3",
        definition_hash="hash-v3",
        definition_state="active",
        calculation_version="calc-v1",
        source_snapshot_hash="snapshot-1",
        analysis_run_id=uuid4(),
        value=Decimal("12.50"),
        quality_state=quality_state,
        freshness=freshness,
        provenance=(
            Provenance(
                id=uuid4(),
                filing_id=filing_id,
                accession="0000320193-25-000001",
                source_url="https://www.sec.gov/Archives/edgar/data/example",
                selector="Revenue",
                captured_at=now,
            ),
        ),
        calculated_at=now,
    )


def test_api_projection_and_xlsx_export_preserve_the_same_rows() -> None:
    """XLSX consumes the authorized API rows without losing state or provenance."""
    from financial_tracker.exports.xlsx import XlsxExportService

    issuer_id = uuid4()
    scope = _scope(issuer_id)
    observations = [
        _observation(issuer_id, quality_state=QualityState.VERIFIED, freshness="fresh"),
        _observation(
            issuer_id,
            quality_state=QualityState.STALE,
            freshness="recalculation-pending",
        ),
    ]
    rows = read_analysis(scope, observations, issuer_id=issuer_id, correlation_id="corr-1")
    exporter = XlsxExportService()

    artifact = exporter.export(
        rows,
        scope=scope,
        filters={"issuer_id": str(issuer_id), "metric_id": "revenue_acceleration"},
        requested_by=scope.user_id,
        schema_version="1",
    )

    assert artifact.rows == rows
    assert artifact.manifest.schema_version == "1"
    assert artifact.manifest.filters == {
        "issuer_id": str(issuer_id),
        "metric_id": "revenue_acceleration",
    }
    assert artifact.manifest.source_accessions == (
        "0000320193-25-000001",
        "0000320193-25-000001",
    )
    assert artifact.manifest.content_hash == sha256(artifact.content).hexdigest()
    assert artifact.content


def test_api_projection_denies_an_issuer_outside_authenticated_scope() -> None:
    """Unauthorized company access fails without returning financial rows."""
    issuer_id = uuid4()
    foreign_issuer_id = uuid4()
    scope = _scope(issuer_id)

    with pytest.raises(AuthorizationError):
        read_analysis(
            scope,
            [_observation(foreign_issuer_id, quality_state=QualityState.VERIFIED, freshness="fresh")],
            issuer_id=foreign_issuer_id,
        )


def test_xlsx_export_denies_rows_outside_authenticated_scope() -> None:
    """Export authorization cannot be bypassed with foreign rows or filters."""
    from financial_tracker.exports.xlsx import XlsxExportService

    issuer_id = uuid4()
    owner_scope = _scope(issuer_id)
    foreign_scope = _scope(uuid4())
    rows = read_analysis(
        owner_scope,
        [_observation(issuer_id, quality_state=QualityState.VERIFIED, freshness="fresh")],
        issuer_id=issuer_id,
    )

    with pytest.raises(AuthorizationError):
        XlsxExportService().export(
            rows,
            scope=foreign_scope,
            filters={"issuer_id": str(issuer_id)},
            requested_by=foreign_scope.user_id,
            schema_version="1",
        )
