"""Approved fact selection and fiscal-period alignment rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from financial_tracker.persistence.models import Filing, FinancialFact, FiscalPeriod, QualityState


class PeriodClassification(StrEnum):
    """Finite classifications used to align reported fiscal periods."""

    STANDALONE_QUARTER = "standalone_quarter"
    CUMULATIVE = "cumulative"
    ANNUAL = "annual"
    UNKNOWN = "unknown"


REVENUE_CONCEPT_PRIORITY = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
OPERATING_INCOME_CONCEPT_PRIORITY = ("OperatingIncomeLoss",)
APPROVED_CONCEPT_PRIORITY = REVENUE_CONCEPT_PRIORITY + OPERATING_INCOME_CONCEPT_PRIORITY
_UNUSABLE_QUALITY_STATES = frozenset(
    {QualityState.AMBIGUOUS, QualityState.INCOMPLETE, QualityState.STALE, QualityState.SUPERSEDED, QualityState.FAILED}
)


def classify_period(period: FiscalPeriod) -> PeriodClassification:
    """Classify a period from its normalized filing-period kind."""
    normalized_kind = period.period_kind.strip().lower()
    if normalized_kind in {"quarter", "standalone", "standalone_quarter"}:
        return PeriodClassification.STANDALONE_QUARTER
    if normalized_kind in {"cumulative", "interim", "ytd"}:
        return PeriodClassification.CUMULATIVE
    if normalized_kind in {"annual", "year"}:
        return PeriodClassification.ANNUAL
    return PeriodClassification.UNKNOWN


def derive_standalone_value(
    current_value: Decimal,
    prior_value: Decimal | None,
    current_period: FiscalPeriod,
    prior_period: FiscalPeriod | None,
) -> Decimal | None:
    """Derive a standalone quarter only when the prior period proves the subtraction."""
    current_kind = classify_period(current_period)
    if current_kind is PeriodClassification.STANDALONE_QUARTER:
        return current_value
    if prior_value is None or prior_period is None or not _supports_derivation(current_period, prior_period):
        return None
    return current_value - prior_value


def select_preferred_fact(
    facts: Sequence[FinancialFact],
    *,
    filings: Mapping[UUID, Filing],
    concept_priority: Sequence[str] | None = None,
) -> FinancialFact | None:
    """Select the highest-priority usable fact and latest accepted filing snapshot."""
    priority = tuple(concept_priority) if concept_priority is not None else APPROVED_CONCEPT_PRIORITY
    rank = {concept: index for index, concept in enumerate(priority)}
    candidates = [
        fact
        for fact in facts
        if fact.concept in rank
        and fact.filing_id in filings
        and fact.quality_state not in _UNUSABLE_QUALITY_STATES
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda fact: (rank[fact.concept], -_filing_timestamp(filings[fact.filing_id])))


def _supports_derivation(current_period: FiscalPeriod, prior_period: FiscalPeriod) -> bool:
    """Return whether two periods provide valid same-series subtraction evidence."""
    if current_period.issuer_id != prior_period.issuer_id:
        return False
    if current_period.fiscal_year != prior_period.fiscal_year:
        return False
    if current_period.start_date != prior_period.start_date:
        return False
    if prior_period.end_date >= current_period.end_date:
        return False
    current_kind = classify_period(current_period)
    prior_kind = classify_period(prior_period)
    if current_kind is PeriodClassification.CUMULATIVE and prior_kind is PeriodClassification.CUMULATIVE:
        return current_period.fiscal_quarter == (prior_period.fiscal_quarter or 0) + 1
    return current_kind is PeriodClassification.ANNUAL and prior_kind is PeriodClassification.CUMULATIVE and prior_period.fiscal_quarter == 3


def _filing_timestamp(filing: Filing) -> float:
    """Return a comparable timestamp using acceptance time before filing time."""
    timestamp = filing.accepted_at or filing.filed_at
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.timestamp()
