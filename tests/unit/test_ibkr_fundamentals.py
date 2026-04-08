"""Unit tests for IBKR fundamentals fetch/parsing helpers."""

from __future__ import annotations

import pytest

from csp_trader.target_price.ibkr_fundamentals import build_ibkr_fundamentals_fetcher


class _FakeIB:
    def __init__(self, reports: dict[str, str]) -> None:
        self._reports = reports
        self.qualify_calls: list[str] = []
        self.report_calls: list[tuple[str, str]] = []

    async def qualifyContractsAsync(self, contract):  # type: ignore[no-untyped-def]
        symbol = str(contract.symbol)
        self.qualify_calls.append(symbol)
        if symbol not in self._reports:
            return []
        contract.conId = len(self.qualify_calls)
        return [contract]

    async def reqFundamentalDataAsync(self, contract, report_type: str):  # type: ignore[no-untyped-def]
        symbol = str(contract.symbol)
        self.report_calls.append((symbol, report_type))
        return self._reports[symbol]


class _FakeIBKRClient:
    def __init__(self, reports: dict[str, str]) -> None:
        self._ib = _FakeIB(reports)


@pytest.mark.asyncio
async def test_fetcher_extracts_sector_proxy_pe_and_tier_metrics() -> None:
    """Test the expected behavior."""
    ticker_xml = """
    <ReportSnapshot>
      <Ratios>
        <Ratio FieldName="ForwardPE">24.6</Ratio>
        <Ratio FieldName="NetDebtToEBITDA">1.2</Ratio>
        <Ratio FieldName="InterestCoverage">10.8</Ratio>
      </Ratios>
    </ReportSnapshot>
    """
    sector_xml = """
    <ReportSnapshot>
      <Ratios>
        <Ratio FieldName="PEEXCLXOR">19.4</Ratio>
      </Ratios>
    </ReportSnapshot>
    """
    client = _FakeIBKRClient({"MSFT": ticker_xml, "XLK": sector_xml})
    fetch = build_ibkr_fundamentals_fetcher(client)  # type: ignore[arg-type]

    payload = await fetch("MSFT", "XLK")

    assert payload == {
        "sector_proxy_pe": 19.4,
        "forward_pe": 24.6,
        "net_debt_ebitda": 1.2,
        "interest_coverage": 10.8,
    }


@pytest.mark.asyncio
async def test_fetcher_derives_missing_tier_metrics_from_component_fields() -> None:
    """Test the expected behavior."""
    ticker_xml = """
    <ReportSnapshot>
      <Ratios>
        <Ratio FieldName="ForwardPE">21.0</Ratio>
        <Ratio FieldName="NetDebt">45.0</Ratio>
        <Ratio FieldName="EBITDA">15.0</Ratio>
        <Ratio FieldName="EBIT">30.0</Ratio>
        <Ratio FieldName="InterestExpense">6.0</Ratio>
      </Ratios>
    </ReportSnapshot>
    """
    sector_xml = """
    <ReportSnapshot>
      <Ratios>
        <Ratio FieldName="PEEXCLXOR">18.0</Ratio>
      </Ratios>
    </ReportSnapshot>
    """
    client = _FakeIBKRClient({"META": ticker_xml, "XLK": sector_xml})
    fetch = build_ibkr_fundamentals_fetcher(client)  # type: ignore[arg-type]

    payload = await fetch("META", "XLK")

    assert payload["sector_proxy_pe"] == 18.0
    assert payload["forward_pe"] == 21.0
    assert payload["net_debt_ebitda"] == 3.0
    assert payload["interest_coverage"] == 5.0


@pytest.mark.asyncio
async def test_fetcher_caches_qualified_contracts() -> None:
    """Test the expected behavior."""
    xml = """
    <ReportSnapshot>
      <Ratios>
        <Ratio FieldName="PEEXCLXOR">20.1</Ratio>
      </Ratios>
    </ReportSnapshot>
    """
    client = _FakeIBKRClient({"NVDA": xml, "SMH": xml})
    fetch = build_ibkr_fundamentals_fetcher(client)  # type: ignore[arg-type]

    await fetch("NVDA", "SMH")
    await fetch("NVDA", "SMH")

    assert client._ib.qualify_calls == ["NVDA", "SMH"]


@pytest.mark.asyncio
async def test_fetcher_returns_ticker_metrics_when_sector_proxy_pe_missing() -> None:
    """Test the expected behavior."""
    ticker_xml = """
    <ReportSnapshot>
      <Ratios>
        <Ratio FieldName="ForwardPE">26.0</Ratio>
        <Ratio FieldName="NetDebtToEBITDA">1.4</Ratio>
        <Ratio FieldName="InterestCoverage">7.2</Ratio>
      </Ratios>
    </ReportSnapshot>
    """
    missing_sector_pe_xml = """
    <ReportSnapshot>
      <Ratios>
        <Ratio FieldName="PB">3.2</Ratio>
      </Ratios>
    </ReportSnapshot>
    """
    client = _FakeIBKRClient({"AAPL": ticker_xml, "XLK": missing_sector_pe_xml})
    fetch = build_ibkr_fundamentals_fetcher(client)  # type: ignore[arg-type]

    payload = await fetch("AAPL", "XLK")

    assert payload == {
        "forward_pe": 26.0,
        "net_debt_ebitda": 1.4,
        "interest_coverage": 7.2,
    }


@pytest.mark.asyncio
async def test_fetcher_returns_ticker_metrics_when_sector_unavailable() -> None:
    """Test the expected behavior."""
    ticker_xml = """
    <ReportSnapshot>
      <Ratios>
        <Ratio FieldName="ForwardPE">18.5</Ratio>
      </Ratios>
    </ReportSnapshot>
    """
    client = _FakeIBKRClient({"AAPL": ticker_xml})
    fetch = build_ibkr_fundamentals_fetcher(client)  # type: ignore[arg-type]

    payload = await fetch("AAPL", "XLK")

    assert payload == {"forward_pe": 18.5}


@pytest.mark.asyncio
async def test_fetcher_raises_on_invalid_xml_payload() -> None:
    """Test the expected behavior."""
    client = _FakeIBKRClient({"AAPL": "<broken", "XLK": "<broken"})
    fetch = build_ibkr_fundamentals_fetcher(client)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="invalid_fundamentals_xml"):
        await fetch("AAPL", "XLK")
