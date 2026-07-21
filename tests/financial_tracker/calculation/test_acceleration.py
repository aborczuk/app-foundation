"""Red fixture coverage for exact-decimal acceleration calculations."""

from decimal import Decimal

from financial_tracker.calculation import acceleration
from financial_tracker.persistence.models import QualityState


def test_calculates_operating_margin_without_binary_float_rounding() -> None:
    """Margin preserves exact decimal arithmetic and rejects zero revenue."""
    assert acceleration.calculate_operating_margin(Decimal("25.00"), Decimal("100.00")) == Decimal("0.25")
    assert acceleration.calculate_operating_margin(Decimal("25.00"), Decimal("0.00")) is None


def test_counts_only_consecutive_improvement_streak() -> None:
    """A decline ends the streak rather than being counted as improvement."""
    values = [Decimal("100"), Decimal("110"), Decimal("125"), Decimal("120")]

    assert acceleration.calculate_improvement_streak(values) == 0
    assert acceleration.calculate_improvement_streak(values[:3]) == 2


def test_calculates_second_difference_and_applies_materiality() -> None:
    """Acceleration is the change in sequential improvement, thresholded exactly."""
    values = [Decimal("100"), Decimal("110"), Decimal("125")]

    assert acceleration.calculate_acceleration(values, materiality=Decimal("1")) == Decimal("5")
    assert acceleration.calculate_acceleration(values, materiality=Decimal("10")) is None


def test_returns_only_finite_quality_states() -> None:
    """Valid, incomplete, and ambiguous inputs map to explicit enum states."""
    verified = acceleration.quality_state_for(value=Decimal("1"), inputs_complete=True)
    incomplete = acceleration.quality_state_for(value=None, inputs_complete=False)
    ambiguous = acceleration.quality_state_for(value=Decimal("1"), inputs_complete=True, ambiguous=True)

    assert verified is QualityState.VERIFIED
    assert incomplete is QualityState.INCOMPLETE
    assert ambiguous is QualityState.AMBIGUOUS
