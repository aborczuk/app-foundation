"""B004: Trading hours cached per symbol with optional refresh."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from csp_trader.ibkr.client import IBKRClient


class _DummyDetails:
    def __init__(self, trading_hours: str) -> None:
        self.tradingHours = trading_hours


class _DummyContract:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol


@pytest.mark.asyncio
async def test_trading_hours_cached_and_refreshable():
    """Test the expected behavior."""
    client = IBKRClient()
    contract = _DummyContract("NVDA")

    details_calls = []

    async def fake_req(_contract):
        details_calls.append(_contract)
        return [_DummyDetails("20260310:0930-20260310:1600")]

    client._ib.reqContractDetailsAsync = AsyncMock(side_effect=fake_req)

    # First call hits IBKR
    first = await client.get_trading_hours(contract)
    # Second call uses cache
    second = await client.get_trading_hours(contract)
    # Force refresh hits IBKR again
    third = await client.get_trading_hours(contract, force_refresh=True)

    assert first == second == third
    assert len(details_calls) == 2
