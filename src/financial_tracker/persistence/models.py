"""Typed domain entities and persistence mapping metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Mapping
from uuid import UUID


class PortfolioKind(StrEnum):
    """Supported analyst-owned company collections."""

    WATCHLIST = "watchlist"
    PORTFOLIO = "portfolio"


class QualityState(StrEnum):
    """Finite quality states attached to facts and derived observations."""

    VERIFIED = "verified"
    DERIVED = "derived"
    AMBIGUOUS = "ambiguous"
    INCOMPLETE = "incomplete"
    STALE = "stale"
    SUPERSEDED = "superseded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class User:
    """Tenant-scoped authenticated subject."""

    id: UUID
    tenant_id: str
    subject_id: str
    role: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Portfolio:
    """Owner-scoped watchlist or portfolio universe."""

    id: UUID
    owner_id: UUID
    name: str
    kind: PortfolioKind
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Issuer:
    """Stable company identity resolved by CIK."""

    id: UUID
    cik: str
    legal_name: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FiscalPeriod:
    """Comparable fiscal period used to align facts across filings."""

    id: UUID
    issuer_id: UUID
    start_date: date
    end_date: date
    fiscal_year: int
    fiscal_quarter: int | None
    period_kind: str


@dataclass(frozen=True, slots=True)
class Filing:
    """Immutable filing snapshot and amendment relationship."""

    id: UUID
    issuer_id: UUID
    authority: str
    accession: str
    form_type: str
    filed_at: datetime
    accepted_at: datetime | None
    fiscal_period_id: UUID | None
    is_amendment: bool
    source_url: str
    supersedes_filing_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class FinancialFact:
    """Normalized exact-decimal fact retaining source and quality context."""

    id: UUID
    issuer_id: UUID
    filing_id: UUID
    fiscal_period_id: UUID | None
    concept: str
    value: Decimal
    unit: str
    dimensions: Mapping[str, str] = field(default_factory=dict)
    quality_state: QualityState = QualityState.VERIFIED


@dataclass(frozen=True, slots=True)
class Provenance:
    """Immutable source selector attached to a filing-backed result."""

    id: UUID
    filing_id: UUID
    accession: str
    source_url: str
    selector: str
    captured_at: datetime
    source_fact_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    """Database column metadata consumed by migration generation."""

    name: str
    sql_type: str
    nullable: bool = False
    primary_key: bool = False


TABLE_MAPPINGS: Mapping[str, tuple[ColumnMapping, ...]] = {
    "users": (
        ColumnMapping("id", "uuid", primary_key=True),
        ColumnMapping("tenant_id", "text"),
        ColumnMapping("subject_id", "text"),
        ColumnMapping("role", "text"),
        ColumnMapping("created_at", "timestamptz"),
    ),
    "portfolios": (
        ColumnMapping("id", "uuid", primary_key=True),
        ColumnMapping("owner_id", "uuid"),
        ColumnMapping("name", "text"),
        ColumnMapping("kind", "text"),
        ColumnMapping("created_at", "timestamptz"),
    ),
    "issuers": (
        ColumnMapping("id", "uuid", primary_key=True),
        ColumnMapping("cik", "text"),
        ColumnMapping("legal_name", "text"),
        ColumnMapping("created_at", "timestamptz"),
    ),
    "fiscal_periods": (
        ColumnMapping("id", "uuid", primary_key=True),
        ColumnMapping("issuer_id", "uuid"),
        ColumnMapping("start_date", "date"),
        ColumnMapping("end_date", "date"),
        ColumnMapping("fiscal_year", "integer"),
        ColumnMapping("fiscal_quarter", "smallint", nullable=True),
        ColumnMapping("period_kind", "text"),
    ),
    "filings": (
        ColumnMapping("id", "uuid", primary_key=True),
        ColumnMapping("issuer_id", "uuid"),
        ColumnMapping("authority", "text"),
        ColumnMapping("accession", "text"),
        ColumnMapping("form_type", "text"),
        ColumnMapping("filed_at", "timestamptz"),
        ColumnMapping("accepted_at", "timestamptz", nullable=True),
        ColumnMapping("fiscal_period_id", "uuid", nullable=True),
        ColumnMapping("is_amendment", "boolean"),
        ColumnMapping("source_url", "text"),
        ColumnMapping("supersedes_filing_id", "uuid", nullable=True),
    ),
    "financial_facts": (
        ColumnMapping("id", "uuid", primary_key=True),
        ColumnMapping("issuer_id", "uuid"),
        ColumnMapping("filing_id", "uuid"),
        ColumnMapping("fiscal_period_id", "uuid", nullable=True),
        ColumnMapping("concept", "text"),
        ColumnMapping("value", "numeric"),
        ColumnMapping("unit", "text"),
        ColumnMapping("dimensions", "jsonb"),
        ColumnMapping("quality_state", "text"),
    ),
    "provenance": (
        ColumnMapping("id", "uuid", primary_key=True),
        ColumnMapping("filing_id", "uuid"),
        ColumnMapping("accession", "text"),
        ColumnMapping("source_url", "text"),
        ColumnMapping("selector", "text"),
        ColumnMapping("captured_at", "timestamptz"),
        ColumnMapping("source_fact_id", "uuid", nullable=True),
    ),
}

__all__ = [
    "ColumnMapping",
    "FinancialFact",
    "Filing",
    "FiscalPeriod",
    "Issuer",
    "Portfolio",
    "PortfolioKind",
    "Provenance",
    "QualityState",
    "TABLE_MAPPINGS",
    "User",
]
