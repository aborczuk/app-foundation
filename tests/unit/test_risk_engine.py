"""Unit tests for canonical risk-engine margin and target computations."""

from __future__ import annotations

from ib_valuation.valuation.risk_engine import (
    MarginPolicy,
    RiskEngine,
    evaluate_fundamentals_gate,
)


def test_risk_engine_applies_canonical_margin_formula() -> None:
    """Test the expected behavior."""
    engine = RiskEngine(
        MarginPolicy(
            min_pct=15.0,
            max_pct=40.0,
            final_cap_pct=95.0,
            manual_adjustment_min_pct=-20.0,
            manual_adjustment_max_pct=20.0,
            score_normalization_denominator=100.0,
            default_manual_adjustment_pct=0.0,
        )
    )

    result = engine.compute_target_price(
        base_fair_value=120.0,
        composite_risk_score=60.0,
        manual_margin_adjustment_pct=0.0,
    )

    assert result.model_margin_safety_pct == 30.0
    assert result.final_margin_safety_pct == 30.0
    assert result.target_price == 84.0


def test_risk_engine_rounds_target_price_after_margin_application() -> None:
    """Test the expected behavior."""
    engine = RiskEngine(
        MarginPolicy(
            min_pct=15.0,
            max_pct=40.0,
            final_cap_pct=95.0,
            manual_adjustment_min_pct=-20.0,
            manual_adjustment_max_pct=20.0,
            score_normalization_denominator=100.0,
            default_manual_adjustment_pct=0.0,
        )
    )

    result = engine.compute_target_price(
        base_fair_value=999.99,
        composite_risk_score=50.22,
        manual_margin_adjustment_pct=0.0,
    )

    assert result.model_margin_safety_pct == 27.555
    assert result.final_margin_safety_pct == 27.555
    assert result.target_price == 724.44


def test_risk_engine_clamps_manual_adjustment_to_policy_bounds() -> None:
    """Test the expected behavior."""
    engine = RiskEngine(
        MarginPolicy(
            min_pct=15.0,
            max_pct=40.0,
            final_cap_pct=95.0,
            manual_adjustment_min_pct=-5.0,
            manual_adjustment_max_pct=5.0,
            score_normalization_denominator=100.0,
            default_manual_adjustment_pct=0.0,
        )
    )

    high = engine.compute_target_price(
        base_fair_value=100.0,
        composite_risk_score=50.0,
        manual_margin_adjustment_pct=99.0,
    )
    low = engine.compute_target_price(
        base_fair_value=100.0,
        composite_risk_score=50.0,
        manual_margin_adjustment_pct=-99.0,
    )

    assert high.manual_margin_adjustment_pct == 5.0
    assert low.manual_margin_adjustment_pct == -5.0


def test_risk_engine_clamps_final_margin_to_min_and_cap() -> None:
    """Test the expected behavior."""
    engine = RiskEngine(
        MarginPolicy(
            min_pct=15.0,
            max_pct=40.0,
            final_cap_pct=55.0,
            manual_adjustment_min_pct=-50.0,
            manual_adjustment_max_pct=50.0,
            score_normalization_denominator=100.0,
            default_manual_adjustment_pct=0.0,
        )
    )

    floored = engine.compute_target_price(
        base_fair_value=100.0,
        composite_risk_score=0.0,
        manual_margin_adjustment_pct=-50.0,
    )
    capped = engine.compute_target_price(
        base_fair_value=100.0,
        composite_risk_score=100.0,
        manual_margin_adjustment_pct=50.0,
    )

    assert floored.final_margin_safety_pct == 15.0
    assert capped.final_margin_safety_pct == 55.0


def test_fundamentals_gate_marks_fresh_when_required_fields_present() -> None:
    """Test the expected behavior."""
    result = evaluate_fundamentals_gate(
        current_snapshot={
            "forward_pe": 24.0,
            "net_debt_ebitda": 1.2,
            "interest_coverage": 9.0,
        },
        last_valid_snapshot=None,
    )

    assert result.state == "fresh"
    assert result.snapshot["forward_pe"] == 24.0


def test_fundamentals_gate_falls_back_to_last_valid_when_current_incomplete() -> None:
    """Test the expected behavior."""
    result = evaluate_fundamentals_gate(
        current_snapshot={"forward_pe": 22.0},
        last_valid_snapshot={
            "forward_pe": 21.0,
            "net_debt_ebitda": 0.9,
            "interest_coverage": 12.0,
        },
    )

    assert result.state == "stale"
    assert result.snapshot["net_debt_ebitda"] == 0.9
    assert result.reason == "incomplete_current_snapshot_using_last_valid"


def test_fundamentals_gate_marks_unavailable_when_no_valid_snapshot_exists() -> None:
    """Test the expected behavior."""
    result = evaluate_fundamentals_gate(
        current_snapshot={"forward_pe": 22.0},
        last_valid_snapshot=None,
    )

    assert result.state == "unavailable"
    assert result.snapshot is None
    assert result.reason == "missing_required_fundamentals"
