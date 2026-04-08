"""B001: Order pause flag prevents order submission."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import csp_trader.ibkr.orders as orders_mod
from csp_trader.ibkr.orders import place_btc_order, place_sto_order


class _DummyIB:
    def __init__(self) -> None:
        self.place_called = False

    def placeOrder(self, *_args, **_kwargs):
        self.place_called = True
        raise AssertionError("placeOrder should not be called when order pause is active")


class _DummyClient:
    def __init__(self) -> None:
        self._order_pause = True
        self._ib = _DummyIB()


class _DummyActiveClient:
    def __init__(self) -> None:
        self._order_pause = False
        self._ib = object()


def _dummy_contract():
    contract = MagicMock()
    contract.symbol = "NVDA"
    return contract


@pytest.mark.asyncio
async def test_place_sto_order_paused_returns_status():
    """Test the expected behavior."""
    client = _DummyClient()
    opportunity = {"contract": _dummy_contract(), "position_id": "p1", "qty": 1}

    result = await place_sto_order(client, opportunity, limit_price=1.25, dry_run=False)

    assert result["status"] == "paused"
    assert client._ib.place_called is False


@pytest.mark.asyncio
async def test_place_btc_order_paused_returns_status():
    """Test the expected behavior."""
    client = _DummyClient()
    position = {"contract": _dummy_contract(), "id": "p1", "qty": 1}

    result = await place_btc_order(client, position, limit_price=0.55, dry_run=False)

    assert result["status"] == "paused"
    assert client._ib.place_called is False


@pytest.mark.asyncio
async def test_place_btc_order_builds_contract_when_missing(monkeypatch):
    """Test the expected behavior."""
    client = _DummyActiveClient()
    monkeypatch.setattr(orders_mod, "_ensure_handlers", lambda _client: None)

    position = {
        "id": "p1",
        "ticker": "NVDA",
        "expiry": "2026-03-20",
        "strike": 180.0,
        "ibkr_conid": 123456,
        "qty": 1,
    }

    result = await place_btc_order(client, position, limit_price=0.55, dry_run=True)

    assert result["status"] == "dry_run"
    assert "contract" in position
    assert position["contract"].symbol == "NVDA"
    assert position["contract"].lastTradeDateOrContractMonth == "20260320"
