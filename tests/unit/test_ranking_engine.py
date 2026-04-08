"""Unit tests for deterministic ranking and override behavior."""

from __future__ import annotations

from ib_valuation.valuation.ranking_engine import rank_entries


def test_rank_entries_applies_canonical_ordering() -> None:
    """Test the expected behavior."""
    ranked = rank_entries(
        [
            {
                "ticker": "MSFT",
                "weighted_composite_score": 88.0,
                "target_price": 120.0,
                "manual_override_rank": None,
            },
            {
                "ticker": "NVDA",
                "weighted_composite_score": 92.0,
                "target_price": 115.0,
                "manual_override_rank": None,
            },
            {
                "ticker": "AAPL",
                "weighted_composite_score": 70.0,
                "target_price": 99.0,
                "manual_override_rank": 1,
            },
            {
                "ticker": "AMZN",
                "weighted_composite_score": 65.0,
                "target_price": 98.0,
                "manual_override_rank": 1,
            },
        ]
    )

    assert [item["ticker"] for item in ranked] == ["AAPL", "AMZN", "NVDA", "MSFT"]
    assert [item["effective_rank"] for item in ranked] == [1, 2, 3, 4]
    assert ranked[0]["status"] == "overridden"
    assert ranked[2]["status"] == "ranked"


def test_rank_entries_breaks_non_override_ties_by_target_then_ticker() -> None:
    """Test the expected behavior."""
    ranked = rank_entries(
        [
            {
                "ticker": "MSFT",
                "weighted_composite_score": 80.0,
                "target_price": 100.0,
                "manual_override_rank": None,
            },
            {
                "ticker": "AAPL",
                "weighted_composite_score": 80.0,
                "target_price": 100.0,
                "manual_override_rank": None,
            },
            {
                "ticker": "NVDA",
                "weighted_composite_score": 80.0,
                "target_price": 105.0,
                "manual_override_rank": None,
            },
        ]
    )

    assert [item["ticker"] for item in ranked] == ["NVDA", "AAPL", "MSFT"]
    assert [item["model_rank"] for item in ranked] == [1, 2, 3]
