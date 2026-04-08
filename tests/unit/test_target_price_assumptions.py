"""Unit tests for target-price ticker-assumption derivation."""

from __future__ import annotations

from pathlib import Path

import pytest

from csp_trader.config import load_config
from csp_trader.target_price.orchestrator import (
    _build_ticker_assumptions_from_watchlist,
    _prepare_prebatch_fundamentals_overrides,
)
from csp_trader.target_price.scoring_adapter import TradingRulesScoringAdapter

EXAMPLE_CONFIG_PATH = (
    Path(__file__).parents[2] / "specs" / "001-auto-options-trader" / "contracts" / "config-example.yaml"
)
_SCORING_PORT = TradingRulesScoringAdapter()


def test_build_ticker_assumptions_are_ticker_specific() -> None:
    """Test the expected behavior."""
    cfg = load_config(EXAMPLE_CONFIG_PATH)

    assumptions = _build_ticker_assumptions_from_watchlist(
        watchlist=cfg.watchlist,
        rules=cfg.rules,
        scoring_port=_SCORING_PORT,
    )

    assert "NVDA" in assumptions
    assert "MSFT" in assumptions
    assert "GLD" in assumptions

    assert assumptions["NVDA"]["base_fcf_per_share"] != assumptions["MSFT"]["base_fcf_per_share"]
    assert assumptions["NVDA"]["composite_risk_score"] != assumptions["GLD"]["composite_risk_score"]
    assert assumptions["GLD"]["sector_proxy_etf"] == "GLD"


def test_build_ticker_assumptions_respects_explicit_sector_proxy() -> None:
    """Test the expected behavior."""
    cfg = load_config(EXAMPLE_CONFIG_PATH)
    entry = cfg.watchlist[0].model_copy(update={"sector_proxy_etf": "xly"})

    assumptions = _build_ticker_assumptions_from_watchlist(
        watchlist=[entry],
        rules=cfg.rules,
        scoring_port=_SCORING_PORT,
    )

    assert assumptions["NVDA"]["sector_proxy_etf"] == "XLY"


def test_build_ticker_assumptions_applies_fundamentals_overrides() -> None:
    """Test the expected behavior."""
    cfg = load_config(EXAMPLE_CONFIG_PATH)
    entry = cfg.watchlist[2]

    assumptions = _build_ticker_assumptions_from_watchlist(
        watchlist=[entry],
        rules=cfg.rules,
        scoring_port=_SCORING_PORT,
        fundamentals_overrides={
            "GLD": {
                "forward_pe_3yr": 31.0,
                "net_debt_ebitda": 2.5,
                "interest_coverage": 7.0,
            }
        },
    )

    assert assumptions["GLD"]["terminal_multiple"] == 31.0
    assert assumptions["GLD"]["discount_rate_pct"] == 9.5


def test_build_ticker_assumptions_does_not_force_discount_above_growth() -> None:
    """Test the expected behavior."""
    cfg = load_config(EXAMPLE_CONFIG_PATH)
    entry = cfg.watchlist[0].model_copy(
        update={
            "eps_growth": 40.0,
            "net_debt_ebitda": 0.5,
            "interest_coverage": 50.0,
        }
    )

    assumptions = _build_ticker_assumptions_from_watchlist(
        watchlist=[entry],
        rules=cfg.rules,
        scoring_port=_SCORING_PORT,
    )

    assert assumptions["NVDA"]["growth_rate_pct"] == 40.0
    # Discount is debt/coverage-derived only; no longer hard-coupled to growth + 1.
    assert assumptions["NVDA"]["discount_rate_pct"] == 8.3


class _StaticSnapshotRepository:
    def __init__(self, snapshot: dict[str, float] | None) -> None:
        self._snapshot = snapshot

    async def get_latest_fundamentals_snapshot_for_ticker(self, _ticker: str) -> dict[str, float] | None:
        return self._snapshot


@pytest.mark.asyncio
async def test_prebatch_fundamentals_overrides_use_stale_snapshot_when_fresh_incomplete() -> None:
    """Test the expected behavior."""
    cfg = load_config(EXAMPLE_CONFIG_PATH)
    repo = _StaticSnapshotRepository(
        {"forward_pe": 28.0, "net_debt_ebitda": 1.4, "interest_coverage": 11.0}
    )

    overrides, blocked = await _prepare_prebatch_fundamentals_overrides(
        watchlist=[cfg.watchlist[0]],
        rules=cfg.rules,
        repository=repo,  # type: ignore[arg-type]
        ibkr_fetch_fundamentals=lambda _ticker, _sector: {"forward_pe": 24.0},
    )

    assert blocked == set()
    assert overrides["NVDA"] == {
        "forward_pe_3yr": 28.0,
        "net_debt_ebitda": 1.4,
        "interest_coverage": 11.0,
    }


@pytest.mark.asyncio
async def test_prebatch_fundamentals_overrides_block_ticker_when_sources_unavailable() -> None:
    """Test the expected behavior."""
    cfg = load_config(EXAMPLE_CONFIG_PATH)
    repo = _StaticSnapshotRepository(None)

    overrides, blocked = await _prepare_prebatch_fundamentals_overrides(
        watchlist=[cfg.watchlist[0]],
        rules=cfg.rules,
        repository=repo,  # type: ignore[arg-type]
        ibkr_fetch_fundamentals=lambda _ticker, _sector: (_ for _ in ()).throw(
            RuntimeError("ibkr unavailable")
        ),
    )

    assert overrides == {}
    assert blocked == {"NVDA"}


@pytest.mark.asyncio
async def test_prebatch_fundamentals_overrides_accept_async_ibkr_provider() -> None:
    """Test the expected behavior."""
    cfg = load_config(EXAMPLE_CONFIG_PATH)
    repo = _StaticSnapshotRepository(None)

    async def _provider(_ticker: str, _sector: str) -> dict[str, float]:
        return {"forward_pe": 25.0, "net_debt_ebitda": 1.3, "interest_coverage": 9.2}

    overrides, blocked = await _prepare_prebatch_fundamentals_overrides(
        watchlist=[cfg.watchlist[0]],
        rules=cfg.rules,
        repository=repo,  # type: ignore[arg-type]
        ibkr_fetch_fundamentals=_provider,
    )

    assert blocked == set()
    assert overrides["NVDA"] == {
        "forward_pe_3yr": 25.0,
        "net_debt_ebitda": 1.3,
        "interest_coverage": 9.2,
    }


class _ConstantScoringPort:
    def __init__(self, score: float) -> None:
        self._score = score

    def score_opportunity(self, _entry: object, _rules: object) -> float:
        return self._score


def test_build_ticker_assumptions_uses_injected_scoring_port() -> None:
    """Test the expected behavior."""
    cfg = load_config(EXAMPLE_CONFIG_PATH)

    assumptions = _build_ticker_assumptions_from_watchlist(
        watchlist=[cfg.watchlist[0]],
        rules=cfg.rules,
        scoring_port=_ConstantScoringPort(0.8),  # type: ignore[arg-type]
    )

    assert assumptions["NVDA"]["composite_risk_score"] == 20.0
