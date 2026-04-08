"""Unit tests for dashboard timeline query helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from csp_trader.dashboard.contracts import LifecycleEvent
from csp_trader.dashboard.timeline_view import (
    RETENTION_CLOCK_SKEW_TOLERANCE_SECONDS,
    InvalidTimelineQuery,
    _validate_query,
    decode_cursor,
    encode_cursor,
    sort_events_for_timeline,
)


def test_timeline_sort_orders_by_timestamp_then_event_id() -> None:
    """Test the expected behavior."""
    events = [
        LifecycleEvent(
            event_id="evt-2",
            occurred_at="2026-03-19T10:00:00Z",
            entity_type="order",
            entity_id="ord-2",
            event_type="order_submitted",
            outcome_status="success",
            actor="system",
            reason=None,
        ),
        LifecycleEvent(
            event_id="evt-1",
            occurred_at="2026-03-19T10:00:00Z",
            entity_type="position",
            entity_id="pos-1",
            event_type="position_opened",
            outcome_status="success",
            actor="system",
            reason=None,
        ),
        LifecycleEvent(
            event_id="evt-3",
            occurred_at="2026-03-19T10:01:00Z",
            entity_type="order",
            entity_id="ord-3",
            event_type="order_cancelled",
            outcome_status="failed",
            actor="system",
            reason="manual_cancel",
        ),
    ]

    ordered = sort_events_for_timeline(events)
    assert [event.event_id for event in ordered] == ["evt-1", "evt-2", "evt-3"]


def test_timeline_cursor_encode_decode_roundtrip() -> None:
    """Test the expected behavior."""
    timestamp = "2026-03-19T11:15:30Z"
    cursor = encode_cursor(timestamp)
    decoded = decode_cursor(cursor)
    assert decoded == timestamp


def test_timeline_cursor_decode_rejects_invalid_values() -> None:
    """Test the expected behavior."""
    with pytest.raises(InvalidTimelineQuery):
        decode_cursor("not-base64")


def _iso(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def test_validate_query_accepts_30_day_boundary_with_small_clock_skew() -> None:
    """Test the expected behavior."""
    server_now = datetime(2026, 3, 20, 16, 0, 0, tzinfo=UTC)
    client_now = server_now - timedelta(seconds=2)

    query = _validate_query(
        cursor=None,
        limit=None,
        entity_type=None,
        outcome_status=None,
        from_ts=_iso(client_now - timedelta(days=30)),
        to_ts=_iso(client_now),
        now=server_now,
        default_limit=50,
        max_limit=200,
    )

    assert query.from_ts == client_now - timedelta(days=30)
    assert query.to_ts == client_now


def test_validate_query_rejects_30_day_boundary_outside_clock_skew_tolerance() -> None:
    """Test the expected behavior."""
    server_now = datetime(2026, 3, 20, 16, 0, 0, tzinfo=UTC)
    skew_seconds = RETENTION_CLOCK_SKEW_TOLERANCE_SECONDS + 1
    client_now = server_now - timedelta(seconds=skew_seconds)

    with pytest.raises(InvalidTimelineQuery, match="from_ts exceeds 30-day retention window"):
        _validate_query(
            cursor=None,
            limit=None,
            entity_type=None,
            outcome_status=None,
            from_ts=_iso(client_now - timedelta(days=30)),
            to_ts=_iso(client_now),
            now=server_now,
            default_limit=50,
            max_limit=200,
        )
