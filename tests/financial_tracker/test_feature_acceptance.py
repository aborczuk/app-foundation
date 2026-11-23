"""Feature-level acceptance selectors for live financial-tracker boundaries."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.financial_tracker.api import test_exports, test_google_sheets
from tests.financial_tracker.metrics import test_api as test_metric_api
from tests.integration.financial_tracker import (
    test_analysis,
    test_foundation,
    test_live_sec,
    test_metric_registry,
)


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
    test_google_sheets.test_google_sheets_delivery_rejects_owner_mismatch()
    test_google_sheets.test_google_sheets_delivery_rejects_credential_mismatch()
    test_google_sheets.test_google_sheets_delivery_creates_only_the_requested_new_destination()


def test_metric_definition_api_acceptance() -> None:
    """Run metric-definition validation, activation, retirement, and history contracts."""
    test_metric_api.test_dry_run_returns_bounded_contract_response_without_persistence()
    test_metric_api.test_invalid_definition_returns_structured_error_without_side_effect()
    test_metric_api.test_activation_is_tenant_scoped_and_history_is_immutable()
    test_metric_api.test_retirement_is_owner_authorized_and_preserves_history()
    test_metric_api.test_retirement_not_found_returns_bounded_error()
    test_metric_api.test_invalid_activation_does_not_mutate_existing_history()
    for expression in ("revenue + operating_income", "revenue / 0"):
        test_metric_api.test_api_contract_rejects_unsafe_or_invalid_calculations(expression)


def test_live_metric_definition_version_history_acceptance(
    acceptance_postgres_connection: object,
) -> None:
    """Run immutable metric-definition persistence and version selection on PostgreSQL."""
    test_metric_registry.test_metric_definition_persists_and_enforces_owner_scope(
        acceptance_postgres_connection
    )
