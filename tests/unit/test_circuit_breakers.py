"""T028: Unit tests for circuit breakers.

Tests cover:
- Per-underlying exposure cap blocks when exceeded
- High-debt sleeve cap blocks when combined high-debt exposure exceeds cap
- Theme cap blocks when theme exposure exceeds cap
- Cash circuit breaker pauses when TotalCashValue/NetLiquidation < threshold
- Circuit breaker clears when condition resolves
"""


from csp_trader.risk.circuit_breakers import check_can_trade


def _make_portfolio_state(
    net_liquidation: float = 100_000.0,
    total_cash: float = 80_000.0,
    positions: list[dict] | None = None,
) -> dict:
    return {
        "net_liquidation": net_liquidation,
        "total_cash": total_cash,
        "positions": positions or [],
    }


def _make_rules_config(**overrides):
    from tests.unit.test_rules import _make_rules
    return _make_rules(**overrides)


def test_per_underlying_exposure_cap_blocks():
    """check_can_trade returns False when per-underlying exposure would exceed cap."""
    rules = _make_rules_config(max_exposure_per_underlying_pct=10.0)
    # Existing NVDA exposure: $9,500 / $100,000 = 9.5%
    # New proposed collateral: $1,000 → total 10.5% > 10% cap
    portfolio = _make_portfolio_state(
        net_liquidation=100_000.0,
        total_cash=80_000.0,
        positions=[
            {"ticker": "NVDA", "strike": 95.0, "qty": 1, "lifecycle_state": "open"},  # $9,500 collateral
        ],
    )
    allowed, reason = check_can_trade(
        ticker="NVDA",
        proposed_collateral=1_000.0,
        portfolio_state=portfolio,
        rules=rules,
    )
    assert not allowed
    assert "exposure" in reason.lower() or "underlying" in reason.lower()


def test_per_underlying_exposure_allows_within_cap():
    """check_can_trade returns True when exposure stays under cap."""
    rules = _make_rules_config(max_exposure_per_underlying_pct=10.0)
    portfolio = _make_portfolio_state(
        net_liquidation=100_000.0,
        positions=[
            {"ticker": "NVDA", "strike": 50.0, "qty": 1, "lifecycle_state": "open"},  # $5,000
        ],
    )
    allowed, reason = check_can_trade(
        ticker="NVDA",
        proposed_collateral=3_000.0,
        portfolio_state=portfolio,
        rules=rules,
    )
    assert allowed


def test_high_debt_sleeve_cap_blocks():
    """check_can_trade blocks when combined high-debt exposure would exceed sleeve cap."""
    rules = _make_rules_config(high_debt_sleeve_cap_pct=25.0)
    # Two high-debt positions: $12,000 + $10,000 = $22,000 / $100,000 = 22%
    # New proposal: $4,000 → total $26,000 = 26% > 25%
    portfolio = _make_portfolio_state(
        net_liquidation=100_000.0,
        positions=[
            {"ticker": "HIGH1", "strike": 120.0, "qty": 1, "lifecycle_state": "open", "is_high_debt": True},
            {"ticker": "HIGH2", "strike": 100.0, "qty": 1, "lifecycle_state": "open", "is_high_debt": True},
        ],
    )
    allowed, reason = check_can_trade(
        ticker="HIGH3",
        proposed_collateral=4_000.0,
        portfolio_state=portfolio,
        rules=rules,
        is_high_debt=True,
    )
    assert not allowed
    assert "high" in reason.lower() or "debt" in reason.lower() or "sleeve" in reason.lower()


def test_theme_cap_blocks():
    """check_can_trade blocks when a theme would exceed the max theme exposure."""
    rules = _make_rules_config(max_theme_exposure_pct=40.0)
    # AI Hardware exposure: $38,000 / $100,000 = 38%
    # New $3,000 → total $41,000 = 41% > 40%
    portfolio = _make_portfolio_state(
        net_liquidation=100_000.0,
        positions=[
            {
                "ticker": "NVDA",
                "strike": 380.0,
                "qty": 1,
                "lifecycle_state": "open",
                "themes": ["AI Hardware"],
            },
        ],
    )
    allowed, reason = check_can_trade(
        ticker="AMD",
        proposed_collateral=3_000.0,
        portfolio_state=portfolio,
        rules=rules,
        themes=["AI Hardware"],
    )
    assert not allowed
    assert "theme" in reason.lower()


def test_cash_circuit_breaker_pauses_new_orders():
    """check_can_trade blocks when cash ratio drops below threshold."""
    # max_cash_committed_pct=80 → pause when cash < 20% of NetLiquidation
    # total_cash=15,000 / net_liquidation=100,000 = 15% < 20% → CB triggered
    rules = _make_rules_config(max_cash_committed_pct=80.0)
    portfolio = _make_portfolio_state(
        net_liquidation=100_000.0,
        total_cash=15_000.0,  # only 15% cash left
    )
    allowed, reason = check_can_trade(
        ticker="NVDA",
        proposed_collateral=1_000.0,
        portfolio_state=portfolio,
        rules=rules,
    )
    assert not allowed
    assert "cash" in reason.lower() or "circuit" in reason.lower()


def test_cash_circuit_breaker_clears_when_resolved():
    """check_can_trade allows trades when cash is above the threshold."""
    rules = _make_rules_config(max_cash_committed_pct=80.0)
    portfolio = _make_portfolio_state(
        net_liquidation=100_000.0,
        total_cash=30_000.0,  # 30% cash — above 20% threshold
    )
    allowed, _ = check_can_trade(
        ticker="NVDA",
        proposed_collateral=1_000.0,
        portfolio_state=portfolio,
        rules=rules,
    )
    assert allowed


def test_per_underlying_exposure_counts_exposure_usd_rows():
    """Stock exposure rows with exposure_usd contribute to per-ticker concentration."""
    rules = _make_rules_config(max_exposure_per_underlying_pct=10.0)
    portfolio = _make_portfolio_state(
        net_liquidation=100_000.0,
        total_cash=80_000.0,
        positions=[
            {
                "ticker": "NVDA",
                "lifecycle_state": "open",
                "exposure_usd": 9_500.0,
                "themes": ["AI Hardware"],
                "is_high_debt": False,
            },
        ],
    )
    allowed, reason = check_can_trade(
        ticker="NVDA",
        proposed_collateral=1_000.0,
        portfolio_state=portfolio,
        rules=rules,
    )

    assert not allowed
    assert "underlying" in reason.lower() or "exposure" in reason.lower()


def test_theme_cap_counts_stock_exposure_rows():
    """Theme caps include synthetic stock exposure rows with exposure_usd."""
    rules = _make_rules_config(max_theme_exposure_pct=40.0)
    portfolio = _make_portfolio_state(
        net_liquidation=100_000.0,
        total_cash=80_000.0,
        positions=[
            {
                "ticker": "NVDA",
                "lifecycle_state": "open",
                "exposure_usd": 39_000.0,
                "themes": ["AI Hardware"],
                "is_high_debt": False,
            },
        ],
    )
    allowed, reason = check_can_trade(
        ticker="AMD",
        proposed_collateral=2_000.0,
        portfolio_state=portfolio,
        rules=rules,
        themes=["AI Hardware"],
    )

    assert not allowed
    assert "theme" in reason.lower()
