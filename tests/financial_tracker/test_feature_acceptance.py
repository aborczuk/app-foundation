"""Feature-level acceptance selectors for live financial-tracker boundaries."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.financial_tracker.api import test_exports, test_google_sheets
from tests.integration.financial_tracker import test_analysis, test_foundation, test_live_sec


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


def test_live_sec_direct_acceptance() -> None:
    """Run opt-in direct SEC discovery compatibility coverage."""
    test_live_sec.test_live_direct_sec_discovery_returns_normalized_filings()


def test_live_sec_edgar_tools_acceptance() -> None:
    """Run opt-in EdgarTools discovery compatibility coverage."""
    test_live_sec.test_live_edgar_tools_discovery_returns_normalized_filings()


def test_live_sec_outage_and_recovery_acceptance() -> None:
    """Run bounded SEC outage, circuit-open, and recovery coverage."""
    test_live_sec.test_direct_sec_outage_stays_bounded_without_provider_fallback()


def test_api_xlsx_parity_acceptance() -> None:
    """Run canonical API and XLSX parity, determinism, and filter coverage."""
    test_exports.test_api_projection_and_xlsx_export_preserve_the_same_rows()
    test_exports.test_xlsx_export_applies_projection_filters_before_rendering()


def test_api_xlsx_authorization_acceptance() -> None:
    """Run canonical API and XLSX authorization boundary coverage."""
    test_exports.test_api_projection_denies_an_issuer_outside_authenticated_scope()
    test_exports.test_xlsx_export_denies_rows_outside_authenticated_scope()


def test_google_sheets_delivery_acceptance() -> None:
    """Run canonical Google Sheets delivery and destination contract coverage."""
    test_google_sheets.test_google_sheets_delivery_preserves_rows_and_scope()
    test_google_sheets.test_google_sheets_delivery_rejects_owner_or_credential_mismatch()
    test_google_sheets.test_google_sheets_delivery_creates_only_the_requested_new_destination()
