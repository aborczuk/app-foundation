"""Unit tests for IBKR-first comparable valuation fallback behavior."""

from __future__ import annotations

import pytest
from ib_valuation.valuation.comparable_engine import ComparableEngine


@pytest.mark.asyncio
async def test_comparable_engine_uses_ibkr_sector_proxy_pe_when_available() -> None:
    """Test the expected behavior."""
    engine = ComparableEngine(
        ibkr_fetch_fundamentals=lambda _ticker, _sector_proxy_etf: {
            "sector_proxy_pe": 12.0,
            "forward_pe": 24.5,
            "net_debt_ebitda": 1.1,
            "interest_coverage": 9.3,
        },
        stale_multiple_lookup=lambda _ticker: None,
    )

    result = await engine.compute(ticker="NVDA", sector_proxy_etf="XLK", base_metric=8.0)

    assert result.multiples_source_state == "fresh"
    assert result.npv_per_share == 96.0
    assert result.unavailable_reason is None
    assert result.fundamentals_snapshot == {
        "sector_proxy_pe": 12.0,
        "forward_pe": 24.5,
        "net_debt_ebitda": 1.1,
        "interest_coverage": 9.3,
    }


@pytest.mark.asyncio
async def test_comparable_engine_falls_back_to_stale_cache_when_ibkr_unavailable() -> None:
    """Test the expected behavior."""
    def failing_ibkr(_ticker: str, _sector_proxy_etf: str) -> dict[str, float]:
        raise RuntimeError("ibkr unavailable")

    engine = ComparableEngine(
        ibkr_fetch_fundamentals=failing_ibkr,
        stale_multiple_lookup=lambda _ticker: 10.5,
    )

    result = await engine.compute(ticker="MSFT", sector_proxy_etf="XLK", base_metric=9.0)

    assert result.multiples_source_state == "stale"
    assert result.npv_per_share == 94.5
    assert result.unavailable_reason is None
    assert result.fundamentals_snapshot is None


@pytest.mark.asyncio
async def test_comparable_engine_uses_stale_when_ibkr_payload_missing_sector_proxy_pe() -> None:
    """Test the expected behavior."""
    engine = ComparableEngine(
        ibkr_fetch_fundamentals=lambda _ticker, _sector_proxy_etf: {"forward_pe": 21.0},
        stale_multiple_lookup=lambda _ticker: 11.0,
    )

    result = await engine.compute(ticker="AMD", sector_proxy_etf="SMH", base_metric=7.0)

    assert result.multiples_source_state == "stale"
    assert result.npv_per_share == 77.0
    assert result.unavailable_reason is None
    assert result.fundamentals_snapshot is None


@pytest.mark.asyncio
async def test_comparable_engine_marks_unavailable_when_no_sources_exist() -> None:
    """Test the expected behavior."""
    def failing_ibkr(_ticker: str, _sector_proxy_etf: str) -> dict[str, float]:
        raise RuntimeError("ibkr unavailable")

    engine = ComparableEngine(
        ibkr_fetch_fundamentals=failing_ibkr,
        stale_multiple_lookup=lambda _ticker: None,
    )

    result = await engine.compute(ticker="AMD", sector_proxy_etf="SMH", base_metric=7.0)

    assert result.multiples_source_state == "unavailable"
    assert result.npv_per_share is None
    assert result.fundamentals_snapshot is None
    assert "ibkr fundamentals" in result.unavailable_reason.lower()


@pytest.mark.asyncio
async def test_comparable_engine_supports_async_ibkr_provider() -> None:
    """Test the expected behavior."""
    async def ibkr_provider(_ticker: str, _sector_proxy_etf: str) -> dict[str, float]:
        return {"sector_proxy_pe": 14.0}

    engine = ComparableEngine(
        ibkr_fetch_fundamentals=ibkr_provider,
        stale_multiple_lookup=lambda _ticker: None,
    )

    result = await engine.compute(ticker="NVDA", sector_proxy_etf="XLK", base_metric=8.0)

    assert result.multiples_source_state == "fresh"
    assert result.npv_per_share == 112.0
