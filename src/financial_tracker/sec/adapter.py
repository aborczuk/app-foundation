"""SEC filing discovery through direct transport or an injected EdgarTools source."""

from __future__ import annotations

import random
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol, TypeVar

import httpx

_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_number}/{accession}/{document}"
ResultT = TypeVar("ResultT")


class RateBudgetExceeded(RuntimeError):
    """Raised when a request would exceed the configured SEC rate budget."""


class CircuitOpenError(RuntimeError):
    """Raised when repeated transient failures put SEC access in degraded mode."""


@dataclass(frozen=True, slots=True)
class SECRetryPolicy:
    """Bounded retry, jitter, and circuit thresholds for SEC dependencies."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0
    circuit_failure_threshold: int = 3
    circuit_recovery_seconds: float = 30.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        """Reject retry settings that could create unbounded or invalid work."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be non-negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must not be below base_delay_seconds")
        if self.circuit_failure_threshold < 1:
            raise ValueError("circuit_failure_threshold must be positive")
        if self.circuit_recovery_seconds <= 0:
            raise ValueError("circuit_recovery_seconds must be positive")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between zero and one")


class EdgarToolsFilingSource(Protocol):
    """Minimal provider boundary required from EdgarTools discovery."""

    def get_filings(
        self,
        cik: str,
        forms: tuple[str, ...],
    ) -> Iterable[Mapping[str, Any]]:
        """Return filing metadata for a CIK and a bounded form allowlist."""
        ...


class EdgarToolsSource:
    """Adapt the installed EdgarTools filing API to the provider boundary."""

    def __init__(self, identity: str) -> None:
        """Store the SEC identity EdgarTools will use for requests."""
        if not identity.strip():
            raise ValueError("identity must be non-empty")
        self._identity = identity.strip()

    def get_filings(
        self,
        cik: str,
        forms: tuple[str, ...],
    ) -> Iterable[Mapping[str, Any]]:
        """Return normalized metadata from EdgarTools' Company filing query."""
        from edgar import Company, set_identity

        set_identity(self._identity)
        for filing in Company(cik).get_filings(form=list(forms)):
            yield {
                "accession": filing.accession_no,
                "form_type": filing.form,
                "filed_at": str(filing.filing_date),
                "source_url": filing.homepage_url,
            }


