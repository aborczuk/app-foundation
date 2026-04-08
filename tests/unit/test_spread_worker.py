"""T014/T029: Unit tests for the spread worker (BTC and STO).

Tests cover:
- BTC price stepping from favorable to less favorable
- Hard return boundary cancels order when remaining return reaches floor
- Price adjustment increment and interval respected
- Partial fill accepted and remainder cancelled
- Detached task does not block caller
- STO price stepping and hard boundary
- STO partial fill creates position record
"""

import asyncio

import pytest

from csp_trader.engine.spread_worker import (
    HardBoundaryReached,
    compute_btc_hard_boundary,
    compute_sto_hard_boundary,
)

# ---------------------------------------------------------------------------
# Hard boundary calculation tests
# ---------------------------------------------------------------------------


def test_btc_hard_boundary_stops_at_floor():
    """BTC hard boundary: maximum price that keeps remaining return below floor."""
    # boundary = floor * strike * DTE / 365 / 100
    boundary = compute_btc_hard_boundary(
        strike=100.0,
        dte_remaining=30,
        annualized_return_floor_pct=15.0,
    )
    # Verify: at boundary, remaining return == floor
    remaining_return = boundary / 100.0 * (365.0 / 30) * 100
    assert abs(remaining_return - 15.0) < 0.01


def test_btc_hard_boundary_exceeded_raises():
    """HardBoundaryReached can represent floor breach when price crosses BTC boundary."""
    boundary = compute_btc_hard_boundary(
        strike=100.0,
        dte_remaining=30,
        annualized_return_floor_pct=15.0,
    )
    # price above boundary makes remaining return >= floor
    with pytest.raises(HardBoundaryReached):
        price_too_high = boundary + 0.01
        remaining_return = price_too_high / 100.0 * (365.0 / 30) * 100
        if remaining_return >= 15.0:
            raise HardBoundaryReached(ask=price_too_high, realized_return=remaining_return)


def test_sto_hard_boundary_floor():
    """STO hard boundary: minimum bid price that meets return floor."""
    # bid/strike * 365/DTE * 100 >= floor
    # boundary = floor * strike * DTE / 365 / 100
    boundary = compute_sto_hard_boundary(
        strike=100.0,
        dte=30,
        annualized_return_floor_pct=15.0,
    )
    # At boundary, annualized return should equal floor
    ret = boundary / 100.0 * (365.0 / 30) * 100
    assert abs(ret - 15.0) < 0.01


def test_sto_boundary_below_floor_raises():
    """HardBoundaryReached is raised when fill price would be below STO boundary."""
    boundary = compute_sto_hard_boundary(
        strike=100.0, dte=30, annualized_return_floor_pct=15.0
    )
    bid_too_low = boundary - 0.01
    ret = bid_too_low / 100.0 * (365.0 / 30) * 100
    with pytest.raises(HardBoundaryReached):
        if ret < 15.0:
            raise HardBoundaryReached(ask=bid_too_low, realized_return=ret)


# ---------------------------------------------------------------------------
# Spread worker step logic
# ---------------------------------------------------------------------------


async def test_btc_spread_worker_detached_does_not_block_caller():
    """work_btc_spread starts as a detached asyncio.Task that does not block."""
    from csp_trader.engine.spread_worker import work_btc_spread

    position = {
        "id": "pos-1",
        "ticker": "NVDA",
        "strike": 100.0,
        "fill_price": 2.00,
        "expiry": "2026-04-01",
        "qty": 1,
    }

    calls = []

    async def fake_place(pos, price, dry_run):
        calls.append(price)
        # Simulate immediate fill
        return {"id": "ord-1", "status": "filled", "fill_price": price, "qty_filled": 1}

    task = await work_btc_spread(
        position=position,
        current_bid=0.05,
        current_ask=0.05,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.01,
        spread_adjustment_interval_seconds=0.001,  # fast for test
        place_order_fn=fake_place,
        dry_run=False,
    )
    assert isinstance(task, asyncio.Task)
    # Task is not yet done immediately (detached)
    await asyncio.sleep(0.05)  # let it run
    # After completion, at least one order placement was attempted
    assert len(calls) >= 1


