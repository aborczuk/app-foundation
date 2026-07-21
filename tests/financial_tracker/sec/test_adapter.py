"""Unit contracts for the SEC discovery adapter request policy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
import pytest

from financial_tracker.sec import adapter


class RecordingHTTPClient:
    """Small transport double that records policy arguments without network I/O."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        """Store the JSON payload returned by each request."""
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, headers: Mapping[str, str], timeout: float) -> httpx.Response:
        """Record one request and return a successful JSON response."""
        self.calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        return httpx.Response(200, json=self.payload, request=httpx.Request("GET", url))


class StubEdgarToolsSource:
    """Injected EdgarTools seam used to prove provider delegation is explicit."""

    def __init__(self, records: tuple[Mapping[str, Any], ...]) -> None:
        """Store provider records for deterministic discovery tests."""
        self.records = records
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def get_filings(self, cik: str, forms: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
        """Return provider records while recording the normalized lookup request."""
        self.calls.append((cik, forms))
        return self.records


def _policy(**overrides: Any) -> adapter.SECRequestPolicy:
    """Build a valid request policy with a test identity."""
    values: dict[str, Any] = {
        "user_agent": "Financial Tracker test@example.com",
        "timeout_seconds": 3.5,
        "max_requests": 5,
        "window_seconds": 60.0,
    }
    values.update(overrides)
    return adapter.SECRequestPolicy(**values)


def test_direct_transport_applies_identity_and_timeout_policy() -> None:
    """Direct SEC requests include the required identity and bounded timeout."""
    client = RecordingHTTPClient({"filings": {"recent": {}}})
    discovery = adapter.SECDiscoveryAdapter(policy=_policy(), http_client=client)

    discovery.fetch_submissions("0000320193")

    assert client.calls == [
        {
            "url": "https://data.sec.gov/submissions/CIK0000320193.json",
            "headers": {"User-Agent": "Financial Tracker test@example.com"},
            "timeout": 3.5,
        }
    ]


def test_rate_budget_rejects_requests_beyond_window_limit() -> None:
    """The adapter refuses a request once its configured SEC budget is spent."""
    client = RecordingHTTPClient({"filings": {"recent": {}}})
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(max_requests=1, window_seconds=60.0),
        http_client=client,
    )

    discovery.fetch_submissions("0000320193")
    with pytest.raises(adapter.RateBudgetExceeded):
        discovery.fetch_submissions("0000320193")

    assert len(client.calls) == 1


def test_direct_submission_discovery_normalizes_recent_filings() -> None:
    """Direct SEC submissions become stable filing records with source URLs."""
    client = RecordingHTTPClient(
        {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-25-000001"],
                    "form": ["10-Q/A"],
                    "filingDate": ["2025-04-30"],
                    "acceptanceDateTime": ["2025-04-30T16:00:00.000Z"],
                    "primaryDocument": ["example.htm"],
                }
            }
        }
    )
    discovery = adapter.SECDiscoveryAdapter(policy=_policy(), http_client=client)

    records = discovery.discover_filings("0000320193", forms=("10-Q",))

    assert len(records) == 1
    assert records[0].accession == "0000320193-25-000001"
    assert records[0].form_type == "10-Q/A"
    assert records[0].is_amendment is True
    assert records[0].source_url.endswith("/000032019325000001/example.htm")


def test_edgar_tools_source_is_an_injected_discovery_seam() -> None:
    """EdgarTools records are preferred when an explicit provider is supplied."""
    source: adapter.EdgarToolsFilingSource = StubEdgarToolsSource(
        (
            {
                "accession": "0000320193-25-000002",
                "form_type": "10-K",
                "filed_at": "2025-11-01",
                "source_url": "https://www.sec.gov/Archives/edgar/data/example",
            },
        )
    )
    client = RecordingHTTPClient({"filings": {"recent": {}}})
    discovery = adapter.SECDiscoveryAdapter(policy=_policy(), http_client=client, edgar_tools=source)

    records = discovery.discover_filings("0000320193", forms=("10-K",))

    assert records[0].accession == "0000320193-25-000002"
    assert client.calls == []
    assert source.calls == [("0000320193", ("10-K",))]


def test_concrete_edgar_tools_source_uses_installed_package_api(monkeypatch: pytest.MonkeyPatch) -> None:
    """The concrete adapter sets identity and maps EdgarTools filing metadata."""
    import edgar

    identities: list[str] = []

    class FakeFiling:
        accession_no = "0000320193-25-000003"
        form = "10-K"
        filing_date = "2025-11-02"
        homepage_url = "https://www.sec.gov/Archives/edgar/data/example"

    class FakeCompany:
        def __init__(self, cik: str) -> None:
            assert cik == "0000320193"

        def get_filings(self, *, form: list[str]) -> tuple[FakeFiling, ...]:
            assert form == ["10-K"]
            return (FakeFiling(),)

    monkeypatch.setattr(edgar, "set_identity", identities.append)
    monkeypatch.setattr(edgar, "Company", FakeCompany)

    records = tuple(
        adapter.EdgarToolsSource("Financial Tracker test@example.com").get_filings(
            "0000320193", ("10-K",)
        )
    )

    assert identities == ["Financial Tracker test@example.com"]
    assert records[0]["accession"] == "0000320193-25-000003"


def test_policy_rejects_missing_identity_or_unbounded_timeout() -> None:
    """Invalid SEC identity and timeout settings fail before any request."""
    with pytest.raises(ValueError, match="user_agent"):
        _policy(user_agent="")
    with pytest.raises(ValueError, match="timeout_seconds"):
        _policy(timeout_seconds=0)
