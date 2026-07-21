"""Exact-decimal fixture normalization and provenance write boundaries."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from financial_tracker.persistence.models import FinancialFact, Provenance, QualityState


class FixtureParseError(ValueError):
    """Raised when a fixture record cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class NormalizedFixture:
    """Normalized fact and immutable source provenance produced from one fixture."""

    fact: FinancialFact
    provenance: Provenance


def parse_decimal(value: Any) -> Decimal:
    """Parse an exact numeric fixture value without accepting binary floats."""
    if isinstance(value, bool) or isinstance(value, float):
        raise FixtureParseError("financial values must not be boolean or binary float values")
    if not isinstance(value, (Decimal, int, str)):
        raise FixtureParseError("financial values must be Decimal, integer, or string values")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise FixtureParseError("financial value is not a valid decimal") from exc
    if not parsed.is_finite():
        raise FixtureParseError("financial value must be finite")
    return parsed


def _required_text(record: Mapping[str, Any], field: str) -> str:
    """Read and validate a required non-empty text field."""
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise FixtureParseError(f"fixture field {field!r} must be non-empty text")
    return value.strip()


def _coerce_uuid(record: Mapping[str, Any], field: str, *, default: UUID | None = None) -> UUID:
    """Read a UUID field while preserving a useful fixture error."""
    value = record.get(field, default)
    if value is None:
        raise FixtureParseError(f"fixture field {field!r} is required")
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise FixtureParseError(f"fixture field {field!r} must be a UUID") from exc


def _coerce_datetime(value: Any) -> datetime:
    """Parse an ISO timestamp and require timezone awareness."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise FixtureParseError("captured_at must be an ISO timestamp") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise FixtureParseError("captured_at must be timezone-aware")
    return value


def normalize_fixture_record(record: Mapping[str, Any]) -> NormalizedFixture:
    """Normalize one raw fixture record into an exact fact and provenance pair."""
    if not isinstance(record, Mapping):
        raise FixtureParseError("fixture record must be a mapping")
    fact_id = _coerce_uuid(record, "fact_id", default=uuid4())
    provenance_id = _coerce_uuid(record, "provenance_id", default=uuid4())
    issuer_id = _coerce_uuid(record, "issuer_id")
    filing_id = _coerce_uuid(record, "filing_id")
    fiscal_period_id = record.get("fiscal_period_id")
    if fiscal_period_id is not None:
        fiscal_period_id = _coerce_uuid(record, "fiscal_period_id")
    dimensions = record.get("dimensions", {})
    if not isinstance(dimensions, Mapping) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in dimensions.items()):
        raise FixtureParseError("dimensions must map text keys to text values")
    captured_at = _coerce_datetime(record.get("captured_at"))
    accession = _required_text(record, "accession")
    source_url = _required_text(record, "source_url")
    try:
        quality_state = QualityState(record.get("quality_state", QualityState.VERIFIED))
    except (TypeError, ValueError) as exc:
        raise FixtureParseError("quality_state is not supported") from exc
    fact = FinancialFact(
        id=fact_id,
        issuer_id=issuer_id,
        filing_id=filing_id,
        fiscal_period_id=fiscal_period_id,
        concept=_required_text(record, "concept"),
        value=parse_decimal(record.get("value")),
        unit=_required_text(record, "unit"),
        dimensions=dict(dimensions),
        quality_state=quality_state,
    )
    provenance = Provenance(
        id=provenance_id,
        filing_id=filing_id,
        accession=accession,
        source_url=source_url,
        selector=_required_text(record, "selector"),
        captured_at=captured_at,
        source_fact_id=fact_id,
    )
    return NormalizedFixture(fact=fact, provenance=provenance)


def parse_fixture_records(records: Iterable[Mapping[str, Any]]) -> tuple[NormalizedFixture, ...]:
    """Normalize fixture records in input order without mutating source mappings."""
    return tuple(normalize_fixture_record(record) for record in records)


def write_normalized_records(
    records: Iterable[NormalizedFixture],
    *,
    fact_writer: Callable[[FinancialFact], None],
    provenance_writer: Callable[[Provenance], None],
) -> int:
    """Write normalized facts and provenance through caller-owned storage callbacks."""
    count = 0
    for record in records:
        fact_writer(record.fact)
        provenance_writer(record.provenance)
        count += 1
    return count
