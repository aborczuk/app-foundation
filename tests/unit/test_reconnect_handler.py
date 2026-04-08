"""B002: Reconnect handler wiring for resubscribe + reconciliation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import csp_trader.ibkr.reconnect as reconnect_mod
from csp_trader.ibkr.reconnect import handle_reconnect


class _DummyContract:
    conId = 123
    symbol = "NVDA"
    secType = "OPT"
    right = "P"
    strike = 100.0
    lastTradeDateOrContractMonth = "20260401"


class _DummyPosition:
    contract = _DummyContract()
    avgCost = 200.0  # ib_insync uses per-share * 100
    position = -1


class _DummyStockContract:
    conId = 999
    symbol = "NVDA"
    secType = "STK"
    right = ""
    strike = 0.0
    lastTradeDateOrContractMonth = ""


class _DummyStockPosition:
    contract = _DummyStockContract()
    avgCost = 18000.0
    position = 100


class _DummyOrderStatus:
    status = "Filled"
    avgFillPrice = 1.25


class _DummyOrder:
    orderId = 456


class _DummyTrade:
    order = _DummyOrder()
    orderStatus = _DummyOrderStatus()


class _DummyIB:
    def __init__(self) -> None:
        self.req_calls = []

    def reqMktData(self, contract, *_args, **_kwargs):
        self.req_calls.append(contract)
        return MagicMock()

    def positions(self):
        return [_DummyPosition(), _DummyStockPosition()]

    def trades(self):
        return [_DummyTrade()]


class _DummyClient:
    def __init__(self) -> None:
        self._ib = _DummyIB()
        self.trading_hours_calls = []

    async def get_trading_hours(self, contract, force_refresh: bool = False):
        self.trading_hours_calls.append(contract)
        return "20260310:0930-20260310:1600"


@pytest.mark.asyncio
async def test_handle_reconnect_resubscribes_and_reconciles(monkeypatch):
    """Test the expected behavior."""
    client = _DummyClient()
    conn = MagicMock()
    watchlist = [SimpleNamespace(ticker="NVDA")]

    open_positions = [
        {
            "id": "pos-1",
            "ticker": "NVDA",
            "strike": 100.0,
            "expiry": "2026-04-01",
        }
    ]

    monkeypatch.setattr(reconnect_mod, "get_open_positions", AsyncMock(return_value=open_positions))
    reconcile_mock = AsyncMock()
    monkeypatch.setattr(reconnect_mod, "reconcile_positions", reconcile_mock)
    dummy_stock = MagicMock()
    monkeypatch.setattr(reconnect_mod, "Stock", lambda *_a, **_k: dummy_stock)

    await handle_reconnect(client, conn, watchlist)

    assert len(client._ib.req_calls) == 1
    assert client._ib.req_calls[0].symbol == "NVDA"
    assert len(client.trading_hours_calls) == 1

    assert reconcile_mock.await_count == 1
    args, _kwargs = reconcile_mock.await_args
    assert args[0] is conn
    assert len(args[1]) == 1
    assert args[1][0]["ibkr_conid"] == 123
    assert args[2][0]["ibkr_order_id"] == 456
