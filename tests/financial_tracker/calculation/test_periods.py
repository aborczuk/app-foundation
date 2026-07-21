"""Red fixture coverage for fiscal-period alignment and fact selection."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from financial_tracker.persistence import models
from financial_tracker.selectors import periods


def _period(
    *,
    start: date,
    end: date,
    fiscal_year: int,
    fiscal_quarter: int | None,
    period_kind: str,
) -> models.FiscalPeriod:
    """Build a fiscal-period fixture with explicit filing metadata."""
    return models.FiscalPeriod(
        id=uuid4(),
        issuer_id=uuid4(),
        start_date=start,
        end_date=end,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        period_kind=period_kind,
    )


def _fact(*, issuer_id: UUID, filing_id: UUID, fiscal_period_id: UUID, concept: str, value: str) -> models.FinancialFact:
    """Build an exact-decimal fact fixture for selector tests."""
    return models.FinancialFact(
        id=uuid4(),
        issuer_id=issuer_id,
        filing_id=filing_id,
        fiscal_period_id=fiscal_period_id,
        concept=concept,
        value=Decimal(value),
        unit="USD",
    )


def _filing(*, issuer_id: UUID, filing_id: UUID, accession: str, accepted_at: datetime, is_amendment: bool, supersedes: UUID | None = None) -> models.Filing:
    """Build an immutable filing fixture for amendment precedence tests."""
    return models.Filing(
        id=filing_id,
        issuer_id=issuer_id,
        authority="sec",
        accession=accession,
        form_type="10-Q/A" if is_amendment else "10-Q",
        filed_at=accepted_at,
        accepted_at=accepted_at,
        fiscal_period_id=None,
        is_amendment=is_amendment,
        source_url=f"https://www.sec.gov/Archives/{accession}",
        supersedes_filing_id=supersedes,
    )


def test_classifies_standalone_quarter() -> None:
    """A three-month fiscal period is eligible for quarter comparisons."""
    period = _period(
        start=date(2025, 1, 1),
        end=date(2025, 3, 31),
        fiscal_year=2025,
        fiscal_quarter=1,
        period_kind="quarter",
    )

    assert periods.classify_period(period) == "standalone_quarter"


def test_derives_cumulative_and_annual_standalone_values_only_with_evidence() -> None:
    """Supported prior cumulative evidence produces exact standalone values."""
    q2 = _period(
        start=date(2025, 1, 1),
        end=date(2025, 6, 30),
        fiscal_year=2025,
        fiscal_quarter=2,
        period_kind="cumulative",
    )
    q1 = _period(
        start=date(2025, 1, 1),
        end=date(2025, 3, 31),
        fiscal_year=2025,
        fiscal_quarter=1,
        period_kind="cumulative",
    )
    annual = _period(
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
        fiscal_year=2025,
        fiscal_quarter=None,
        period_kind="annual",
    )
    nine_months = _period(
        start=date(2025, 1, 1),
        end=date(2025, 9, 30),
        fiscal_year=2025,
        fiscal_quarter=3,
        period_kind="cumulative",
    )

    assert periods.classify_period(q2) == "cumulative"
    assert periods.classify_period(annual) == "annual"
    assert periods.derive_standalone_value(Decimal("250"), Decimal("100"), q2, q1) == Decimal("150")
    assert periods.derive_standalone_value(Decimal("400"), Decimal("300"), annual, nine_months) == Decimal("100")
    assert periods.derive_standalone_value(Decimal("250"), None, q2, q1) is None


def test_selects_documented_concept_priority() -> None:
    """The preferred approved concept wins over a lower-priority fallback."""
    issuer_id = uuid4()
    filing_id = uuid4()
    period_id = uuid4()
    preferred = _fact(
        issuer_id=issuer_id,
        filing_id=filing_id,
        fiscal_period_id=period_id,
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        value="100",
    )
    fallback = _fact(issuer_id=issuer_id, filing_id=filing_id, fiscal_period_id=period_id, concept="Revenues", value="99")

    selected = periods.select_preferred_fact(
        [fallback, preferred],
        filings={filing_id: _filing(issuer_id=issuer_id, filing_id=filing_id, accession="000001-25-000001", accepted_at=datetime(2025, 4, 1, tzinfo=timezone.utc), is_amendment=False)},
    )

    assert selected is preferred


def test_prefers_amendment_without_discarding_prior_fact() -> None:
    """An accepted amendment wins while the original accession remains available."""
    original_filing_id = uuid4()
    amendment_filing_id = uuid4()
    issuer_id = uuid4()
    period_id = uuid4()
    original = _fact(issuer_id=issuer_id, filing_id=original_filing_id, fiscal_period_id=period_id, concept="Revenues", value="100")
    amendment = _fact(issuer_id=issuer_id, filing_id=amendment_filing_id, fiscal_period_id=period_id, concept="Revenues", value="110")
    filings = {
        original_filing_id: _filing(
            issuer_id=issuer_id,
            filing_id=original_filing_id,
            accession="000001-25-000001",
            accepted_at=datetime(2025, 4, 1, tzinfo=timezone.utc),
            is_amendment=False,
        ),
        amendment_filing_id: _filing(
            issuer_id=issuer_id,
            filing_id=amendment_filing_id,
            accession="000001-25-000002",
            accepted_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
            is_amendment=True,
            supersedes=original_filing_id,
        ),
    }

    selected = periods.select_preferred_fact([original, amendment], filings=filings)

    assert selected is amendment
    assert original.value == Decimal("100")
