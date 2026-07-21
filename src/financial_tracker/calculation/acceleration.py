"""Exact-decimal calculations for filing-backed acceleration metrics."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from financial_tracker.persistence.models import QualityState


def calculate_operating_margin(operating_income: Decimal, revenue: Decimal) -> Decimal | None:
    """Return operating income divided by revenue, or unavailable for zero revenue."""
    if revenue == 0:
        return None
    return operating_income / revenue


def calculate_improvement_streak(values: Sequence[Decimal]) -> int:
    """Count consecutive increases ending at the latest metric value."""
    streak = 0
    for current, prior in zip(reversed(values), reversed(values[:-1])):
        if current <= prior:
            break
        streak += 1
    return streak


def calculate_acceleration(values: Sequence[Decimal], *, materiality: Decimal) -> Decimal | None:
    """Return the latest second difference when it meets the materiality threshold."""
    if len(values) < 3:
        return None
    latest_change = values[-1] - values[-2]
    prior_change = values[-2] - values[-3]
    acceleration = latest_change - prior_change
    if abs(acceleration) < materiality:
        return None
    return acceleration


def quality_state_for(*, value: Decimal | None, inputs_complete: bool, ambiguous: bool = False) -> QualityState:
    """Map calculation inputs to a finite quality state without collapsing failure to null."""
    if ambiguous:
        return QualityState.AMBIGUOUS
    if value is not None and not value.is_finite():
        return QualityState.FAILED
    if not inputs_complete or value is None:
        return QualityState.INCOMPLETE
    return QualityState.VERIFIED
