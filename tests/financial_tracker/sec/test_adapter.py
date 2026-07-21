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


class SequenceHTTPClient:
    """Transport double that returns or raises a sequence of outcomes."""

    def __init__(self, outcomes: list[httpx.Response | Exception]) -> None:
        """Store ordered HTTP outcomes for retry tests."""
        self.outcomes = outcomes
        self.calls = 0

    def get(self, url: str, *, headers: Mapping[str, str], timeout: float) -> httpx.Response:
        """Return the next outcome while recording the request count."""
        del headers, timeout
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


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


class FailingThenEdgarToolsSource:
    """Provider double that fails once before returning one filing."""

    def __init__(self) -> None:
        """Initialize the provider call counter."""
        self.calls = 0

    def get_filings(self, cik: str, forms: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
        """Raise a transient timeout once, then return a valid provider record."""
        del cik, forms
        self.calls += 1
        if self.calls == 1:
            raise httpx.ReadTimeout("provider timeout", request=httpx.Request("GET", "https://example.com"))
        return (
            {
                "accession": "0000320193-25-000007",
                "form_type": "10-K",
                "filed_at": "2025-11-06",
                "source_url": "https://www.sec.gov/Archives/edgar/data/example",
            },
        )


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


def test_rate_budget_applies_to_edgar_tools_discovery() -> None:
    """Provider discovery consumes the same bounded request budget as direct HTTP."""
    source = StubEdgarToolsSource(
        (
            {
                "accession": "0000320193-25-000004",
                "form_type": "10-K",
                "filed_at": "2025-11-03",
                "source_url": "https://www.sec.gov/Archives/edgar/data/example",
            },
        )
    )
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(max_requests=1, window_seconds=60.0),
        edgar_tools=source,
    )

    discovery.discover_filings("0000320193", forms=("10-K",))
    with pytest.raises(adapter.RateBudgetExceeded):
        discovery.discover_filings("0000320193", forms=("10-K",))

    assert len(source.calls) == 1


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


def test_direct_discovery_rejects_malformed_filing_arrays() -> None:
    """Direct SEC discovery rejects records whose parallel arrays do not align."""
    client = RecordingHTTPClient(
        {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000320193-25-000005"],
                    "form": ["10-K", "10-Q"],
                    "filingDate": ["2025-11-04"],
                    "primaryDocument": ["example.htm"],
                }
            }
        }
    )
    discovery = adapter.SECDiscoveryAdapter(policy=_policy(), http_client=client)

    with pytest.raises(ValueError, match="equal lengths"):
        discovery.discover_filings("0000320193", forms=("10-K",))


def test_provider_discovery_rejects_missing_source_url() -> None:
    """Provider discovery rejects metadata that cannot be traced to a source URL."""
    source: adapter.EdgarToolsFilingSource = StubEdgarToolsSource(
        (
            {
                "accession": "0000320193-25-000006",
                "form_type": "10-K",
                "filed_at": "2025-11-05",
            },
        )
    )
    discovery = adapter.SECDiscoveryAdapter(policy=_policy(), edgar_tools=source)

    with pytest.raises(ValueError, match="source_url"):
        discovery.discover_filings("0000320193", forms=("10-K",))


def test_retry_repeats_transient_429_with_bounded_jitter() -> None:
    """Transient rate limiting retries with the configured delay before success."""
    request = httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000320193.json")
    client = SequenceHTTPClient(
        [
            httpx.Response(429, request=request),
            httpx.Response(200, json={"filings": {"recent": {}}}, request=request),
        ]
    )
    sleeps: list[float] = []
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(
            retry_policy=adapter.SECRetryPolicy(
                max_attempts=2,
                base_delay_seconds=1.0,
                max_delay_seconds=1.0,
                jitter_ratio=0.0,
            )
        ),
        http_client=client,
        sleep=sleeps.append,
        random_value=lambda: 0.5,
    )

    discovery.fetch_submissions("0000320193")

    assert client.calls == 2
    assert sleeps == [1.0]


@pytest.mark.parametrize("status_code", [408, 500])
def test_retry_repeats_transient_http_statuses(status_code: int) -> None:
    """Timeout and server failures are retried before a successful response."""
    request = httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000320193.json")
    client = SequenceHTTPClient(
        [
            httpx.Response(status_code, request=request),
            httpx.Response(200, json={"filings": {"recent": {}}}, request=request),
        ]
    )
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(
            retry_policy=adapter.SECRetryPolicy(
                max_attempts=2,
                base_delay_seconds=0.0,
                max_delay_seconds=0.0,
                jitter_ratio=0.0,
            )
        ),
        http_client=client,
        sleep=lambda _: None,
    )

    discovery.fetch_submissions("0000320193")

    assert client.calls == 2


