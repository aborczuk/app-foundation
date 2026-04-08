"""Unit tests for exposure assembly helpers in main runtime loop."""

from __future__ import annotations

from types import SimpleNamespace

from csp_trader.main import _build_portfolio_exposure_positions


class _Contract:
    def __init__(self, symbol: str, sec_type: str) -> None:
        self.symbol = symbol
        self.secType = sec_type


class _PortfolioItem:
    def __init__(
        self,
        symbol: str,
        sec_type: str,
        position: float,
        market_value: float | None,
        average_cost: float | None,
    ) -> None:
        self.contract = _Contract(symbol, sec_type)
        self.position = position
        self.marketValue = market_value
        self.averageCost = average_cost


def test_build_portfolio_exposure_positions_adds_mapped_stock_exposure() -> None:
    """Test the expected behavior."""
    open_options = [
        {"ticker": "NVDA", "strike": 100.0, "qty": 1, "lifecycle_state": "open"},
    ]
    watchlist = [
        SimpleNamespace(ticker="NVDA", is_high_debt=True, themes=["AI"]),
    ]
    portfolio_items = [
        _PortfolioItem(
            symbol="NVDA",
            sec_type="STK",
            position=100.0,
            market_value=17_823.0,
            average_cost=180.0,
        ),
    ]

    positions, unmapped = _build_portfolio_exposure_positions(
        open_option_positions=open_options,
        live_portfolio_items=portfolio_items,
        watchlist_entries=watchlist,
    )

    assert unmapped == []
    assert len(positions) == 2

    option_row = positions[0]
    stock_row = positions[1]

    assert option_row["ticker"] == "NVDA"
    assert option_row["is_high_debt"] is True
    assert option_row["themes"] == ["AI"]

    assert stock_row["ticker"] == "NVDA"
    assert stock_row["exposure_usd"] == 17_823.0
    assert stock_row["is_high_debt"] is True
    assert stock_row["themes"] == ["AI"]


def test_build_portfolio_exposure_positions_reports_unmapped_stock_ticker() -> None:
    """Test the expected behavior."""
    open_options = []
    watchlist = []
    portfolio_items = [
        _PortfolioItem(
            symbol="MSFT",
            sec_type="STK",
            position=100.0,
            market_value=35_000.0,
            average_cost=340.0,
        ),
    ]

    positions, unmapped = _build_portfolio_exposure_positions(
        open_option_positions=open_options,
        live_portfolio_items=portfolio_items,
        watchlist_entries=watchlist,
    )

    assert positions == []
    assert unmapped == ["MSFT"]


def test_build_portfolio_exposure_positions_uses_average_cost_fallback() -> None:
    """Test the expected behavior."""
    open_options = []
    watchlist = [
        SimpleNamespace(ticker="GLD", is_high_debt=False, themes=["Gold"]),
    ]
    portfolio_items = [
        _PortfolioItem(
            symbol="GLD",
            sec_type="STK",
            position=10.0,
            market_value=None,
            average_cost=250.0,
        ),
    ]

    positions, unmapped = _build_portfolio_exposure_positions(
        open_option_positions=open_options,
        live_portfolio_items=portfolio_items,
        watchlist_entries=watchlist,
    )

    assert unmapped == []
    assert len(positions) == 1
    assert positions[0]["exposure_usd"] == 2500.0
