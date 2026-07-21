"""Red contract for trustworthy quarter-aligned company history."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.persistence.models import (
    Filing,
    FiscalPeriod,
    Provenance,
    QualityState,
)


def _scope(issuer_id) -> AuthorizationScope:
    """Build a server-derived scope for one tenant-owned issuer."""
    return AuthorizationScope(
        user_id=uuid4(),
        tenant_id="tenant-a",
        subject_id="subject-a",
        portfolio_ids=frozenset({uuid4()}),
        issuer_ids=frozenset({issuer_id}),
    )


def _period(issuer_id, quarter: int) -> FiscalPeriod:
    """Build one quarter-aligned period for the history fixture."""
    return FiscalPeriod(
        id=uuid4(),
        issuer_id=issuer_id,
        start_date=date(2025, quarter, 1),
        end_date=date(2025, quarter, 28),
        fiscal_year=2025,
        fiscal_quarter=quarter,
        period_kind="quarter",
    )


def _filing(issuer_id, period_id, *, amendment: bool, supersedes=None) -> Filing:
    """Build immutable filing metadata with optional amendment lineage."""
    return Filing(
        id=uuid4(),
        issuer_id=issuer_id,
        authority="sec",
        accession=f"0000000000-25-{uuid4().hex[:6]}",
        form_type="10-Q",
        filed_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
        accepted_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
        fiscal_period_id=period_id,
        is_amendment=amendment,
        source_url="https://www.sec.gov/Archives/edgar/data/example",
        supersedes_filing_id=supersedes,
    )


def _observation(
    issuer_id,
    period_id,
    filing: Filing,
    *,
    quality_state: QualityState,
    value: Decimal | None,
) -> MetricObservation:
    """Build one filing-backed observation for the history fixture."""
    captured_at = datetime(2025, 4, 1, tzinfo=timezone.utc)
    return MetricObservation(
        id=uuid4(),
        tenant_id="tenant-a",
        issuer_id=issuer_id,
        fiscal_period_id=period_id,
        metric_id="operating_margin",
        definition_version="3",
        definition_hash="hash-v3",
        definition_state="active",
        calculation_version="calc-v1",
        source_snapshot_hash="snapshot-1",
        analysis_run_id=uuid4(),
        value=value,
        quality_state=quality_state,
        freshness="fresh" if value is not None else "recalculation-pending",
        provenance=(
            Provenance(
                id=uuid4(),
                filing_id=filing.id,
                accession=filing.accession,
                source_url=filing.source_url,
                selector="OperatingIncome / Revenue",
                captured_at=captured_at,
            ),
        ),
        calculated_at=captured_at,
    )


def test_company_history_preserves_gaps_outliers_amendments_and_provenance() -> None:
    """History emits every quarter without smoothing or hiding data-quality state."""
    from financial_tracker.query.company_history import read_company_history

    issuer_id = uuid4()
    scope = _scope(issuer_id)
    periods = tuple(_period(issuer_id, quarter) for quarter in range(1, 5))
    prior_filing = _filing(issuer_id, periods[3].id, amendment=False)
    restated_filing = _filing(
        issuer_id,
        periods[3].id,
        amendment=False,
        supersedes=prior_filing.id,
    )
    filings = (
        _filing(issuer_id, periods[0].id, amendment=False),
        _filing(issuer_id, periods[1].id, amendment=True),
        prior_filing,
        restated_filing,
    )
    observations = (
        _observation(
            issuer_id,
            periods[0].id,
            filings[0],
            quality_state=QualityState.VERIFIED,
            value=Decimal("0.12"),
        ),
        _observation(
            issuer_id,
            periods[1].id,
            filings[1],
            quality_state=QualityState.FAILED,
            value=None,
        ),
        _observation(
            issuer_id,
            periods[3].id,
            filings[3],
            quality_state=QualityState.VERIFIED,
            value=Decimal("0.90"),
        ),
    )

    history = read_company_history(
        scope,
        periods,
        observations,
        filings,
        issuer_id=issuer_id,
        metric_id="operating_margin",
        outlier_period_ids=frozenset({periods[3].id}),
    )

    assert [point.quarter_label for point in history] == [
        "2025 Q1",
        "2025 Q2",
        "2025 Q3",
        "2025 Q4",
    ]
    assert history[0].source_accessions == (filings[0].accession,)
    assert history[0].definition_version == "3"
    assert history[1].is_amendment is True
    assert history[1].source_accessions == (filings[1].accession,)
    assert history[1].calculation_status == "invalid"
    assert history[2].is_gap is True
    assert history[2].value is None
    assert history[3].is_restated is True
    assert history[3].is_outlier is True
    assert history[3].source_accessions == (filings[3].accession,)
    assert history[3].value == Decimal("0.90")


def test_company_history_rejects_an_issuer_outside_authenticated_scope() -> None:
    """History authorization fails before any period or metric filtering."""
    from financial_tracker.query.company_history import read_company_history

    issuer_id = uuid4()
    foreign_issuer_id = uuid4()
    scope = _scope(issuer_id)

    with pytest.raises(AuthorizationError):
        read_company_history(
            scope,
            (),
            (),
            (),
            issuer_id=foreign_issuer_id,
            metric_id="operating_margin",
        )


def test_company_history_excludes_foreign_tenant_observations_for_authorized_issuer() -> None:
    """Tenant filtering leaves a same-issuer foreign observation as an explicit gap."""
    from financial_tracker.query.company_history import read_company_history

    issuer_id = uuid4()
    scope = _scope(issuer_id)
    period = _period(issuer_id, 1)
    filing = _filing(issuer_id, period.id, amendment=False)
    foreign_observation = replace(
        _observation(
            issuer_id,
            period.id,
            filing,
            quality_state=QualityState.VERIFIED,
            value=Decimal("0.12"),
        ),
        tenant_id="tenant-b",
    )

    history = read_company_history(
        scope,
        (period,),
        (foreign_observation,),
        (filing,),
        issuer_id=issuer_id,
        metric_id="operating_margin",
    )

    assert history[0].is_gap is True
    assert history[0].source_accessions == ()
