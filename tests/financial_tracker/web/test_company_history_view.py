"""Contract for rendering trustworthy company history view data."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from financial_tracker.persistence.models import QualityState
from financial_tracker.query.company_history import CompanyHistoryPoint


def _point(
    quarter_label: str,
    value: Decimal | None,
    *,
    quality_state: QualityState,
    freshness: str,
    source_accessions: tuple[str, ...],
    is_amendment: bool = False,
    is_restated: bool = False,
    is_outlier: bool = False,
    is_gap: bool = False,
    calculation_status: str = "available",
) -> CompanyHistoryPoint:
    """Build one history point for the view contract."""
    return CompanyHistoryPoint(
        issuer_id=uuid4(),
        fiscal_period_id=uuid4(),
        quarter_label=quarter_label,
        metric_id="operating_margin",
        definition_version="3",
        value=value,
        quality_state=quality_state,
        freshness=freshness,
        source_accessions=source_accessions,
        is_amendment=is_amendment,
        is_restated=is_restated,
        is_outlier=is_outlier,
        is_gap=is_gap,
        calculation_status=calculation_status,
    )


def test_company_history_view_preserves_gaps_outliers_and_status_labels() -> None:
    """View data keeps chart gaps and visible provenance/status markers intact."""
    from financial_tracker.web.company_history import render_company_history

    history = (
        _point(
            "2025 Q1",
            Decimal("0.12"),
            quality_state=QualityState.VERIFIED,
            freshness="fresh",
            source_accessions=("acc-q1",),
        ),
        _point(
            "2025 Q2",
            None,
            quality_state=QualityState.INCOMPLETE,
            freshness="missing",
            source_accessions=(),
            is_gap=True,
            calculation_status="missing",
        ),
        _point(
            "2025 Q3",
            Decimal("0.90"),
            quality_state=QualityState.VERIFIED,
            freshness="fresh",
            source_accessions=("acc-q3-amend",),
            is_amendment=True,
            is_outlier=True,
        ),
    )

    view = render_company_history(
        history,
        company_name="Example Holdings",
        metric_label="Operating margin",
    )

    assert view.title == "Example Holdings"
    assert [point.quarter_label for point in view.chart_points] == [
        "2025 Q1",
        "2025 Q2",
        "2025 Q3",
    ]
    assert [point.value for point in view.chart_points] == [
        Decimal("0.12"),
        None,
        Decimal("0.90"),
    ]
    assert view.chart_points[1].is_gap is True
    assert view.chart_points[2].is_outlier is True
    assert view.rows[2].status_label == "amended; outlier"
    assert view.rows[2].source_accessions == ("acc-q3-amend",)


def test_company_history_view_does_not_interpolate_an_empty_history() -> None:
    """Empty history produces an explicit state instead of synthetic chart points."""
    from financial_tracker.web.company_history import render_company_history

    view = render_company_history(
        (),
        company_name="Example Holdings",
        metric_label="Operating margin",
    )

    assert view.chart_points == ()
    assert view.rows == ()
    assert view.empty_state == "No quarter history available"
