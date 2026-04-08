"""Unit tests for bull/base/bear DCF scenario math."""

from __future__ import annotations

import pytest
from ib_valuation.valuation.dcf_engine import DcfAssumptions, DcfEngine


def test_dcf_engine_returns_bull_base_bear_scenarios() -> None:
    """Test the expected behavior."""
    engine = DcfEngine()
    assumptions = DcfAssumptions(
        base_fcf_per_share=8.0,
        growth_rate_pct=12.0,
        discount_rate_pct=10.0,
        terminal_multiple=18.0,
        projection_years=5,
    )

    scenarios = engine.compute_scenarios(assumptions)

    assert set(scenarios.keys()) == {"bull", "base", "bear"}
    assert scenarios["bull"] > scenarios["base"] > scenarios["bear"]


def test_dcf_engine_base_scenario_matches_expected_math() -> None:
    """Test the expected behavior."""
    engine = DcfEngine()
    assumptions = DcfAssumptions(
        base_fcf_per_share=10.0,
        growth_rate_pct=8.0,
        discount_rate_pct=10.0,
        terminal_multiple=15.0,
        projection_years=3,
    )

    scenarios = engine.compute_scenarios(assumptions)

    # Expected value from discounted cash flows + discounted terminal value.
    assert scenarios["base"] == pytest.approx(170.89, abs=0.01)


def test_dcf_engine_rejects_invalid_discount_rate() -> None:
    """Test the expected behavior."""
    with pytest.raises(ValueError, match="discount_rate_pct"):
        DcfAssumptions(
            base_fcf_per_share=10.0,
            growth_rate_pct=8.0,
            discount_rate_pct=0.0,
            terminal_multiple=15.0,
            projection_years=3,
        )