class SECTransport(Protocol):
    """HTTP client boundary used by direct SEC requests and tests."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> Any:
        """Fetch one SEC resource with explicit request policy arguments."""
        ...


@dataclass(frozen=True, slots=True)
class SECRequestPolicy:
    """Identity, timeout, and bounded request budget for SEC access."""

    user_agent: str
    timeout_seconds: float = 10.0
    max_requests: int = 10
    window_seconds: float = 1.0
    retry_policy: SECRetryPolicy = field(default_factory=SECRetryPolicy)

    def __post_init__(self) -> None:
        """Reject request policies that could omit identity or bounds."""
        if not isinstance(self.user_agent, str) or not self.user_agent.strip():
            raise ValueError("user_agent must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_requests < 1:
            raise ValueError("max_requests must be positive")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")


@dataclass(frozen=True, slots=True)
class SECFilingRecord:
    """Normalized filing metadata shared by direct and EdgarTools sources."""

    accession: str
    form_type: str
    filed_at: date
    accepted_at: datetime | None
    source_url: str
    is_amendment: bool = False
    supersedes_accession: str | None = None


class SECDiscoveryAdapter:
    """Discover SEC filing metadata under one explicit request policy."""

    def __init__(
        self,
        *,
        policy: SECRequestPolicy,
        http_client: SECTransport | None = None,
        edgar_tools: EdgarToolsFilingSource | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        random_value: Callable[[], float] | None = None,
    ) -> None:
        """Bind sources, request policy, and injectable retry dependencies."""
        self._policy = policy
        self._http_client = http_client or httpx.Client()
        self._edgar_tools = edgar_tools
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._random_value = random_value or random.random
        self._request_times: deque[float] = deque()
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None

    def fetch_submissions(self, cik: str) -> Mapping[str, Any]:
        """Fetch one SEC submissions JSON document with bounded request policy."""
        normalized_cik = _normalize_cik(cik)
        return self._run_with_retry(lambda: self._fetch_submissions_once(normalized_cik))

    def discover_filings(
        self,
        cik: str,
        *,
        forms: Sequence[str] = ("10-Q", "10-K"),
    ) -> tuple[SECFilingRecord, ...]:
        """Return normalized filing records from EdgarTools or direct SEC JSON."""
        normalized_cik = _normalize_cik(cik)
        normalized_forms = _normalize_forms(forms)
        source = self._edgar_tools
        if source is not None:
            source_records = self._run_with_retry(
                lambda: self._fetch_provider_filings(
                    source, normalized_cik, normalized_forms
                )
            )
            return tuple(
                _normalize_provider_record(normalized_cik, record)
                for record in source_records
                if _form_requested(_record_form(record), normalized_forms)
            )
        return _parse_recent_filings(
            normalized_cik,
            self.fetch_submissions(normalized_cik),
            normalized_forms,
        )

    def _fetch_submissions_once(self, cik: str) -> Mapping[str, Any]:
        """Perform one direct SEC request and consume one attempt budget slot."""
        self._consume_budget()
        url = _SEC_SUBMISSIONS_URL.format(cik=cik)
        response = self._http_client.get(
            url,
            headers={"User-Agent": self._policy.user_agent.strip()},
            timeout=self._policy.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("SEC submissions response must be an object")
        return payload

    def _fetch_provider_filings(
        self,
        source: EdgarToolsFilingSource,
        cik: str,
        forms: tuple[str, ...],
    ) -> tuple[Mapping[str, Any], ...]:
        """Perform one provider discovery attempt under the shared rate budget."""
        self._consume_budget()
        return tuple(source.get_filings(cik, forms))

    def _run_with_retry(self, operation: Callable[[], "ResultT"]) -> "ResultT":
        """Run one SEC operation with classified retries and circuit tracking."""
        self._assert_circuit_closed()
        retry_policy = self._policy.retry_policy
        for attempt in range(1, retry_policy.max_attempts + 1):
            try:
                result = operation()
            except Exception as exc:
                if not _is_retryable(exc):
                    raise
                if attempt == retry_policy.max_attempts:
                    self._record_transient_failure()
                    raise
                self._sleep(self._retry_delay(attempt))
            else:
                self._record_success()
                return result
        raise AssertionError("retry loop exited without a result")

    def _assert_circuit_closed(self) -> None:
        """Reject calls while the circuit is open unless recovery time elapsed."""
        if self._circuit_opened_at is None:
            return
        if self._clock() - self._circuit_opened_at < self._policy.retry_policy.circuit_recovery_seconds:
            raise CircuitOpenError("SEC dependency circuit is open")
        self._circuit_opened_at = None
        self._consecutive_failures = 0

    def _record_transient_failure(self) -> None:
        """Open the shared circuit after enough exhausted transient operations."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._policy.retry_policy.circuit_failure_threshold:
            self._circuit_opened_at = self._clock()

    def _record_success(self) -> None:
        """Clear prior transient failure state after a successful operation."""
        self._consecutive_failures = 0
        self._circuit_opened_at = None

    def _retry_delay(self, attempt: int) -> float:
        """Calculate capped exponential backoff with bounded symmetric jitter."""
        policy = self._policy.retry_policy
        delay = min(policy.max_delay_seconds, policy.base_delay_seconds * 2 ** (attempt - 1))
        jitter = (self._random_value() * 2 - 1) * policy.jitter_ratio
        return max(0.0, delay * (1 + jitter))

    def _consume_budget(self) -> None:
        """Reserve one request slot and reject calls outside the current window."""
        now = self._clock()
        cutoff = now - self._policy.window_seconds
        while self._request_times and self._request_times[0] <= cutoff:
            self._request_times.popleft()
        if len(self._request_times) >= self._policy.max_requests:
            raise RateBudgetExceeded("SEC request rate budget exceeded")
        self._request_times.append(now)


def _normalize_cik(cik: str) -> str:
    """Return a ten-digit CIK and reject non-numeric identifiers."""
    normalized = str(cik).strip()
    if not normalized.isdecimal():
        raise ValueError("cik must contain only digits")
    return normalized.zfill(10)


def _normalize_forms(forms: Sequence[str]) -> tuple[str, ...]:
    """Normalize a non-empty form allowlist without duplicate requests."""
    normalized = tuple(dict.fromkeys(form.strip().upper() for form in forms if form.strip()))
    if not normalized:
        raise ValueError("forms must contain at least one form")
    return normalized


