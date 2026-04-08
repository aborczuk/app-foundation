"""T013: Unit tests for the position monitor.

Tests cover:
- Position at profit target triggers close
- Position not at target returns hold
- Position with stale data is skipped
- Multiple positions evaluated independently
- Only 'open' state positions checked
"""


from csp_trader.engine.position_monitor import evaluate_positions
from csp_trader.engine.rules import CloseSignal


def _make_position(
    id: str = "pos-1",
    ticker: str = "NVDA",
    strike: float = 100.0,
    expiry: str = "2026-04-01",
    qty: int = 1,
    fill_price: float = 2.00,
    lifecycle_state: str = "open",
    opened_at: str = "2026-03-01T10:00:00Z",
) -> dict:
    """Build a minimal position dict for testing."""
    return {
        "id": id,
        "ticker": ticker,
        "strike": strike,
        "expiry": expiry,
        "qty": qty,
        "fill_price": fill_price,
        "lifecycle_state": lifecycle_state,
        "opened_at": opened_at,
        "ibkr_conid": 12345,
        "premium_collected": fill_price * qty * 100,
        "closed_at": None,
        "assigned_at": None,
        "realized_pnl": None,
        "open_order_id": None,
        "close_order_id": None,
        "created_at": opened_at,
        "updated_at": opened_at,
    }


async def test_position_at_profit_target_triggers_close():
    """A position whose remaining return is below the floor should produce a CloseSignal."""
    position = _make_position(fill_price=2.00, strike=100.0)
    # DTE ~10 days from now; bid=$0.05 → very low remaining return → triggers close
    market_data = {
        "pos-1": {"ask": 0.05, "bid": 0.04, "stale": False, "dte_remaining": 10},
    }

    results = await evaluate_positions(
        open_positions=[position],
        market_data=market_data,
        annualized_return_floor_pct=15.0,
    )

    assert len(results) == 1
    pos_id, signal = results[0]
    assert pos_id == "pos-1"
    assert isinstance(signal, CloseSignal)


async def test_position_not_at_target_returns_hold():
    """A position with high remaining return should NOT produce a CloseSignal."""
    position = _make_position(fill_price=2.00, strike=100.0)
    # ask=$1.80, DTE=14 → high remaining return → hold
    market_data = {
        "pos-1": {"ask": 1.80, "bid": 1.75, "stale": False, "dte_remaining": 14},
    }

    results = await evaluate_positions(
        open_positions=[position],
        market_data=market_data,
        annualized_return_floor_pct=15.0,
    )

    assert len(results) == 0


async def test_stale_data_position_is_skipped():
    """Position with stale market data must be skipped (not in results)."""
    position = _make_position()
    market_data = {
        "pos-1": {"ask": 0.05, "bid": 0.04, "stale": True, "dte_remaining": 10},
    }

    results = await evaluate_positions(
        open_positions=[position],
        market_data=market_data,
        annualized_return_floor_pct=15.0,
    )

    assert len(results) == 0


async def test_multiple_positions_evaluated_independently():
    """Each position is evaluated on its own merits."""
    pos_close = _make_position(id="pos-close", fill_price=2.00, strike=100.0)
    pos_hold = _make_position(id="pos-hold", fill_price=2.00, strike=100.0)

    market_data = {
        "pos-close": {"ask": 0.05, "bid": 0.04, "stale": False, "dte_remaining": 10},
        "pos-hold": {"ask": 1.80, "bid": 1.75, "stale": False, "dte_remaining": 14},
    }

    results = await evaluate_positions(
        open_positions=[pos_close, pos_hold],
        market_data=market_data,
        annualized_return_floor_pct=15.0,
    )

    result_ids = {r[0] for r in results}
    assert "pos-close" in result_ids
    assert "pos-hold" not in result_ids


async def test_only_open_state_positions_checked():
    """Positions in closing/closed/assigned states are not evaluated."""
    positions = [
        _make_position(id="pos-open", lifecycle_state="open"),
        _make_position(id="pos-closing", lifecycle_state="closing"),
        _make_position(id="pos-closed", lifecycle_state="closed"),
        _make_position(id="pos-assigned", lifecycle_state="assigned"),
    ]
    market_data = {
        p["id"]: {"ask": 0.05, "bid": 0.04, "stale": False, "dte_remaining": 10}
        for p in positions
    }

    results = await evaluate_positions(
        open_positions=positions,
        market_data=market_data,
        annualized_return_floor_pct=15.0,
    )

    result_ids = {r[0] for r in results}
    # Only the 'open' position should appear
    assert "pos-open" in result_ids
    assert "pos-closing" not in result_ids
    assert "pos-closed" not in result_ids
    assert "pos-assigned" not in result_ids
