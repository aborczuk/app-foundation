"""Unit coverage for the financial tracker domain model seam."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from financial_tracker.persistence.models import TABLE_MAPPINGS, FinancialFact, FiscalPeriod, Portfolio, PortfolioKind, QualityState


def test_financial_fact_preserves_exact_decimal_and_quality_state() -> None:
    """Facts retain exact numeric values and explicit quality state."""
    issuer_id = uuid4()
    fact = FinancialFact(
        id=uuid4(),
        issuer_id=issuer_id,
        filing_id=uuid4(),
        fiscal_period_id=uuid4(),
        concept="Revenue",
        value=Decimal("100.10"),
        unit="USD",
        quality_state=QualityState.VERIFIED,
    )

    assert fact.value == Decimal("100.10")
    assert fact.quality_state is QualityState.VERIFIED


def test_entity_fields_match_persistence_mappings() -> None:
    """Core entity construction exposes the fields migration mappings name."""
    now = datetime.now(timezone.utc)
    portfolio = Portfolio(uuid4(), uuid4(), "Growth", PortfolioKind.PORTFOLIO, now)
    period = FiscalPeriod(uuid4(), uuid4(), date(2025, 1, 1), date(2025, 3, 31), 2025, 1, "quarter")

    assert portfolio.kind is PortfolioKind.PORTFOLIO
    assert period.fiscal_quarter == 1
    assert {column.name for column in TABLE_MAPPINGS["portfolios"]} >= {"id", "owner_id", "kind"}
