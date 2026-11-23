"""Opt-in live SEC-to-PostgreSQL application seam verification."""

from __future__ import annotations

import os

import pytest

from financial_tracker.runtime import FinancialTrackerRuntime


@pytest.mark.contract
def test_live_aapl_refresh_round_trips_to_dashboard() -> None:
    """Verify one real SEC refresh is durable and visible through the read seam."""
    if os.getenv("FINANCIAL_TRACKER_LIVE_SEC") != "1":
        pytest.skip("set FINANCIAL_TRACKER_LIVE_SEC=1 to enable the live SEC seam")
    if not os.getenv("FINANCIAL_TRACKER_TEST_DATABASE_URL") and not os.getenv("FINANCIAL_TRACKER_DATABASE_URL"):
        pytest.skip("set a Financial Tracker PostgreSQL URL to enable the live database seam")

    runtime = FinancialTrackerRuntime.from_environment()
    summary = runtime.refresh("AAPL")
    rows = runtime.dashboard("AAPL")

    assert summary.ticker == "AAPL"
    assert summary.accession
    assert rows
    assert rows[0]["accession"] == summary.accession
    assert rows[0]["metric_id"] == "revenue"
