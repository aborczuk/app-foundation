"""Unit tests for IBKR conversion helpers."""

from __future__ import annotations

from csp_trader.ibkr.conversion import (
    ibkr_position_to_dict,
    is_csp_option_position,
)


class _DummyOptionContract:
    conId = 123
    symbol = "NVDA"
    secType = "OPT"
    right = "P"
    strike = 100.0
    lastTradeDateOrContractMonth = "20260401"


class _DummyStockContract:
    conId = 456
    symbol = "NVDA"
    secType = "STK"
    right = ""
    strike = 0.0
    lastTradeDateOrContractMonth = ""


class _DummyPosition:
    def __init__(self, contract, avg_cost: float, position: float) -> None:
        self.contract = contract
        self.avgCost = avg_cost
        self.position = position


def test_ibkr_position_to_dict_includes_contract_type_fields() -> None:
    """Test the expected behavior."""
    pos = _DummyPosition(_DummyOptionContract(), avg_cost=200.0, position=-1.0)

    result = ibkr_position_to_dict(pos)

    assert result["sec_type"] == "OPT"
    assert result["right"] == "P"
    assert result["strike"] == 100.0
    assert result["expiry"] == "2026-04-01"
    assert result["qty"] == 1


def test_is_csp_option_position_accepts_put_options_only() -> None:
    """Test the expected behavior."""
    pos = _DummyPosition(_DummyOptionContract(), avg_cost=200.0, position=-1.0)
    converted = ibkr_position_to_dict(pos)

    assert is_csp_option_position(converted) is True


def test_is_csp_option_position_rejects_stock_positions() -> None:
    """Test the expected behavior."""
    pos = _DummyPosition(_DummyStockContract(), avg_cost=18000.0, position=100.0)
    converted = ibkr_position_to_dict(pos)

    assert is_csp_option_position(converted) is False
