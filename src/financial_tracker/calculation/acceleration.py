"""Exact-decimal calculations for filing-backed acceleration metrics."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from financial_tracker.persistence.models import QualityState


class AccelerationClassification(StrEnum):
    """Finite display states for the direction of a material acceleration."""

    ACCELERATING = "accelerating"
    DECELERATING = "decelerating"
    STABLE = "stable"
    UNAVAILABLE = "unavailable"


def calculate_operating_margin(operating_income: Decimal, revenue: Decimal) -> Decimal | None:
    """Return operating income divided by revenue, or unavailable for zero revenue."""
    if not operating_income.is_finite() or not revenue.is_finite() or revenue == 0:
        return None
    return operating_income / revenue


def calculate_improvement_streak(values: Sequence[Decimal]) -> int:
    """Count consecutive increases ending at the latest metric value."""
    if not all(value.is_finite() for value in values):
        return 0
    streak = 0
    for current, prior in zip(reversed(values), reversed(values[:-1])):
        if current <= prior:
            break
        streak += 1
    return streak


def calculate_acceleration(values: Sequence[Decimal], *, materiality: Decimal) -> Decimal | None:
    """Return the latest second difference when it meets the materiality threshold."""
    if len(values) < 3 or not materiality.is_finite() or not all(value.is_finite() for value in values):
        return None
    latest_change = values[-1] - values[-2]
    prior_change = values[-2] - values[-3]
    acceleration = latest_change - prior_change
    if abs(acceleration) < materiality:
        return None
    return acceleration


def classify_acceleration(acceleration: Decimal | None, *, materiality: Decimal) -> AccelerationClassification:
    """Classify acceleration direction while keeping missing and invalid states explicit."""
    if acceleration is None or not acceleration.is_finite() or not materiality.is_finite() or materiality < 0:
        return AccelerationClassification.UNAVAILABLE
    if acceleration == 0 or abs(acceleration) <= materiality:
        return AccelerationClassification.STABLE
    if acceleration > 0:
        return AccelerationClassification.ACCELERATING
    return AccelerationClassification.DECELERATING


def quality_state_for(*, value: Decimal | None, inputs_complete: bool, ambiguous: bool = False) -> QualityState:
    """Map calculation inputs to a finite quality state without collapsing failure to null."""
    if ambiguous:
        return QualityState.AMBIGUOUS
    if value is not None and not value.is_finite():
        return QualityState.FAILED
    if not inputs_complete or value is None:
        return QualityState.INCOMPLETE
    return QualityState.VERIFIED
