"""T012/T025/T026: Unit tests for the rules engine.

Covers:
- T012: Exit trigger: return calculation, close/hold decisions, edge cases
- T025: Hard filters: DTE, return floor, strike <= target_price
- T026: 7-tier scoring: weight normalization, ranking, lower-is-better inversion
"""


from csp_trader.config import (
    RulesConfig,
    WatchlistEntry,
)
from csp_trader.engine.rules import (
    CloseSignal,
    apply_hard_filters,
    evaluate_exit_trigger,
    score_opportunity,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_rules(**overrides) -> RulesConfig:
    weights = {
        "tier_weights": {
            "fundamental_value": 30.0,
            "business_quality": 20.0,
            "balance_sheet": 15.0,
            "strategic_power": 15.0,
            "volatility_reduction": 8.0,
            "market_signals": 7.0,
            "technicals": 5.0,
        },
        "fundamental_value": {"forward_pe_3yr": 40.0, "fcf_yield": 30.0, "eps_growth": 20.0, "pe_flight_path": 10.0},
        "business_quality": {"business_diversification": 35.0, "customer_concentration": 35.0, "revenue_model": 30.0},
        "balance_sheet": {"net_debt_ebitda": 45.0, "interest_coverage": 35.0, "altman_z": 20.0},
        "strategic_power": {"roic": 40.0, "management_score": 30.0, "pricing_power_score": 30.0},
        "volatility_reduction": {"market_cap_billions": 50.0, "capital_return_score": 50.0},
        "market_signals": {"analyst_target_distance_pct": 60.0, "brand_strength_score": 40.0},
        "technicals": {"order_book_depth": 50.0, "bollinger_position": 50.0},
    }
    base = dict(
        min_dte=7,
        annualized_return_floor_pct=15.0,
        max_exposure_per_underlying_pct=10.0,
        max_cash_committed_pct=80.0,
        high_debt_sleeve_cap_pct=25.0,
        max_theme_exposure_pct=40.0,
        spread_adjustment_interval_seconds=30.0,
        spread_adjustment_increment=0.01,
        target_price={
            "margin_of_safety": {
                "min_pct": 15.0,
                "max_pct": 40.0,
                "final_cap_pct": 95.0,
                "manual_adjustment_min_pct": -20.0,
                "manual_adjustment_max_pct": 20.0,
                "score_normalization_denominator": 100.0,
                "default_manual_adjustment_pct": 0.0,
            }
        },
        scoring_weights=weights,
    )
    base.update(overrides)
    return RulesConfig(**base)


def _make_watchlist_entry(**overrides) -> WatchlistEntry:
    base = dict(
        ticker="NVDA",
        target_price=110.0,
        themes=["AI Hardware"],
        net_debt_ebitda=-0.8,
        interest_coverage=45.0,
        altman_z=8.2,
        forward_pe_3yr=22.0,
        pe_flight_path=3.5,
        fcf_yield=4.2,
        eps_growth=38.0,
        business_diversification=3,
        customer_concentration=2,
        revenue_model=4,
        roic=52.0,
        management_score=5,
        pricing_power_score=5,
        market_cap_billions=2800.0,
        capital_return_score=4,
        analyst_target_distance_pct=12.5,
        brand_strength_score=5,
    )
    base.update(overrides)
    return WatchlistEntry(**base)


# ---------------------------------------------------------------------------
# T012: Exit trigger tests
# ---------------------------------------------------------------------------


def test_exit_trigger_formula():
    """Remaining return is `(current_bid / strike) * (365 / DTE_remaining) * 100`."""
    # bid=$0.50, strike=$100, DTE=10 → 0.50/100 * 36.5 * 100 = 18.25% — hold
    signal = evaluate_exit_trigger(
        current_bid=0.50,
        strike=100.0,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
    )
    assert signal is None, "18.25% remaining return is above floor — should hold"


def test_exit_trigger_close_when_below_floor():
    """Close when remaining_return_pct < annualized_return_floor_pct."""
    # bid=$0.10, strike=$100, DTE=30 → 0.10/100 * (365/30) * 100 = 1.22% — close
    signal = evaluate_exit_trigger(
        current_bid=0.10,
        strike=100.0,
        dte_remaining=30,
        annualized_return_floor_pct=15.0,
    )
    assert isinstance(signal, CloseSignal)
    assert signal.remaining_return_pct < 15.0


def test_exit_trigger_hold_when_above_floor():
    """Hold when remaining_return_pct >= floor."""
    # bid=$1.50, strike=$100, DTE=20 → 1.50/100 * (365/20) * 100 = 27.375% — hold
    signal = evaluate_exit_trigger(
        current_bid=1.50,
        strike=100.0,
        dte_remaining=20,
        annualized_return_floor_pct=15.0,
    )
    assert signal is None


def test_exit_trigger_1_dte_edge_case():
    """1 DTE amplifies remaining return — a high bid may still hold."""
    # bid=$0.40, strike=$100, DTE=1 → 0.40/100 * 365 * 100 = 146% — hold
    signal = evaluate_exit_trigger(
        current_bid=0.40,
        strike=100.0,
        dte_remaining=1,
        annualized_return_floor_pct=15.0,
    )
    assert signal is None


def test_exit_trigger_zero_remaining_premium():
    """Zero remaining premium (worthless option) triggers close."""
    signal = evaluate_exit_trigger(
        current_bid=0.0,
        strike=100.0,
        dte_remaining=10,
        annualized_return_floor_pct=15.0,
    )
    assert isinstance(signal, CloseSignal)
    assert signal.remaining_return_pct == 0.0


# ---------------------------------------------------------------------------
# T025: Hard filter tests
# ---------------------------------------------------------------------------


def _make_option(
    strike: float = 100.0,
    dte: int = 14,
    bid: float = 0.50,
    expiry: str = "2026-04-01",
) -> dict:
    """Minimal option dict for filter tests."""
    return {"strike": strike, "dte": dte, "bid": bid, "expiry": expiry}


def test_hard_filter_rejects_dte_below_min():
    """Options with DTE < min_dte are rejected."""
    rules = _make_rules(min_dte=7)
    option = _make_option(strike=100.0, dte=5, bid=0.50)
    results = apply_hard_filters(
        options=[option],
        target_price=110.0,
        rules=rules,
    )
    passing = [r for r in results if r.passes]
    assert len(passing) == 0
    failed = [r for r in results if not r.passes]
    assert any("dte" in r.skip_reason.lower() for r in failed)


def test_hard_filter_rejects_below_return_floor():
    """Options with annualized return below floor are rejected."""
    rules = _make_rules(annualized_return_floor_pct=15.0)
    # bid=$0.01, strike=$100, DTE=14 → very low return
    option = _make_option(strike=100.0, dte=14, bid=0.01)
    results = apply_hard_filters(
        options=[option],
        target_price=110.0,
        rules=rules,
    )
    passing = [r for r in results if r.passes]
    assert len(passing) == 0


def test_hard_filter_rejects_strike_above_target_price():
    """Strikes above target_price are rejected."""
    rules = _make_rules()
    option = _make_option(strike=120.0, dte=14, bid=2.00)
    results = apply_hard_filters(
        options=[option],
        target_price=110.0,
        rules=rules,
    )
    passing = [r for r in results if r.passes]
    assert len(passing) == 0
    failed = [r for r in results if not r.passes]
    assert any("strike" in r.skip_reason.lower() or "target" in r.skip_reason.lower() for r in failed)


def test_hard_filter_passes_all_criteria():
    """Option meeting all criteria passes."""
    rules = _make_rules(min_dte=7, annualized_return_floor_pct=15.0)
    # bid=$2.00, strike=$100, DTE=30 → 2.00/100 * (365/30) * 100 = 24.3% — passes
    option = _make_option(strike=100.0, dte=30, bid=2.00)
    results = apply_hard_filters(
        options=[option],
        target_price=110.0,
        rules=rules,
    )
    passing = [r for r in results if r.passes]
    assert len(passing) == 1


def test_hard_filter_skip_reasons_logged_per_criterion():
    """Each failing criterion has a non-empty skip_reason."""
    rules = _make_rules(min_dte=7, annualized_return_floor_pct=15.0)
    option = _make_option(strike=130.0, dte=3, bid=0.01)
    results = apply_hard_filters(
        options=[option],
        target_price=110.0,
        rules=rules,
    )
    for r in results:
        if not r.passes:
            assert r.skip_reason, "Every failing filter must have a skip_reason"


# ---------------------------------------------------------------------------
# T026: 7-tier scoring tests
# ---------------------------------------------------------------------------


def test_scoring_normalization():
    """Composite score is in [0, 1] range after normalization."""
    rules = _make_rules()
    entry = _make_watchlist_entry()
    score = score_opportunity(entry, rules)
    assert 0.0 <= score <= 1.0


def test_higher_scored_ranks_above_lower():
    """Better fundamental entry scores higher than weaker one."""
    rules = _make_rules()
    good = _make_watchlist_entry(forward_pe_3yr=10.0, fcf_yield=8.0, eps_growth=50.0)
    weak = _make_watchlist_entry(forward_pe_3yr=80.0, fcf_yield=0.5, eps_growth=2.0)
    assert score_opportunity(good, rules) > score_opportunity(weak, rules)


def test_all_7_tiers_contribute():
    """Changing a single tier's attribute changes the total score."""
    rules = _make_rules()
    base = _make_watchlist_entry(management_score=1)
    high_mgmt = _make_watchlist_entry(management_score=5)
    assert score_opportunity(high_mgmt, rules) != score_opportunity(base, rules)


def test_configurable_weights_change_ranking():
    """Changing tier weights can alter relative ranking."""
    # Build rules that weight Tier 3 (balance_sheet) at 90%, everything else tiny
    heavy_balance_sheet_weights = {
        "tier_weights": {
            "fundamental_value": 1.0,
            "business_quality": 1.0,
            "balance_sheet": 90.0,
            "strategic_power": 1.0,
            "volatility_reduction": 1.0,
            "market_signals": 1.0,
            "technicals": 1.0,
        },
        "fundamental_value": {"forward_pe_3yr": 40.0, "fcf_yield": 30.0, "eps_growth": 20.0, "pe_flight_path": 10.0},
        "business_quality": {"business_diversification": 35.0, "customer_concentration": 35.0, "revenue_model": 30.0},
        "balance_sheet": {"net_debt_ebitda": 45.0, "interest_coverage": 35.0, "altman_z": 20.0},
        "strategic_power": {"roic": 40.0, "management_score": 30.0, "pricing_power_score": 30.0},
        "volatility_reduction": {"market_cap_billions": 50.0, "capital_return_score": 50.0},
        "market_signals": {"analyst_target_distance_pct": 60.0, "brand_strength_score": 40.0},
        "technicals": {"order_book_depth": 50.0, "bollinger_position": 50.0},
    }
    rules_bs_heavy = _make_rules(scoring_weights=heavy_balance_sheet_weights)

    # Entry with great balance sheet but bad fundamentals
    great_bs = _make_watchlist_entry(
        net_debt_ebitda=-5.0, interest_coverage=100.0, altman_z=12.0,
        forward_pe_3yr=99.0, fcf_yield=0.1,
    )
    # Entry with bad balance sheet but great fundamentals
    great_fund = _make_watchlist_entry(
        net_debt_ebitda=4.0, interest_coverage=2.5, altman_z=1.0,
        forward_pe_3yr=5.0, fcf_yield=20.0,
    )

    # Under BS-heavy weights, great_bs should score higher
    assert score_opportunity(great_bs, rules_bs_heavy) > score_opportunity(great_fund, rules_bs_heavy)


def test_forward_pe_3yr_lower_is_better():
    """forward_pe_3yr is inverted — lower value should give higher contribution."""
    rules = _make_rules()
    low_pe = _make_watchlist_entry(forward_pe_3yr=10.0)
    high_pe = _make_watchlist_entry(forward_pe_3yr=80.0)
    assert score_opportunity(low_pe, rules) > score_opportunity(high_pe, rules)
