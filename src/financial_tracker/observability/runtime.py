"""Runtime observability event, metric, and alert contracts."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import uuid4

MAX_MESSAGE_EXCERPT = 256
MAX_ARTIFACT_URI = 512
_ARTIFACT_SCHEMES = frozenset({"artifact", "https", "s3"})
_SOURCES = frozenset({"direct_sec", "edgar_tools", "fixture"})
_METRIC_LABELS = {
    "financial_tracker_refresh_total": frozenset({"outcome"}),
    "financial_tracker_refresh_duration_seconds": frozenset({"outcome"}),
    "financial_tracker_filing_total": frozenset({"source", "outcome"}),
    "financial_tracker_work_items_total": frozenset({"state", "kind"}),
    "financial_tracker_queue_age_seconds": frozenset({"tenant_scope"}),
    "financial_tracker_sec_requests_total": frozenset({"source", "outcome"}),
    "financial_tracker_sec_circuit_open_total": frozenset({"source"}),
    "financial_tracker_dead_letter_total": frozenset({"kind", "category"}),
}
_SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|api[_-]?key|token|password|secret)\b\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """Bounded structured event shared by refresh and work-item operations."""

    operation: str
    tenant_scope: str
    source: str
    occurred_at: datetime
    correlation_id: str
    issuer_id: str | None
    accession: str | None
    failure_category: str | None
    retryable: bool | None
    attempt: int
    work_state: str | None
    message_excerpt: str
    artifact_uri: str | None


@dataclass(frozen=True, slots=True)
class MetricSample:
    """One metric observation with a validated low-cardinality label set."""

    name: str
    value: float
    labels: tuple[tuple[str, str], ...]
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class RuntimeAlert:
    """Actionable alert output linked to the originating runtime context."""

    kind: str
    severity: str
    message: str
    correlation_id: str
    artifact_uri: str | None


class RuntimeObservability:
    """Collect bounded runtime events and allowlisted metric samples in memory."""

    def __init__(self) -> None:
        """Create an empty collector owned by the current runtime process."""
        self._events: list[RuntimeEvent] = []
        self._metrics: list[MetricSample] = []

    @property
    def events(self) -> tuple[RuntimeEvent, ...]:
        """Return captured events without exposing mutable collector state."""
        return tuple(self._events)

    @property
    def metrics(self) -> tuple[MetricSample, ...]:
        """Return captured metric samples without exposing mutable collector state."""
        return tuple(self._metrics)

    def record_event(
        self,
        *,
        operation: str,
        tenant_scope: str,
        source: str,
        occurred_at: datetime | None = None,
        correlation_id: str | None = None,
        issuer_id: str | None = None,
        accession: str | None = None,
        failure_category: str | None = None,
        retryable: bool | None = None,
        attempt: int = 0,
        work_state: str | None = None,
        message: str = "",
        artifact_uri: str | None = None,
    ) -> RuntimeEvent:
        """Record one UTC event while bounding and redacting diagnostic context."""
        normalized_source = _required_text(source, "source")
        if normalized_source not in _SOURCES:
            raise ValueError(f"unsupported source: {normalized_source}")
        if attempt < 0:
            raise ValueError("attempt must be non-negative")
        event = RuntimeEvent(
            operation=_required_text(operation, "operation"),
            tenant_scope=_required_text(tenant_scope, "tenant_scope"),
            source=normalized_source,
            occurred_at=_utc_datetime(occurred_at or datetime.now(timezone.utc), "occurred_at"),
            correlation_id=_correlation_id(correlation_id),
            issuer_id=issuer_id,
            accession=accession,
            failure_category=failure_category,
            retryable=retryable,
            attempt=attempt,
            work_state=work_state,
            message_excerpt=_redact_excerpt(message),
            artifact_uri=_safe_artifact_uri(artifact_uri),
        )
        self._events.append(event)
        return event

    def record_metric(
        self,
        name: str,
        *,
        value: int | float,
        labels: Mapping[str, str],
        recorded_at: datetime | None = None,
    ) -> MetricSample:
        """Record one allowlisted metric with exactly its documented dimensions."""
        expected_labels = _METRIC_LABELS.get(name)
        if expected_labels is None:
            raise ValueError(f"unsupported metric: {name}")
        if isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError("metric value must be finite numeric")
        if set(labels) != expected_labels:
            raise ValueError(f"metric labels for {name} must match the documented dimensions")
        normalized_labels = tuple(sorted((_required_text(key, "label"), _required_text(item, key)) for key, item in labels.items()))
        for key, item in normalized_labels:
            if key == "source" and item not in _SOURCES:
                raise ValueError(f"unsupported source label: {item}")
        sample = MetricSample(
            name=name,
            value=float(value),
            labels=normalized_labels,
            recorded_at=_utc_datetime(recorded_at or datetime.now(timezone.utc), "recorded_at"),
        )
        self._metrics.append(sample)
        return sample


@dataclass(frozen=True, slots=True)
class AlertPolicy:
    """Threshold policy for actionable scheduled-refresh runtime alerts."""

    circuit_open_after: timedelta = timedelta(minutes=5)
    queue_age_objective: timedelta = timedelta(minutes=15)
    repeated_refresh_failures: int = 3

    def __post_init__(self) -> None:
        """Reject non-actionable threshold configuration at construction time."""
        if self.circuit_open_after <= timedelta(0):
            raise ValueError("circuit_open_after must be positive")
        if self.queue_age_objective <= timedelta(0):
            raise ValueError("queue_age_objective must be positive")
        if self.repeated_refresh_failures < 1:
            raise ValueError("repeated_refresh_failures must be positive")

    def evaluate(
        self,
        *,
        now: datetime,
        circuit_open_since: datetime | None,
        queue_age: timedelta | None,
        refresh_failures: int,
        dead_letter_delta: int,
        correlation_id: str,
        artifact_uri: str | None,
    ) -> tuple[RuntimeAlert, ...]:
        """Evaluate bounded runtime state against the four operational thresholds."""
        current = _utc_datetime(now, "now")
        alerts: list[RuntimeAlert] = []
        if circuit_open_since is not None and current - _utc_datetime(circuit_open_since, "circuit_open_since") >= self.circuit_open_after:
            alerts.append(_alert("sec_circuit_open", "critical", "SEC circuit has remained open", correlation_id, artifact_uri))
        if queue_age is not None and queue_age > self.queue_age_objective:
            alerts.append(_alert("queue_age_exceeded", "warning", "eligible work queue is beyond its objective", correlation_id, artifact_uri))
        if refresh_failures >= self.repeated_refresh_failures:
            alerts.append(_alert("refresh_failures", "warning", "refresh failures exceeded the repetition threshold", correlation_id, artifact_uri))
        if dead_letter_delta > 0:
            alerts.append(_alert("dead_letter_rising", "critical", "dead-letter count increased", correlation_id, artifact_uri))
        return tuple(alerts)


def _required_text(value: str, field_name: str) -> str:
    """Normalize and validate one required observability text field."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _correlation_id(value: str | None) -> str:
    """Reuse a caller correlation ID or create one for a new operation."""
    return _required_text(value, "correlation_id") if value is not None else str(uuid4())


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    """Normalize aware timestamps to UTC and reject ambiguous naive values."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _redact_excerpt(message: str) -> str:
    """Collapse and redact common secret assignments before applying the size bound."""
    collapsed = " ".join(message.split())
    redacted = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", collapsed)
    return redacted[:MAX_MESSAGE_EXCERPT]


def _safe_artifact_uri(value: str | None) -> str | None:
    """Validate a bounded credential-free URI before exposing it in telemetry."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > MAX_ARTIFACT_URI or any(char.isspace() or ord(char) < 32 for char in normalized):
        raise ValueError("artifact_uri must be bounded and whitespace-free")
    try:
        parsed = urlsplit(normalized)
    except ValueError as exc:
        raise ValueError("artifact_uri must be a valid URI") from exc
    if parsed.scheme.lower() not in _ARTIFACT_SCHEMES or parsed.username or parsed.password:
        raise ValueError("artifact_uri must use a safe credential-free scheme")
    return normalized


def _alert(
    kind: str,
    severity: str,
    message: str,
    correlation_id: str,
    artifact_uri: str | None,
) -> RuntimeAlert:
    """Build one consistent correlated alert record."""
    return RuntimeAlert(kind, severity, message, _required_text(correlation_id, "correlation_id"), _safe_artifact_uri(artifact_uri))
