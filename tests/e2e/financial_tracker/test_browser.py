"""Opt-in browser-server smoke test for the local MVP."""

from __future__ import annotations

import os

import httpx
import pytest


@pytest.mark.contract
def test_browser_proxy_exposes_live_aapl_result() -> None:
    """Verify the Vite page and its proxied API expose the same filing result."""
    if os.getenv("FINANCIAL_TRACKER_E2E") != "1":
        pytest.skip("set FINANCIAL_TRACKER_E2E=1 while API and Vite are running")

    base_url = os.getenv("FINANCIAL_TRACKER_BROWSER_URL", "http://127.0.0.1:5173")
    page = httpx.get(f"{base_url}/", timeout=5)
    data = httpx.get(f"{base_url}/api/v1/dashboard?ticker=AAPL", timeout=5)

    assert page.status_code == 200
    assert "Financial Acceleration Tracker" in page.text
    assert data.status_code == 200
    row = data.json()[0]
    assert row["ticker"] == "AAPL"
    assert row["quality_state"] == "verified"
    assert row["accession"]
    assert row["source_url"].startswith("https://www.sec.gov/")
