"""B006: Market data snapshot retrieval behavior."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from ib_async import Option

from csp_trader.ibkr.market_data import get_market_data, get_option_chain


class _DummyTicker:
    def __init__(self, bid, ask, *, contract=None, market_price=None, last=None, close=None, time=None):
        self.bid = bid
        self.ask = ask
        self.contract = contract
        self._market_price = market_price
        self.last = last
        self.close = close
        self.time = time

    def marketPrice(self):
        return self._market_price


class _DummyIB:
    def __init__(self, ticker):
        self.ticker = ticker
        self.cancel_calls = []

    def reqMktData(self, contract, *_args, **_kwargs):
        self.contract = contract
        return self.ticker

    def cancelMktData(self, contract):
        self.cancel_calls.append(contract)


class _DummyClient:
    def __init__(self, ticker):
        self._ib = _DummyIB(ticker)


class _DummyContract:
    symbol = "NVDA"


@pytest.mark.asyncio
async def test_cancel_called_on_success(monkeypatch):
    """Test the expected behavior."""
    ticker = _DummyTicker(bid=1.0, ask=1.1)
    client = _DummyClient(ticker)
    contract = _DummyContract()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    result = await get_market_data(client, contract)

    assert result["stale"] is False
    # Snapshot requests auto-expire; helper should not issue explicit cancel.
    assert client._ib.cancel_calls == []


@pytest.mark.asyncio
async def test_cancel_called_on_stale(monkeypatch):
    """Test the expected behavior."""
    ticker = _DummyTicker(bid=None, ask=None)
    client = _DummyClient(ticker)
    contract = _DummyContract()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    result = await get_market_data(client, contract)

    assert result["stale"] is True
    # Snapshot requests auto-expire; helper should not issue explicit cancel.
    assert client._ib.cancel_calls == []


@pytest.mark.asyncio
async def test_market_data_marks_stale_when_quote_exceeds_ttl(monkeypatch):
    """Test the expected behavior."""
    quote_time = datetime.now(timezone.utc) - timedelta(seconds=180)
    ticker = _DummyTicker(bid=1.0, ask=1.1, time=quote_time)
    client = _DummyClient(ticker)
    contract = _DummyContract()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    result = await get_market_data(client, contract, stale_data_threshold_seconds=60)

    assert result["stale"] is True


@pytest.mark.asyncio
async def test_market_data_accepts_recent_quote_with_ttl(monkeypatch):
    """Test the expected behavior."""
    quote_time = datetime.now(timezone.utc) - timedelta(seconds=5)
    ticker = _DummyTicker(bid=1.0, ask=1.1, time=quote_time)
    client = _DummyClient(ticker)
    contract = _DummyContract()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    result = await get_market_data(client, contract, stale_data_threshold_seconds=60)

    assert result["stale"] is False


class _OptionChainDummyIB:
    def __init__(self):
        self.cancel_calls = []
        self.market_data_type_calls = []
        self.contract_details_calls = []
        self.option_market_data_contracts = []
        self.expiry_date = datetime.now(timezone.utc).date() + timedelta(days=7)
        self.expiry_yyyymmdd = self.expiry_date.strftime("%Y%m%d")
        self.expiry_iso = self.expiry_date.isoformat()

    async def qualifyContractsAsync(self, contract):
        contract.conId = 4815747
        return [contract]

    def reqMarketDataType(self, market_data_type: int):
        self.market_data_type_calls.append(market_data_type)

    def reqMktData(self, contract, *_args, **_kwargs):
        # Stock snapshot used for strike filtering.
        if getattr(contract, "secType", "") == "STK":
            return _DummyTicker(
                bid=100.0,
                ask=100.5,
                contract=contract,
                market_price=100.0,
                last=100.0,
                close=99.5,
            )

        # Option snapshots used for bid/ask output.
        self.option_market_data_contracts.append(contract)
        if int(contract.strike) == 80:
            return _DummyTicker(bid=1.1, ask=1.2, contract=contract)
        return _DummyTicker(bid=0.9, ask=1.0, contract=contract)

    def cancelMktData(self, contract):
        self.cancel_calls.append(contract)

    async def reqSecDefOptParamsAsync(self, *_args):
        return [
            SimpleNamespace(
                exchange="SMART",
                underlyingConId=4815747,
                tradingClass="NVDA",
                multiplier="100",
                expirations=[self.expiry_yyyymmdd],
                strikes=[80.0, 90.0, 100.0],
            )
        ]

    async def reqContractDetailsAsync(self, template):
        self.contract_details_calls.append(template)
        details = []
        # One strike below range and one above range should be filtered out.
        for strike in (70.0, 80.0, 90.0, 105.0):
            contract = Option(
                template.symbol,
                template.lastTradeDateOrContractMonth,
                strike,
                "P",
                template.exchange,
                template.multiplier,
                template.currency,
                tradingClass=template.tradingClass,
            )
            contract.conId = int(strike * 10)
            details.append(SimpleNamespace(contract=contract))
        return details


@pytest.mark.asyncio
async def test_get_option_chain_uses_contract_details_and_filters_invalid_strikes(monkeypatch):
    """Test the expected behavior."""
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    ib = _OptionChainDummyIB()
    client = SimpleNamespace(_ib=ib)

    options = await get_option_chain(client, "NVDA", min_dte=1)

    assert len(options) == 2
    assert {opt["strike"] for opt in options} == {80.0, 90.0}
    assert all(opt["expiry"] == ib.expiry_iso for opt in options)
    assert all(opt["stale"] is False for opt in options)

    # The new path must discover contracts from contract details, not synthetic cross-product qualification.
    assert len(ib.contract_details_calls) == 1
    template = ib.contract_details_calls[0]
    assert template.tradingClass == "NVDA"
    assert template.multiplier == "100"
    assert template.exchange == "SMART"

    # Option market data subscriptions should only be requested for valid in-range contracts.
    assert len(ib.option_market_data_contracts) == 2
    assert {float(c.strike) for c in ib.option_market_data_contracts} == {80.0, 90.0}
    # Snapshot requests should not attempt explicit cancelMktData.
    assert ib.cancel_calls == []
