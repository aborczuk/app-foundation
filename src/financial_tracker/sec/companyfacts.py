"""Extract one filing-backed revenue point from SEC company-facts JSON."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

_REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
_ALLOWED_FORMS = frozenset({"10-Q", "10-Q/A", "10-K", "10-K/A"})
_ALLOWED_PERIODS = frozenset({"Q1", "Q2", "Q3", "FY"})


@dataclass(frozen=True, slots=True)
class CompanyFactPoint:
    """One comparable SEC revenue fact with its source filing identity."""

    concept: str
    value: Decimal
    unit: str
    accession: str
    filed_at: date
    start_date: date
    end_date: date
    fiscal_year: int
    fiscal_period: str
    form_type: str


def select_latest_revenue(payload: Mapping[str, Any]) -> CompanyFactPoint:
    """Select the latest supported USD revenue fact without inventing a value."""
    facts = payload.get("facts")
    if not isinstance(facts, Mapping):
        raise ValueError("SEC company-facts payload is missing facts")
    us_gaap = facts.get("us-gaap")
    if not isinstance(us_gaap, Mapping):
        raise ValueError("SEC company-facts payload is missing us-gaap facts")

    candidates: list[CompanyFactPoint] = []
    for concept in _REVENUE_CONCEPTS:
        definition = us_gaap.get(concept)
        if not isinstance(definition, Mapping):
            continue
        units = definition.get("units")
        if not isinstance(units, Mapping):
            continue
        entries = units.get("USD")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            point = _candidate_point(concept, entry)
            if point is not None:
                candidates.append(point)
        if candidates:
            break
    if not candidates:
        raise ValueError("SEC company-facts payload has no supported quarterly revenue fact")
    return max(candidates, key=lambda item: (item.end_date, item.filed_at, item.accession))


def _candidate_point(concept: str, entry: Any) -> CompanyFactPoint | None:
    """Normalize one SEC fact entry when it has comparable period evidence."""
    if not isinstance(entry, Mapping):
        return None
    form_type = str(entry.get("form", ""))
    fiscal_period = str(entry.get("fp", ""))
    if form_type not in _ALLOWED_FORMS or fiscal_period not in _ALLOWED_PERIODS:
        return None
    try:
        start_date = date.fromisoformat(str(entry["start"]))
        end_date = date.fromisoformat(str(entry["end"]))
        filed_at = date.fromisoformat(str(entry["filed"]))
        fiscal_year = int(entry["fy"])
        value = Decimal(str(entry["val"]))
        accession = str(entry["accn"])
    except (KeyError, TypeError, ValueError):
        return None
    if not accession or end_date < start_date:
        return None
    return CompanyFactPoint(
        concept=concept,
        value=value,
        unit="USD",
        accession=accession,
        filed_at=filed_at,
        start_date=start_date,
        end_date=end_date,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form_type=form_type,
    )
