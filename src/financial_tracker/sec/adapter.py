"""SEC filing discovery through direct transport or an injected EdgarTools source."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Protocol

import httpx

_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_number}/{accession}/{document}"


class RateBudgetExceeded(RuntimeError):
    """Raised when a request would exceed the configured SEC rate budget."""


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
    ) -> None:
        """Bind direct transport, optional EdgarTools, and a monotonic clock."""
        self._policy = policy
        self._http_client = http_client or httpx.Client()
        self._edgar_tools = edgar_tools
        self._clock = clock or time.monotonic
        self._request_times: deque[float] = deque()

    def fetch_submissions(self, cik: str) -> Mapping[str, Any]:
        """Fetch one SEC submissions JSON document with bounded request policy."""
        normalized_cik = _normalize_cik(cik)
        self._consume_budget()
        url = _SEC_SUBMISSIONS_URL.format(cik=normalized_cik)
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

    def discover_filings(
        self,
        cik: str,
        *,
        forms: Sequence[str] = ("10-Q", "10-K"),
    ) -> tuple[SECFilingRecord, ...]:
        """Return normalized filing records from EdgarTools or direct SEC JSON."""
        normalized_cik = _normalize_cik(cik)
        normalized_forms = _normalize_forms(forms)
        if self._edgar_tools is not None:
            self._consume_budget()
            source_records = self._edgar_tools.get_filings(normalized_cik, normalized_forms)
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