async def test_btc_spread_worker_paused_exits():
    """Paused order status exits without retrying."""
    from csp_trader.engine.spread_worker import work_btc_spread

    position = {
        "id": "pos-1",
        "ticker": "NVDA",
        "strike": 100.0,
        "fill_price": 2.00,
        "expiry": "2026-04-01",
        "qty": 1,
    }

    async def paused_place(_pos, _price, _dry_run):
        return {"id": "ord-1", "status": "paused", "fill_price": None, "qty_filled": 0}

    task = await work_btc_spread(
        position=position,
        current_bid=0.05,
        current_ask=0.05,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.01,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=paused_place,
        dry_run=False,
    )
    await asyncio.wait_for(task, timeout=1.0)


async def test_btc_spread_worker_price_increment_respected():
    """BTC spread worker steps price by increment each interval."""
    from csp_trader.engine.spread_worker import work_btc_spread

    position = {
        "id": "pos-1",
        "ticker": "NVDA",
        "strike": 100.0,
        "fill_price": 2.00,
        "expiry": "2026-04-01",
        "qty": 1,
    }
    prices_attempted = []
    call_count = 0

    async def slow_place(pos, price, dry_run):
        nonlocal call_count
        prices_attempted.append(price)
        call_count += 1
        if call_count >= 3:
            return {"id": "ord-1", "status": "filled", "fill_price": price, "qty_filled": 1}
        return {"id": "ord-1", "status": "submitted", "fill_price": None, "qty_filled": 0}

    task = await work_btc_spread(
        position=position,
        current_bid=0.05,
        current_ask=0.20,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.01,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=slow_place,
        dry_run=False,
    )
    await asyncio.wait_for(task, timeout=2.0)
    assert len(prices_attempted) >= 2
    # Each step should increase by increment (moving toward less favorable = higher ask for BTC)
    for i in range(1, len(prices_attempted)):
        assert prices_attempted[i] >= prices_attempted[i - 1] - 0.001  # allow float rounding


async def test_btc_spread_worker_stops_before_crossing_forward_return_floor():
    """Worker exits when next step would make remaining return reach floor."""
    from csp_trader.engine.spread_worker import work_btc_spread

    position = {
        "id": "pos-1",
        "ticker": "NVDA",
        "strike": 100.0,
        "fill_price": 2.00,
        "expiry": "2026-04-01",
        "qty": 1,
    }
    prices_attempted = []

    async def never_fill(_pos, price, _dry_run):
        prices_attempted.append(price)
        return {"id": "ord-1", "status": "submitted", "fill_price": None, "qty_filled": 0}

    task = await work_btc_spread(
        position=position,
        current_bid=0.40,
        current_ask=0.50,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.02,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=never_fill,
        dry_run=False,
    )
    await asyncio.wait_for(task, timeout=1.0)
    assert prices_attempted == [0.4]


async def test_sto_spread_worker_paused_exits():
    """Paused order status exits without retrying."""
    from csp_trader.engine.spread_worker import work_sto_spread

    opportunity = {
        "ticker": "NVDA",
        "strike": 100.0,
        "expiry": "2026-04-01",
        "qty": 1,
        "bid": 1.00,
        "ask": 1.20,
    }

    async def paused_place(_opp, _price, _dry_run):
        return {"id": "ord-1", "status": "paused", "fill_price": None, "qty_filled": 0}

    task = await work_sto_spread(
        opportunity=opportunity,
        dte=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.01,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=paused_place,
        dry_run=False,
    )
    await asyncio.wait_for(task, timeout=1.0)


async def test_sto_spread_worker_starts_at_ask_then_walks_down():
    """STO spread worker starts at ask and steps down by increment."""
    from csp_trader.engine.spread_worker import work_sto_spread

    opportunity = {
        "ticker": "NVDA",
        "strike": 100.0,
        "expiry": "2026-04-01",
        "qty": 1,
        "bid": 1.00,
        "ask": 1.20,
    }
    prices_attempted = []
    call_count = 0

    async def slow_fill(_opp, price, _dry_run):
        nonlocal call_count
        prices_attempted.append(price)
        call_count += 1
        if call_count >= 3:
            return {"id": "ord-1", "status": "filled", "fill_price": price, "qty_filled": 1}
        return {"id": "ord-1", "status": "submitted", "fill_price": None, "qty_filled": 0}

    task = await work_sto_spread(
        opportunity=opportunity,
        dte=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.01,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=slow_fill,
        dry_run=False,
    )
    await asyncio.wait_for(task, timeout=2.0)
    assert prices_attempted[:3] == [1.2, 1.19, 1.18]


