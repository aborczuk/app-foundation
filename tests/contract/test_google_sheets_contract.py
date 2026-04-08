"""Contract tests for the Google Sheets valuations worksheet."""

from __future__ import annotations

import pytest
from ib_valuation.valuation.sheets_gateway import (
    CURATION_ACTIONS_COLUMNS,
    RANKING_COLUMNS,
    TARGETS_COLUMNS,
    VALUATIONS_COLUMNS,
    build_curation_action_row,
    build_ranking_row,
    build_target_row,
    build_valuation_row,
)


def test_valuations_row_has_contract_column_order_for_base_scenario() -> None:
    """Test the expected behavior."""
    row = build_valuation_row(
        valuation_version_id="ver-1",
        ticker="NVDA",
        scenario_type="base",
        npv_per_share=123.45,
        assumptions_payload={"discount_rate_pct": 10.0},
        created_at="2026-03-15T00:00:00Z",
    )

    assert list(row.keys()) == VALUATIONS_COLUMNS


def test_valuations_base_scenario_requires_assumptions_json() -> None:
    """Test the expected behavior."""
    row = build_valuation_row(
        valuation_version_id="ver-2",
        ticker="MSFT",
        scenario_type="base",
        npv_per_share=210.01,
        assumptions_payload={"growth_rate_pct": 8.0},
        created_at="2026-03-15T00:00:00Z",
    )

    assert row["assumptions_json"] is not None
    assert row["multiples_source_state"] is None
    assert row["unavailable_reason"] is None


def test_comparable_unavailable_allows_null_npv_and_requires_reason() -> None:
    """Test the expected behavior."""
    row = build_valuation_row(
        valuation_version_id="ver-3",
        ticker="AMD",
        scenario_type="comparable",
        npv_per_share=None,
        assumptions_payload=None,
        multiples_source_state="unavailable",
        unavailable_reason="provider_unreachable",
        created_at="2026-03-15T00:00:00Z",
    )

    assert row["npv_per_share"] is None
    assert row["multiples_source_state"] == "unavailable"
    assert row["unavailable_reason"] == "provider_unreachable"


def test_comparable_fresh_requires_npv_value() -> None:
    """Test the expected behavior."""
    try:
        build_valuation_row(
            valuation_version_id="ver-4",
            ticker="AMD",
            scenario_type="comparable",
            npv_per_share=None,
            assumptions_payload=None,
            multiples_source_state="fresh",
            unavailable_reason=None,
            created_at="2026-03-15T00:00:00Z",
        )
    except ValueError as exc:
        assert "npv_per_share" in str(exc)
    else:
        raise AssertionError("Expected ValueError for comparable fresh row missing npv_per_share")


def test_targets_row_has_contract_column_order() -> None:
    """Test the expected behavior."""
    row = build_target_row(
        target_price_id="tp-1",
        valuation_version_id="ver-1",
        ticker="NVDA",
        composite_risk_score=44.0,
        final_margin_safety_pct=26.0,
        target_price=91.24,
        manual_margin_adjustment_pct=2.5,
        computed_in_batch_id="batch-1",
        computed_at="2026-03-15T00:00:00Z",
    )

    assert list(row.keys()) == TARGETS_COLUMNS


def test_targets_row_enforces_contract_bounds() -> None:
    """Test the expected behavior."""
    with pytest.raises(ValueError, match="composite_risk_score"):
        build_target_row(
            target_price_id="tp-2",
            valuation_version_id="ver-1",
            ticker="NVDA",
            composite_risk_score=140.0,
            final_margin_safety_pct=26.0,
            target_price=91.24,
            manual_margin_adjustment_pct=0.0,
            computed_in_batch_id="batch-1",
            computed_at="2026-03-15T00:00:00Z",
        )

    with pytest.raises(ValueError, match="final_margin_safety_pct"):
        build_target_row(
            target_price_id="tp-3",
            valuation_version_id="ver-1",
            ticker="NVDA",
            composite_risk_score=44.0,
            final_margin_safety_pct=126.0,
            target_price=91.24,
            manual_margin_adjustment_pct=0.0,
            computed_in_batch_id="batch-1",
            computed_at="2026-03-15T00:00:00Z",
        )

    with pytest.raises(ValueError, match="target_price"):
        build_target_row(
            target_price_id="tp-4",
            valuation_version_id="ver-1",
            ticker="NVDA",
            composite_risk_score=44.0,
            final_margin_safety_pct=26.0,
            target_price=-1.0,
            manual_margin_adjustment_pct=0.0,
            computed_in_batch_id="batch-1",
            computed_at="2026-03-15T00:00:00Z",
        )


def test_ranking_row_has_contract_column_order() -> None:
    """Test the expected behavior."""
    row = build_ranking_row(
        batch_id="batch-1",
        ticker="NVDA",
        weighted_composite_score=82.5,
        model_rank=2,
        manual_override_rank=None,
        effective_rank=2,
        rank_state="ranked",
    )

    assert list(row.keys()) == RANKING_COLUMNS


def test_ranking_row_enforces_rank_state_enum() -> None:
    """Test the expected behavior."""
    with pytest.raises(ValueError, match="rank_state"):
        build_ranking_row(
            batch_id="batch-1",
            ticker="NVDA",
            weighted_composite_score=82.5,
            model_rank=2,
            manual_override_rank=None,
            effective_rank=2,
            rank_state="invalid",
        )


def test_curation_action_row_has_contract_column_order() -> None:
    """Test the expected behavior."""
    row = build_curation_action_row(
        action_id="act-1",
        ticker="NVDA",
        action_type="push",
        requested_at="2026-03-15T00:00:00Z",
        approved=True,
        approved_by="trader",
        approved_at="2026-03-15T00:01:00Z",
        status="approved",
        error_reason=None,
    )

    assert list(row.keys()) == CURATION_ACTIONS_COLUMNS


def test_curation_action_row_enforces_status_and_approval_requirements() -> None:
    """Test the expected behavior."""
    with pytest.raises(ValueError, match="status"):
        build_curation_action_row(
            action_id="act-2",
            ticker="NVDA",
            action_type="push",
            requested_at="2026-03-15T00:00:00Z",
            approved=False,
            approved_by=None,
            approved_at=None,
            status="not-a-status",
            error_reason=None,
        )

    with pytest.raises(ValueError, match="approved_by"):
        build_curation_action_row(
            action_id="act-3",
            ticker="NVDA",
            action_type="push",
            requested_at="2026-03-15T00:00:00Z",
            approved=True,
            approved_by=None,
            approved_at="2026-03-15T00:01:00Z",
            status="approved",
            error_reason=None,
        )
