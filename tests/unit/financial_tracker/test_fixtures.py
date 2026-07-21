"""Unit coverage for exact-decimal fixture normalization."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_tracker.ingestion import (
    FixtureParseError,
    IngestionResult,
    ingest_fixture_batch,
    normalize_fixture_record,
    parse_decimal,
    write_normalized_records,
)


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


class _TransactionalStore:
    """Small transactional fake used to verify coordinator ordering."""

    def __init__(self) -> None:
        self.accepted: set[tuple[str, str]] = set()
        self.facts = []
        self.provenance = []
        self.audit_events = []

    @contextmanager
    def transaction(self):
        """Expose the store as a transaction for the unit contract."""
        yield self

    def has_ingestion(self, tenant_id: str, idempotency_key: str) -> bool:
        """Check the accepted idempotency key set."""
        return (tenant_id, idempotency_key) in self.accepted

    def write_fact(self, fact) -> None:
        """Collect one fact write."""
        self.facts.append(fact)

    def write_provenance(self, provenance) -> None:
        """Collect one provenance write."""
        self.provenance.append(provenance)

    def write_audit_event(self, event) -> None:
        """Collect and accept one audit event."""
        self.audit_events.append(event)
        self.accepted.add((event.tenant_id, event.idempotency_key))


def test_ingest_fixture_batch_is_idempotent_and_audited() -> None:
    """The second delivery does not duplicate facts, provenance, or audit events."""
    store = _TransactionalStore()
    record = normalize_fixture_record(_record())
    first = ingest_fixture_batch((record,), tenant_id="tenant-a", idempotency_key="batch-1", store=store)
    second = ingest_fixture_batch((record,), tenant_id=" tenant-a ", idempotency_key=" batch-1 ", store=store)

    assert first == IngestionResult(1, False, first.audit_event)
    assert first.audit_event is not None
    assert second == IngestionResult(0, True, None)
    assert len(store.facts) == len(store.provenance) == len(store.audit_events) == 1