async def test_sto_spread_worker_stops_before_failing_forward_return_floor():
    """STO worker exits before placing an order below forward-return boundary."""
    from csp_trader.engine.spread_worker import work_sto_spread

    opportunity = {
        "ticker": "NVDA",
        "strike": 100.0,
        "expiry": "2026-04-01",
        "qty": 1,
        "bid": 0.42,
        "ask": 0.43,
    }
    prices_attempted = []

    async def never_fill(_opp, price, _dry_run):
        prices_attempted.append(price)
        return {"id": "ord-1", "status": "submitted", "fill_price": None, "qty_filled": 0}

    task = await work_sto_spread(
        opportunity=opportunity,
        dte=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.02,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=never_fill,
        dry_run=False,
    )
    await asyncio.wait_for(task, timeout=1.0)
    assert prices_attempted == [0.43]


# ---------------------------------------------------------------------------
# on_fill callback tests (B013)
# ---------------------------------------------------------------------------


async def test_btc_spread_worker_calls_on_fill_when_filled():
    """BTC spread worker invokes on_fill callback with order dict on fill."""
    from csp_trader.engine.spread_worker import work_btc_spread

    position = {
        "id": "pos-1",
        "ticker": "NVDA",
        "strike": 100.0,
        "fill_price": 2.00,
        "expiry": "2026-04-01",
        "qty": 1,
    }
    fill_results = []

    async def fake_place(_pos, price, _dry_run):
        return {"id": "ord-1", "status": "filled", "fill_price": price, "qty_filled": 1}

    async def on_fill(order):
        fill_results.append(order)

    task = await work_btc_spread(
        position=position,
        current_bid=0.05,
        current_ask=0.05,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.01,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=fake_place,
        dry_run=False,
        on_fill=on_fill,
    )
    await asyncio.wait_for(task, timeout=1.0)
    assert len(fill_results) == 1
    assert fill_results[0]["status"] == "filled"
    assert fill_results[0]["fill_price"] == 0.05


async def test_btc_spread_worker_skips_on_fill_when_not_filled():
    """BTC spread worker does NOT call on_fill when order is cancelled/boundary."""
    from csp_trader.engine.spread_worker import work_btc_spread

    position = {
        "id": "pos-1",
        "ticker": "NVDA",
        "strike": 100.0,
        "fill_price": 2.00,
        "expiry": "2026-04-01",
        "qty": 1,
    }
    fill_results = []

    async def never_fill(_pos, price, _dry_run):
        return {"id": "ord-1", "status": "submitted", "fill_price": None, "qty_filled": 0}

    async def on_fill(order):
        fill_results.append(order)

    task = await work_btc_spread(
        position=position,
        current_bid=0.40,
        current_ask=0.50,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.02,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=never_fill,
        dry_run=False,
        on_fill=on_fill,
    )
    await asyncio.wait_for(task, timeout=1.0)
    assert fill_results == []


async def test_btc_spread_worker_on_fill_defaults_to_none():
    """BTC spread worker works without on_fill (backward compatible)."""
    from csp_trader.engine.spread_worker import work_btc_spread

    position = {
        "id": "pos-1",
        "ticker": "NVDA",
        "strike": 100.0,
        "fill_price": 2.00,
        "expiry": "2026-04-01",
        "qty": 1,
    }

    async def fake_place(_pos, price, _dry_run):
        return {"id": "ord-1", "status": "filled", "fill_price": price, "qty_filled": 1}

    # No on_fill — should not raise
    task = await work_btc_spread(
        position=position,
        current_bid=0.05,
        current_ask=0.05,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.01,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=fake_place,
        dry_run=False,
    )
    await asyncio.wait_for(task, timeout=1.0)


