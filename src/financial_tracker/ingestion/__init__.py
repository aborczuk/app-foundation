"""Fixture ingestion primitives for normalized financial facts and provenance."""

from .fixtures import (
    FixtureParseError,
    NormalizedFixture,
    normalize_fixture_record,
    parse_decimal,
    parse_fixture_records,
    write_normalized_records,
)

__all__ = [
    "FixtureParseError",
    "NormalizedFixture",
    "normalize_fixture_record",
    "parse_decimal",
    "parse_fixture_records",
    "write_normalized_records",
]
