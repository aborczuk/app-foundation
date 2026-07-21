"""Fixture ingestion primitives for normalized financial facts and provenance."""

from .fixtures import (
    FixtureParseError,
    IngestionAuditEvent,
    IngestionResult,
    NormalizedFixture,
    TransactionalFixtureStore,
    ingest_fixture_batch,
    normalize_fixture_record,
    parse_decimal,
    parse_fixture_records,
    write_normalized_records,
)

__all__ = [
    "FixtureParseError",
    "IngestionAuditEvent",
    "IngestionResult",
    "NormalizedFixture",
    "TransactionalFixtureStore",
    "ingest_fixture_batch",
    "normalize_fixture_record",
    "parse_decimal",
    "parse_fixture_records",
    "write_normalized_records",
]