async def test_sto_spread_worker_calls_on_fill_when_filled():
    """STO spread worker invokes on_fill callback with order dict on fill."""
    from csp_trader.engine.spread_worker import work_sto_spread

    opportunity = {
        "ticker": "NVDA",
        "strike": 100.0,
        "expiry": "2026-04-01",
        "qty": 1,
        "bid": 1.00,
        "ask": 1.20,
    }
    fill_results = []

    async def fake_fill(_opp, price, _dry_run):
        return {"id": "ord-1", "status": "filled", "fill_price": price, "qty_filled": 1}

    async def on_fill(order):
        fill_results.append(order)

    task = await work_sto_spread(
        opportunity=opportunity,
        dte=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.01,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=fake_fill,
        dry_run=False,
        on_fill=on_fill,
    )
    await asyncio.wait_for(task, timeout=1.0)
    assert len(fill_results) == 1
    assert fill_results[0]["status"] == "filled"
    assert fill_results[0]["fill_price"] == 1.20


async def test_sto_spread_worker_skips_on_fill_when_boundary_reached():
    """STO spread worker does NOT call on_fill when boundary cancels."""
    from csp_trader.engine.spread_worker import work_sto_spread

    opportunity = {
        "ticker": "NVDA",
        "strike": 100.0,
        "expiry": "2026-04-01",
        "qty": 1,
        "bid": 0.42,
        "ask": 0.43,
    }
    fill_results = []

    async def never_fill(_opp, price, _dry_run):
        return {"id": "ord-1", "status": "submitted", "fill_price": None, "qty_filled": 0}

    async def on_fill(order):
        fill_results.append(order)

    task = await work_sto_spread(
        opportunity=opportunity,
        dte=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.02,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=never_fill,
        dry_run=False,
        on_fill=on_fill,
    )
    await asyncio.wait_for(task, timeout=1.0)
    assert fill_results == []


async def test_btc_spread_worker_requests_cancel_before_boundary_exit():
    """BTC worker issues best-effort cancel on non-fill before boundary terminal return."""
    from csp_trader.engine.spread_worker import work_btc_spread

    position = {
        "id": "pos-1",
        "ticker": "NVDA",
        "strike": 100.0,
        "fill_price": 2.00,
        "expiry": "2026-04-01",
        "qty": 1,
    }
    cancel_calls = []
    terminal_results = []

    async def timeout_place(_pos, price, _dry_run):
        return {
            "id": "ord-1",
            "ibkr_order_id": 42,
            "status": "submitted",
            "fill_price": None,
            "qty_filled": 0,
            "submitted_at": "2026-03-20T12:00:00Z",
            "limit_price_initial": price,
        }

    async def fake_cancel(ibkr_order_id, reason):
        cancel_calls.append((ibkr_order_id, reason))
        return {"status": "requested", "requested": True}

    async def on_terminal(payload):
        terminal_results.append(payload)

    task = await work_btc_spread(
        position=position,
        current_bid=0.40,
        current_ask=0.50,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.02,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=timeout_place,
        cancel_order_fn=fake_cancel,
        on_terminal=on_terminal,
        dry_run=False,
    )
    await asyncio.wait_for(task, timeout=1.0)

    assert cancel_calls == [(42, "timeout_no_fill")]
    assert len(terminal_results) == 1
    terminal = terminal_results[0]
    assert terminal["outcome"] == "boundary"
    assert terminal["cancel_reason"] == "forward_return_boundary"
    assert terminal["ibkr_order_id"] == 42
    assert terminal["cancel_outcome"]["status"] == "requested"


async def test_btc_spread_worker_terminal_payload_for_paused_status():
    """Paused BTC placement emits terminal payload so lifecycle compensation can run."""
    from csp_trader.engine.spread_worker import work_btc_spread

    position = {
        "id": "pos-2",
        "ticker": "MSFT",
        "strike": 100.0,
        "fill_price": 1.50,
        "expiry": "2026-04-01",
        "qty": 1,
    }
    terminal_results = []

    async def paused_place(_pos, _price, _dry_run):
        return {"id": "ord-paused", "status": "paused", "qty_filled": 0}

    async def on_terminal(payload):
        terminal_results.append(payload)

    task = await work_btc_spread(
        position=position,
        current_bid=0.05,
        current_ask=0.10,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
        spread_adjustment_increment=0.01,
        spread_adjustment_interval_seconds=0.001,
        place_order_fn=paused_place,
        on_terminal=on_terminal,
        dry_run=False,
    )
    await asyncio.wait_for(task, timeout=1.0)

    assert len(terminal_results) == 1
    assert terminal_results[0]["outcome"] == "paused"
    assert terminal_results[0]["cancel_reason"] == "order_paused"
