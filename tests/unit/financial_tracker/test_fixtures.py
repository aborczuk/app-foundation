"""Unit coverage for exact-decimal fixture normalization."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from financial_tracker.ingestion import FixtureParseError, normalize_fixture_record, parse_decimal, write_normalized_records


def _record() -> dict[str, object]:
    """Return a minimal valid filing-backed fixture record."""
    return {
        "issuer_id": str(uuid4()),
        "filing_id": str(uuid4()),
        "accession": "0000000001-25-000001",
        "source_url": "https://example.test/filing",
        "selector": "facts.Revenue.us-gaap:Revenues",
        "concept": "revenue",
        "value": "123.4500",
        "unit": "USD",
        "dimensions": {"segment": "North America"},
    }


def test_fixture_normalization_preserves_exact_decimal_and_provenance() -> None:
    """Normalized output retains decimal scale and source selector details."""
    normalized = normalize_fixture_record(_record())
    assert normalized.fact.value == Decimal("123.4500")
    assert normalized.fact.dimensions == {"segment": "North America"}
    assert normalized.provenance.source_fact_id == normalized.fact.id
    assert normalized.provenance.selector == "facts.Revenue.us-gaap:Revenues"


def test_parse_decimal_rejects_binary_float() -> None:
    """Binary floats cannot enter the exact financial fact path."""
    with pytest.raises(FixtureParseError):
        parse_decimal(1.25)
    with pytest.raises(FixtureParseError):
        parse_decimal("NaN")


def test_fixture_normalization_rejects_unknown_quality_state() -> None:
    """Quality states remain within the finite domain taxonomy."""
    record = _record()
    record["quality_state"] = "unknown"
    with pytest.raises(FixtureParseError):
        normalize_fixture_record(record)


def test_write_normalized_records_calls_both_storage_boundaries() -> None:
    """The writer emits each fact and its provenance exactly once."""
    record = normalize_fixture_record(_record())
    facts = []
    provenance = []
    assert write_normalized_records((record,), fact_writer=facts.append, provenance_writer=provenance.append) == 1
    assert facts == [record.fact]
    assert provenance == [record.provenance]
