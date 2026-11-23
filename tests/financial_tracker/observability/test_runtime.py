"""Contract coverage for runtime events, metrics, and alert policy."""

from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2025, 5, 1, 12, tzinfo=timezone.utc)


def test_events_keep_correlation_and_redact_bounded_failure_context() -> None:
    """Failure events retain operational identifiers without leaking credentials."""
    from financial_tracker.observability.runtime import RuntimeObservability

    runtime = RuntimeObservability()
    event = runtime.record_event(
        operation="filing_discovery",
        tenant_scope="tenant-a",
        source="direct_sec",
        occurred_at=NOW,
        correlation_id="corr-1",
        issuer_id="issuer-1",
        accession="0001-23-000001",
        failure_category="rate_limit",
        retryable=True,
        attempt=2,
        work_state="retry_wait",
        message="Authorization: Bearer secret-token; request failed",
        artifact_uri="artifact://failure-1",
    )

    assert event.correlation_id == "corr-1"
    assert event.occurred_at == NOW
    assert event.source == "direct_sec"
    assert event.retryable is True
    assert event.attempt == 2
    assert "secret-token" not in event.message_excerpt
    assert "Bearer" not in event.message_excerpt
    assert runtime.events == (event,)


def test_artifact_uris_are_bounded_and_cannot_embed_credentials() -> None:
    """Telemetry links use safe opaque references rather than credential-bearing URLs."""
    from financial_tracker.observability.runtime import AlertPolicy, RuntimeObservability

    runtime = RuntimeObservability()
    with pytest.raises(ValueError, match="artifact_uri"):
        runtime.record_event(
            operation="refresh",
            tenant_scope="tenant-a",
            source="direct_sec",
            message="failed",
            artifact_uri="https://user:password@example.com/failure",
        )

    with pytest.raises(ValueError, match="artifact_uri"):
        AlertPolicy().evaluate(
            now=NOW,
            circuit_open_since=NOW - timedelta(minutes=6),
            queue_age=None,
            refresh_failures=0,
            dead_letter_delta=0,
            correlation_id="corr-uri",
            artifact_uri="artifact://" + ("x" * 512),
        )


def test_metrics_allow_only_documented_low_cardinality_dimensions() -> None:
    """Metric samples preserve approved dimensions and reject issuer-level labels."""
    from financial_tracker.observability.runtime import RuntimeObservability

    runtime = RuntimeObservability()
    sample = runtime.record_metric(
        "financial_tracker_refresh_total",
        value=1,
        labels={"outcome": "success"},
        recorded_at=NOW,
    )

    assert sample.value == 1
    assert sample.labels == (("outcome", "success"),)
    with pytest.raises(ValueError, match="label"):
        runtime.record_metric(
            "financial_tracker_filing_total",
            value=1,
            labels={"source": "direct_sec", "accession": "0001-23-000001"},
            recorded_at=NOW,
        )


def test_alert_policy_covers_sustained_runtime_failure_signals() -> None:
    """Alert output is bounded, correlated, and covers the four operational signals."""
    from financial_tracker.observability.runtime import AlertPolicy

    policy = AlertPolicy(
        circuit_open_after=timedelta(minutes=5),
        queue_age_objective=timedelta(minutes=10),
        repeated_refresh_failures=3,
    )
    alerts = policy.evaluate(
        now=NOW,
        circuit_open_since=NOW - timedelta(minutes=6),
        queue_age=timedelta(minutes=11),
        refresh_failures=3,
        dead_letter_delta=1,
        correlation_id="corr-2",
        artifact_uri="artifact://failure-2",
    )

    assert {alert.kind for alert in alerts} == {
        "sec_circuit_open",
        "queue_age_exceeded",
        "refresh_failures",
        "dead_letter_rising",
    }
    assert all(alert.correlation_id == "corr-2" for alert in alerts)
    assert all(alert.artifact_uri == "artifact://failure-2" for alert in alerts)
