"""Feature-level acceptance selectors for live financial-tracker boundaries."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.integration.financial_tracker import test_analysis, test_foundation


@pytest.fixture()
def acceptance_postgres_connection() -> Iterator[object]:
    """Yield one live PostgreSQL connection for the analysis acceptance path."""
    psycopg = test_analysis._load_psycopg()
    with psycopg.connect(test_analysis._require_database_url(), connect_timeout=5) as connection:
        yield connection


def test_real_postgres_foundation_acceptance() -> None:
    """Run the canonical live foundation identity and provenance scenario."""
    test_foundation.test_foundation_identity_and_provenance_constraints()


def test_real_postgres_analysis_acceptance(acceptance_postgres_connection: object) -> None:
    """Run the canonical filing-backed analysis scenario against live PostgreSQL."""
    test_analysis.test_filing_backed_analysis_runs_against_live_postgres(
        acceptance_postgres_connection
    )
