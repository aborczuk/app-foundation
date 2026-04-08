"""Unit tests for dashboard reconciliation derivation."""

from __future__ import annotations

from csp_trader.dashboard.reconciliation_view import derive_reconciliation_statuses


def test_reconciliation_marks_missing_live_records_as_degraded() -> None:
    """Test the expected behavior."""
    statuses = derive_reconciliation_statuses(
        combined_positions=[{"id": "pos-1", "ibkr_conid": 1111}],
        active_orders=[{"order_id": "ord-1", "ibkr_order_id": 2222}],
        live_positions=[{"ibkr_conid": 1111}],
        live_orders=[],
        evaluated_at="2026-03-19T00:00:00Z",
        broker_source_status="healthy",
        broker_degradation_reason=None,
    )

    by_record = {(row["record_type"], row["record_id"]): row for row in statuses}
    position_row = by_record[("position", "pos-1")]
    order_row = by_record[("order", "ord-1")]

    assert position_row["status"] == "healthy"
    assert position_row["reason"] is None
    assert order_row["status"] == "degraded"
    assert order_row["reason"] == "order_missing_in_live_broker"


def test_reconciliation_marks_all_active_records_degraded_when_broker_unavailable() -> None:
    """Test the expected behavior."""
    statuses = derive_reconciliation_statuses(
        combined_positions=[{"id": "pos-1", "ibkr_conid": 1111}],
        active_orders=[{"order_id": "ord-1", "ibkr_order_id": 2222}],
        live_positions=[],
        live_orders=[],
        evaluated_at="2026-03-19T00:00:00Z",
        broker_source_status="degraded",
        broker_degradation_reason="live_broker_unavailable",
    )

    assert len(statuses) == 2
    for row in statuses:
        assert row["status"] == "degraded"
        assert row["reason"] == "live_broker_unavailable"


def test_reconciliation_degraded_rows_always_include_reason_text() -> None:
    """Test the expected behavior."""
    statuses = derive_reconciliation_statuses(
        combined_positions=[{"id": "pos-1"}],
        active_orders=[{"order_id": "ord-1"}],
        live_positions=[],
        live_orders=[],
        evaluated_at="2026-03-19T00:00:00Z",
        broker_source_status="healthy",
        broker_degradation_reason=None,
    )

    degraded = [row for row in statuses if row["status"] == "degraded"]
    assert degraded
    assert all(isinstance(row["reason"], str) and row["reason"] for row in degraded)