def _is_retryable(error: Exception) -> bool:
    """Classify transient SEC failures without retrying permanent or malformed data."""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in {408, 429} or error.response.status_code >= 500
    return isinstance(error, httpx.RequestError)


def _record_form(record: Mapping[str, Any]) -> str:
    """Read and normalize a provider record's form type."""
    form = record.get("form_type", record.get("form"))
    if not isinstance(form, str) or not form.strip():
        raise ValueError("filing record form_type must be non-empty")
    return form.strip().upper()


def _parse_recent_filings(
    cik: str,
    payload: Mapping[str, Any],
    forms: tuple[str, ...],
) -> tuple[SECFilingRecord, ...]:
    """Normalize SEC submissions recent arrays while ignoring unrequested forms."""
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, Mapping) else None
    if not isinstance(recent, Mapping):
        raise ValueError("SEC submissions response is missing filings.recent")
    accessions = _required_sequence(recent, "accessionNumber")
    form_values = _required_sequence(recent, "form")
    filed_values = _required_sequence(recent, "filingDate")
    documents = _required_sequence(recent, "primaryDocument")
    accepted_values = recent.get("acceptanceDateTime", ())
    if not isinstance(accepted_values, Sequence) or isinstance(accepted_values, str):
        accepted_values = ()
    if not (len(accessions) == len(form_values) == len(filed_values) == len(documents)):
        raise ValueError("SEC submissions filing arrays must have equal lengths")
    records: list[SECFilingRecord] = []
    for accession, form, filed, document, accepted in zip(
        accessions,
        form_values,
        filed_values,
        documents,
        (*accepted_values, *([None] * len(accessions))),
        strict=False,
    ):
        if not isinstance(accession, str) or not isinstance(form, str):
            raise ValueError("SEC filing accession and form must be strings")
        normalized_form = form.strip().upper()
        if not _form_requested(normalized_form, forms):
            continue
        if not isinstance(filed, str) or not isinstance(document, str):
            raise ValueError("SEC filing date and document must be strings")
        records.append(
            SECFilingRecord(
                accession=accession,
                form_type=normalized_form,
                filed_at=date.fromisoformat(filed),
                accepted_at=_parse_timestamp(accepted),
                source_url=_source_url(cik, accession, document),
                is_amendment=normalized_form.endswith("/A"),
            )
        )
    return tuple(records)


def _required_sequence(payload: Mapping[str, Any], key: str) -> Sequence[Any]:
    """Return one required SEC array or reject malformed provider data."""
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"SEC submissions response is missing {key}")
    return value


def _form_requested(form: str, forms: tuple[str, ...]) -> bool:
    """Match a requested base form to its SEC amendment variant."""
    return form in forms or form.removesuffix("/A") in forms


def _normalize_provider_record(cik: str, record: Mapping[str, Any]) -> SECFilingRecord:
    """Normalize one bounded EdgarTools metadata mapping."""
    accession = record.get("accession")
    filed_at = record.get("filed_at", record.get("filing_date"))
    source_url = record.get("source_url")
    if not isinstance(accession, str) or not accession.strip():
        raise ValueError("filing record accession must be non-empty")
    if not isinstance(filed_at, str):
        raise ValueError("filing record filed_at must be an ISO date")
    if not isinstance(source_url, str) or not source_url.strip():
        raise ValueError("filing record source_url must be non-empty")
    return SECFilingRecord(
        accession=accession,
        form_type=_record_form(record),
        filed_at=date.fromisoformat(filed_at),
        accepted_at=_parse_timestamp(record.get("accepted_at")),
        source_url=source_url,
        is_amendment=bool(record.get("is_amendment", _record_form(record).endswith("/A"))),
        supersedes_accession=record.get("supersedes_accession"),
    )


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an optional SEC timestamp into aware UTC time."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("filing accepted_at must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("filing accepted_at must include timezone")
    return parsed.astimezone(timezone.utc)


def _source_url(cik: str, accession: str, document: str) -> str:
    """Build the canonical SEC archive URL for one primary document."""
    return _SEC_ARCHIVES_URL.format(
        cik_number=str(int(cik)),
        accession=accession.replace("-", ""),
        document=document,
    )
