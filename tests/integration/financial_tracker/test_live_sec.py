"""Opt-in live SEC compatibility and bounded outage-path coverage."""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest

from financial_tracker.sec.adapter import (
    EdgarToolsSource,
    SECDiscoveryAdapter,
    SECRequestPolicy,
    SECRetryPolicy,
)


def _live_identity() -> str:
    """Return the operator-supplied SEC identity or skip live network tests."""
    if os.getenv("FINANCIAL_TRACKER_LIVE_SEC") != "1":
        pytest.skip("set FINANCIAL_TRACKER_LIVE_SEC=1 for bounded live SEC coverage")
    identity = os.getenv("FINANCIAL_TRACKER_SEC_IDENTITY", "").strip()
    if not identity:
        pytest.skip("set FINANCIAL_TRACKER_SEC_IDENTITY to a valid SEC User-Agent")
    return identity


def _policy(identity: str) -> SECRequestPolicy:
    """Build a short-lived policy suitable for one compatibility request."""
    return SECRequestPolicy(
        user_agent=identity,
        timeout_seconds=10.0,
        max_requests=2,
        window_seconds=1.0,
    )


def test_live_direct_sec_discovery_returns_normalized_filings() -> None:
    """Direct SEC transport returns bounded normalized Apple filing metadata."""
    identity = _live_identity()
    discovery = SECDiscoveryAdapter(policy=_policy(identity))

    records = discovery.discover_filings("0000320193", forms=("10-K",), source="direct")

    assert records
    assert all(record.form_type == "10-K" for record in records)
    assert all(record.accession and record.source_url.startswith("http") for record in records)


def test_live_edgar_tools_discovery_returns_normalized_filings() -> None:
    """EdgarTools primary extraction returns the same normalized filing contract."""
    identity = _live_identity()
    discovery = SECDiscoveryAdapter(
        policy=_policy(identity),
        edgar_tools=EdgarToolsSource(identity),
    )

    records = discovery.discover_filings("0000320193", forms=("10-K",), source="edgar_tools")

    assert records
    assert all(record.form_type == "10-K" for record in records)
    assert all(record.accession and record.source_url.startswith("http") for record in records)


def test_direct_sec_outage_stays_bounded_without_provider_fallback() -> None:
    """Direct outage stops at the retry budget and never invokes EdgarTools."""
    calls = 0
    clock = [0.0]

    def outage(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, request=request)

    class UnexpectedProvider:
        """Fail if the direct source incorrectly falls through to a provider."""

        def get_filings(self, cik: str, forms: tuple[str, ...]) -> Iterator[dict[str, str]]:
            raise AssertionError("direct SEC outage must not invoke EdgarTools")

    client = httpx.Client(transport=httpx.MockTransport(outage))

    def advance(seconds: float) -> None:
        """Advance the fake clock beyond the one-second request window."""
        clock[0] += seconds + 1.0

    discovery = SECDiscoveryAdapter(
        policy=SECRequestPolicy(
            user_agent="financial-tracker-test/1.0 contact=test@example.invalid",
            timeout_seconds=1.0,
            max_requests=2,
            window_seconds=1.0,
            retry_policy=SECRetryPolicy(
                max_attempts=2,
                base_delay_seconds=0.0,
                max_delay_seconds=0.0,
                jitter_ratio=0.0,
            ),
        ),
        http_client=client,
        edgar_tools=UnexpectedProvider(),
        clock=lambda: clock[0],
        sleep=advance,
        random_value=lambda: 0.5,
    )

    with pytest.raises(httpx.HTTPStatusError):
        discovery.discover_filings("0000320193", source="direct")

    assert calls == 2