def test_retry_delay_never_exceeds_cap_after_positive_jitter() -> None:
    """Positive jitter cannot push a backoff above its configured maximum."""
    request = httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000320193.json")
    client = SequenceHTTPClient(
        [
            httpx.Response(429, request=request),
            httpx.Response(200, json={"filings": {"recent": {}}}, request=request),
        ]
    )
    sleeps: list[float] = []
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(
            retry_policy=adapter.SECRetryPolicy(
                max_attempts=2,
                base_delay_seconds=1.0,
                max_delay_seconds=1.0,
                jitter_ratio=1.0,
            )
        ),
        http_client=client,
        sleep=sleeps.append,
        random_value=lambda: 1.0,
    )

    discovery.fetch_submissions("0000320193")

    assert sleeps == [1.0]


def test_retry_does_not_repeat_permanent_http_errors() -> None:
    """Permanent client errors fail immediately without consuming retry attempts."""
    request = httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000320193.json")
    client = SequenceHTTPClient([httpx.Response(404, request=request)])
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(retry_policy=adapter.SECRetryPolicy(max_attempts=3)),
        http_client=client,
    )

    with pytest.raises(httpx.HTTPStatusError):
        discovery.fetch_submissions("0000320193")

    assert client.calls == 1


def test_retry_attempts_consume_the_rate_budget() -> None:
    """A retry cannot bypass the per-attempt SEC request budget."""
    request = httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000320193.json")
    client = SequenceHTTPClient([httpx.Response(429, request=request)])
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(
            max_requests=1,
            retry_policy=adapter.SECRetryPolicy(max_attempts=2),
        ),
        http_client=client,
    )

    with pytest.raises(adapter.RateBudgetExceeded):
        discovery.fetch_submissions("0000320193")

    assert client.calls == 1


def test_circuit_opens_after_exhausted_failures_and_recovers() -> None:
    """Repeated exhausted failures open the circuit until its recovery window ends."""
    request = httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000320193.json")
    client = SequenceHTTPClient(
        [
            httpx.Response(503, request=request),
            httpx.Response(503, request=request),
            httpx.Response(200, json={"filings": {"recent": {}}}, request=request),
        ]
    )
    now = [0.0]
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(
            retry_policy=adapter.SECRetryPolicy(
                max_attempts=1,
                circuit_failure_threshold=2,
                circuit_recovery_seconds=10.0,
            )
        ),
        http_client=client,
        clock=lambda: now[0],
    )

    for _ in range(2):
        with pytest.raises(httpx.HTTPStatusError):
            discovery.fetch_submissions("0000320193")
    with pytest.raises(adapter.CircuitOpenError):
        discovery.fetch_submissions("0000320193")

    now[0] = 11.0
    discovery.fetch_submissions("0000320193")
    assert client.calls == 3


def test_circuit_state_is_shared_across_direct_and_provider_sources() -> None:
    """A direct outage opens the same circuit used by the EdgarTools path."""
    request = httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000320193.json")
    client = SequenceHTTPClient([httpx.Response(503, request=request)])
    source = StubEdgarToolsSource(
        (
            {
                "accession": "0000320193-25-000008",
                "form_type": "10-K",
                "filed_at": "2025-11-07",
                "source_url": "https://www.sec.gov/Archives/edgar/data/example",
            },
        )
    )
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(
            retry_policy=adapter.SECRetryPolicy(
                max_attempts=1,
                circuit_failure_threshold=1,
                circuit_recovery_seconds=60.0,
            )
        ),
        http_client=client,
        edgar_tools=source,
    )

    with pytest.raises(httpx.HTTPStatusError):
        discovery.discover_filings("0000320193", source="direct")
    with pytest.raises(adapter.CircuitOpenError):
        discovery.discover_filings("0000320193", source="edgar_tools")

    assert client.calls == 1
    assert source.calls == []


def test_edgar_tools_path_retries_transient_provider_failures() -> None:
    """EdgarTools discovery uses the same classified retry boundary as direct HTTP."""
    source = FailingThenEdgarToolsSource()
    sleeps: list[float] = []
    discovery = adapter.SECDiscoveryAdapter(
        policy=_policy(
            retry_policy=adapter.SECRetryPolicy(
                max_attempts=2,
                base_delay_seconds=0.25,
                max_delay_seconds=0.25,
                jitter_ratio=0.0,
            )
        ),
        edgar_tools=source,
        sleep=sleeps.append,
        random_value=lambda: 0.5,
    )

    records = discovery.discover_filings("0000320193", forms=("10-K",))

    assert len(records) == 1
    assert source.calls == 2
    assert sleeps == [0.25]
