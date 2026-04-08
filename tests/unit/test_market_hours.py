"""B003: Market hours parsing uses exchange-local timezone (US/Eastern)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import csp_trader.ibkr.client as client_mod


@pytest.mark.parametrize(
    "now_str,expected",
    [
        ("2026-03-10 14:00", True),   # within 09:30-16:00 ET
        ("2026-03-10 08:00", False),  # before open
        ("2026-03-10 16:30", False),  # after close
    ],
)
def test_is_market_open_uses_exchange_local_time(monkeypatch, now_str, expected):
    """Test the expected behavior."""
    tz = ZoneInfo("America/New_York")
    fixed_now = datetime.strptime(now_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, _tz=None):
            return fixed_now

    monkeypatch.setattr(client_mod, "datetime", _FixedDatetime)

    trading_hours = "20260310:0930-20260310:1600"
    assert client_mod.IBKRClient.is_market_open(trading_hours) is expected
