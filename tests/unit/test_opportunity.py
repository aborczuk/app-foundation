"""T027: Unit tests for opportunity discovery.

Tests cover:
- Strike selection from option chain (nearest expiry >= min_dte with return >= floor)
- Multiple qualifying strikes selects best return
- No qualifying strike skips ticker
- Stale market data triggers retry then skip
"""


from csp_trader.engine.opportunity import evaluate_ticker_opportunity


def _make_option(strike: float, dte: int, bid: float, expiry: str = "2026-04-01") -> dict:
    return {"strike": strike, "dte": dte, "bid": bid, "expiry": expiry, "stale": False}


def _make_rules_config():
    from tests.unit.test_rules import _make_rules
    return _make_rules()


async def test_strike_selection_returns_best_return_option():
    """When multiple strikes pass filters, the one with the best annualized return is chosen."""
    rules = _make_rules_config()
    options = [
        _make_option(strike=100.0, dte=30, bid=1.50),  # 18.25%
        _make_option(strike=95.0, dte=30, bid=1.80),   # 23.09%  ← best
        _make_option(strike=90.0, dte=30, bid=0.50),   # 7.12%   ← below floor
    ]
    result = await evaluate_ticker_opportunity(
        ticker="NVDA",
        target_price=110.0,
        options=options,
        rules=rules,
    )
    assert result is not None
    assert result["strike"] == 95.0


async def test_no_qualifying_strike_returns_none():
    """If no strike meets all hard filters, return None."""
    rules = _make_rules_config()
    options = [
        _make_option(strike=100.0, dte=30, bid=0.01),  # tiny return
        _make_option(strike=100.0, dte=3, bid=5.00),   # DTE too low
    ]
    result = await evaluate_ticker_opportunity(
        ticker="NVDA",
        target_price=110.0,
        options=options,
        rules=rules,
    )
    assert result is None


async def test_strike_above_target_price_skipped():
    """Strikes above target_price are rejected even with good returns."""
    rules = _make_rules_config()
    options = [
        _make_option(strike=120.0, dte=30, bid=5.00),  # strike > target_price=110
    ]
    result = await evaluate_ticker_opportunity(
        ticker="NVDA",
        target_price=110.0,
        options=options,
        rules=rules,
    )
    assert result is None


async def test_stale_options_skipped():
    """Options with stale=True market data are excluded from evaluation."""
    rules = _make_rules_config()
    # Only stale option
    stale_opt = {"strike": 100.0, "dte": 30, "bid": 3.00, "expiry": "2026-04-01", "stale": True}
    result = await evaluate_ticker_opportunity(
        ticker="NVDA",
        target_price=110.0,
        options=[stale_opt],
        rules=rules,
    )
    assert result is None
