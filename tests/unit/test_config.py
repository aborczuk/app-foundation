"""T004: Unit tests for config validation (Pydantic v2 models).

Tests cover:
- Valid config loads correctly
- Missing required fields raise ValidationError
- Invalid types rejected
- Numeric range constraints enforced
- is_high_debt derived correctly
- scoring_weights structure validation
- Empty watchlist rejected
"""

import pytest
from pydantic import ValidationError

from csp_trader.config import (
    AppConfig,
    ExecutionConfig,
    IbkrConfig,
    RulesConfig,
    ScoringWeights,
    StorageConfig,
    TierWeights,
    WatchlistEntry,
    load_config,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_SCORING_WEIGHTS = {
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

VALID_WATCHLIST_ENTRY = {
    "ticker": "NVDA",
    "target_price": 110.00,
    "themes": ["AI Hardware"],
    "net_debt_ebitda": -0.8,
    "interest_coverage": 45.0,
    "altman_z": 8.2,
    "forward_pe_3yr": 22.0,
    "pe_flight_path": 3.5,
    "fcf_yield": 4.2,
    "eps_growth": 38.0,
    "business_diversification": 3,
    "customer_concentration": 2,
    "revenue_model": 4,
    "roic": 52.0,
    "management_score": 5,
    "pricing_power_score": 5,
    "market_cap_billions": 2800.0,
    "capital_return_score": 4,
    "analyst_target_distance_pct": 12.5,
    "brand_strength_score": 5,
}

VALID_RULES = {
    "min_dte": 7,
    "annualized_return_floor_pct": 15.0,
    "max_exposure_per_underlying_pct": 10.0,
    "max_cash_committed_pct": 80.0,
    "high_debt_sleeve_cap_pct": 25.0,
    "max_theme_exposure_pct": 40.0,
    "spread_adjustment_interval_seconds": 30.0,
    "spread_adjustment_increment": 0.01,
    "target_price": {
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
    "scoring_weights": VALID_SCORING_WEIGHTS,
}


# ---------------------------------------------------------------------------
# WatchlistEntry tests
# ---------------------------------------------------------------------------


def test_watchlist_entry_valid():
    """Valid watchlist entry loads without errors."""
    entry = WatchlistEntry(**VALID_WATCHLIST_ENTRY)
    assert entry.ticker == "NVDA"
    assert entry.target_price == 110.00


def test_watchlist_entry_missing_required_field():
    """Missing required field raises ValidationError."""
    data = dict(VALID_WATCHLIST_ENTRY)
    del data["ticker"]
    with pytest.raises(ValidationError):
        WatchlistEntry(**data)


def test_watchlist_entry_target_price_zero_rejected():
    """target_price must be > 0."""
    data = dict(VALID_WATCHLIST_ENTRY)
    data["target_price"] = 0.0
    with pytest.raises(ValidationError):
        WatchlistEntry(**data)


def test_watchlist_entry_empty_themes_rejected():
    """Themes must be non-empty."""
    data = dict(VALID_WATCHLIST_ENTRY)
    data["themes"] = []
    with pytest.raises(ValidationError):
        WatchlistEntry(**data)


def test_watchlist_entry_sector_proxy_etf_normalized_uppercase():
    """sector_proxy_etf is normalized to uppercase when provided."""
    data = dict(VALID_WATCHLIST_ENTRY)
    data["sector_proxy_etf"] = " xlk "
    entry = WatchlistEntry(**data)
    assert entry.sector_proxy_etf == "XLK"


def test_watchlist_entry_sector_proxy_etf_blank_becomes_none():
    """Blank sector_proxy_etf normalizes to None."""
    data = dict(VALID_WATCHLIST_ENTRY)
    data["sector_proxy_etf"] = "   "
    entry = WatchlistEntry(**data)
    assert entry.sector_proxy_etf is None


def test_is_high_debt_derived_net_debt_over_3():
    """is_high_debt is True when net_debt_ebitda > 3."""
    data = dict(VALID_WATCHLIST_ENTRY)
    data["net_debt_ebitda"] = 3.5
    data["interest_coverage"] = 10.0
    entry = WatchlistEntry(**data)
    assert entry.is_high_debt is True


def test_is_high_debt_derived_interest_coverage_under_3():
    """is_high_debt is True when interest_coverage < 3."""
    data = dict(VALID_WATCHLIST_ENTRY)
    data["net_debt_ebitda"] = 1.0
    data["interest_coverage"] = 2.5
    entry = WatchlistEntry(**data)
    assert entry.is_high_debt is True


def test_is_high_debt_false_when_both_ok():
    """is_high_debt is False when net_debt_ebitda <= 3 AND interest_coverage >= 3."""
    data = dict(VALID_WATCHLIST_ENTRY)
    data["net_debt_ebitda"] = 2.0
    data["interest_coverage"] = 5.0
    entry = WatchlistEntry(**data)
    assert entry.is_high_debt is False


def test_management_score_range_constraint():
    """management_score must be 1–5."""
    data = dict(VALID_WATCHLIST_ENTRY)
    data["management_score"] = 6
    with pytest.raises(ValidationError):
        WatchlistEntry(**data)

    data["management_score"] = 0
    with pytest.raises(ValidationError):
        WatchlistEntry(**data)


def test_forward_pe_3yr_must_be_positive():
    """forward_pe_3yr must be > 0."""
    data = dict(VALID_WATCHLIST_ENTRY)
    data["forward_pe_3yr"] = 0.0
    with pytest.raises(ValidationError):
        WatchlistEntry(**data)


# ---------------------------------------------------------------------------
# RulesConfig tests
# ---------------------------------------------------------------------------


def test_rules_config_valid():
    """Valid rules config loads without errors."""
    rules = RulesConfig(**VALID_RULES)
    assert rules.min_dte == 7
    assert rules.annualized_return_floor_pct == 15.0
    assert rules.target_price.fundamentals_hydration.fail_policy == "block_ticker"


def test_rules_config_min_dte_below_1_rejected():
    """min_dte must be >= 1."""
    data = dict(VALID_RULES)
    data["min_dte"] = 0
    with pytest.raises(ValidationError):
        RulesConfig(**data)


def test_rules_config_return_floor_must_be_positive():
    """annualized_return_floor_pct must be > 0."""
    data = dict(VALID_RULES)
    data["annualized_return_floor_pct"] = 0.0
    with pytest.raises(ValidationError):
        RulesConfig(**data)


def test_rules_config_spread_interval_allows_fast_e2e_values():
    """spread_adjustment_interval_seconds can be lowered for E2E acceleration."""
    data = dict(VALID_RULES)
    data["spread_adjustment_interval_seconds"] = 2.0
    rules = RulesConfig(**data)
    assert rules.spread_adjustment_interval_seconds == 2.0


def test_rules_config_spread_interval_below_1_rejected():
    """spread_adjustment_interval_seconds must remain >= 1 second."""
    data = dict(VALID_RULES)
    data["spread_adjustment_interval_seconds"] = 0.5
    with pytest.raises(ValidationError):
        RulesConfig(**data)


def test_rules_config_requires_target_price_policy():
    """rules.target_price.margin_of_safety must be present."""
    data = dict(VALID_RULES)
    data.pop("target_price")
    with pytest.raises(ValidationError):
        RulesConfig(**data)


def test_rules_config_target_price_policy_rejects_invalid_bounds():
    """Target-price policy bounds must be internally consistent."""
    data = dict(VALID_RULES)
    target_price = dict(data["target_price"])
    margin = dict(target_price["margin_of_safety"])
    margin["max_pct"] = 10.0
    margin["min_pct"] = 20.0
    target_price["margin_of_safety"] = margin
    data["target_price"] = target_price
    with pytest.raises(ValidationError):
        RulesConfig(**data)


def test_rules_config_target_price_fundamentals_hydration_rejects_unknown_fields():
    """Hydration field list must stay within the supported Tier 1/3 set."""
    data = dict(VALID_RULES)
    target_price = dict(data["target_price"])
    target_price["fundamentals_hydration"] = {
        "selected_fields": ["forward_pe_3yr", "made_up_metric"],
        "fail_policy": "block_ticker",
    }
    data["target_price"] = target_price
    with pytest.raises(ValidationError):
        RulesConfig(**data)


def test_rules_config_exposure_pct_range():
    """max_exposure_per_underlying_pct must be in (0, 100)."""
    data = dict(VALID_RULES)
    data["max_exposure_per_underlying_pct"] = 0.0
    with pytest.raises(ValidationError):
        RulesConfig(**data)

    data["max_exposure_per_underlying_pct"] = 100.0
    with pytest.raises(ValidationError):
        RulesConfig(**data)


def test_scoring_weights_all_7_tiers_present():
    """scoring_weights must include all 7 tier keys."""
    ScoringWeights(**VALID_SCORING_WEIGHTS)
    tier_names = set(TierWeights.model_fields.keys())
    expected = {
        "fundamental_value",
        "business_quality",
        "balance_sheet",
        "strategic_power",
        "volatility_reduction",
        "market_signals",
        "technicals",
    }
    assert tier_names == expected


def test_scoring_weights_normalized_to_1():
    """Tier weights and per-attribute weights are normalized to sum=1.0 at load."""
    rules = RulesConfig(**VALID_RULES)
    tier_sum = sum(rules.scoring_weights.tier_weights.model_dump().values())
    assert abs(tier_sum - 1.0) < 1e-9

    attr_sum = sum(rules.scoring_weights.fundamental_value.values())
    assert abs(attr_sum - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# AppConfig integration tests
# ---------------------------------------------------------------------------


def test_app_config_empty_watchlist_rejected():
    """AppConfig raises ValidationError when watchlist is empty."""
    with pytest.raises(ValidationError):
        AppConfig(
            rules=RulesConfig(**VALID_RULES),
            execution=ExecutionConfig(),
            ibkr=IbkrConfig(),
            storage=StorageConfig(),
            watchlist=[],
        )


def test_app_config_heartbeat_url_not_in_config():
    """HEARTBEAT_URL must not appear as a config field (it's env-only)."""
    assert not hasattr(AppConfig, "heartbeat_url"), "HEARTBEAT_URL must not be a config field"


def test_app_config_valid():
    """Full valid AppConfig loads correctly."""
    cfg = AppConfig(
        rules=RulesConfig(**VALID_RULES),
        execution=ExecutionConfig(),
        ibkr=IbkrConfig(),
        storage=StorageConfig(),
        watchlist=[WatchlistEntry(**VALID_WATCHLIST_ENTRY)],
    )
    assert len(cfg.watchlist) == 1
    assert cfg.rules.min_dte == 7


def test_load_config_applies_runtime_overrides(tmp_path, monkeypatch):
    """Runtime env overrides should patch rules and selected ticker target price."""
    config_path = tmp_path / "config.yaml"
    raw = {
        "rules": VALID_RULES,
        "execution": {"eval_interval_seconds": 300, "stale_data_threshold_seconds": 60, "heartbeat_interval_seconds": 120},
        "ibkr": {"host": "127.0.0.1", "port": 4001, "client_id": 2},
        "storage": {"db_path": "trading_state.db"},
        "watchlist": [VALID_WATCHLIST_ENTRY],
    }

    import yaml

    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    monkeypatch.setenv("CSP_OVERRIDE_ANNUALIZED_RETURN_FLOOR_PCT", "1.25")
    monkeypatch.setenv("CSP_OVERRIDE_MIN_DTE", "2")
    monkeypatch.setenv("CSP_OVERRIDE_SPREAD_ADJUSTMENT_INTERVAL_SECONDS", "2.0")
    monkeypatch.setenv("CSP_OVERRIDE_SPREAD_ADJUSTMENT_INCREMENT", "0.10")
    monkeypatch.setenv("CSP_OVERRIDE_TARGET_TICKER", "NVDA")
    monkeypatch.setenv("CSP_OVERRIDE_TARGET_PRICE", "123.45")

    cfg = load_config(config_path)
    assert cfg.rules.annualized_return_floor_pct == 1.25
    assert cfg.rules.min_dte == 2
    assert cfg.rules.spread_adjustment_interval_seconds == 2.0
    assert cfg.rules.spread_adjustment_increment == 0.10
    assert cfg.watchlist[0].ticker == "NVDA"
    assert cfg.watchlist[0].target_price == 123.45


def test_load_config_resolves_storage_paths_relative_to_config_dir(tmp_path):
    """Relative storage paths should be normalized against config file directory."""
    config_dir = tmp_path / "profiles"
    config_dir.mkdir()
    config_path = config_dir / "paper.yaml"

    raw = {
        "rules": VALID_RULES,
        "execution": {
            "eval_interval_seconds": 300,
            "stale_data_threshold_seconds": 60,
            "heartbeat_interval_seconds": 120,
        },
        "ibkr": {"host": "127.0.0.1", "port": 4001, "client_id": 2},
        "storage": {
            "db_path": "../state/trading_state.db",
            "valuation_db_path": "../state/valuation_state.db",
            "log_root_dir": "../logs/paper",
            "log_path_template": "../logs/{run_id}/events.jsonl",
        },
        "watchlist": [VALID_WATCHLIST_ENTRY],
    }

    import yaml

    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    cfg = load_config(config_path)
    assert cfg.storage.db_path == str((config_dir / "../state/trading_state.db").resolve())
    assert cfg.storage.valuation_db_path == str((config_dir / "../state/valuation_state.db").resolve())
    assert cfg.storage.log_root_dir == str((config_dir / "../logs/paper").resolve())
    assert cfg.storage.log_path_template == str((config_dir / "../logs/{run_id}/events.jsonl").resolve())


def test_load_config_preserves_absolute_storage_paths(tmp_path):
    """Absolute storage paths should remain unchanged."""
    config_path = tmp_path / "config.yaml"
    abs_db = str((tmp_path / "db" / "trading_state.db").resolve())
    abs_valuation_db = str((tmp_path / "db" / "valuation_state.db").resolve())
    abs_log_root = str((tmp_path / "logs").resolve())
    abs_log_template = str((tmp_path / "logs" / "{run_id}" / "trading.jsonl").resolve())

    raw = {
        "rules": VALID_RULES,
        "execution": {
            "eval_interval_seconds": 300,
            "stale_data_threshold_seconds": 60,
            "heartbeat_interval_seconds": 120,
        },
        "ibkr": {"host": "127.0.0.1", "port": 4001, "client_id": 2},
        "storage": {
            "db_path": abs_db,
            "valuation_db_path": abs_valuation_db,
            "log_root_dir": abs_log_root,
            "log_path_template": abs_log_template,
        },
        "watchlist": [VALID_WATCHLIST_ENTRY],
    }

    import yaml

    config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    cfg = load_config(config_path)
    assert cfg.storage.db_path == abs_db
    assert cfg.storage.valuation_db_path == abs_valuation_db
    assert cfg.storage.log_root_dir == abs_log_root
    assert cfg.storage.log_path_template == abs_log_template
