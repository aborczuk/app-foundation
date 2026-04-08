"""Unit tests for conversational assumptions normalization guardrails."""

from __future__ import annotations

from ib_valuation.valuation.conversation_adapter import ConversationAdapter


def test_normalize_allows_projection_growth_above_discount_rate() -> None:
    """Test the expected behavior."""
    adapter = ConversationAdapter()

    normalized = adapter.normalize_for_ticker(
        "NVDA",
        {
            "base_fcf_per_share": 9.0,
            "growth_rate_pct": 35.0,
            "discount_rate_pct": 12.0,
            "terminal_multiple": 20.0,
            "projection_years": 5,
        },
    )

    assert normalized.growth_rate_pct == 35.0
    assert normalized.discount_rate_pct == 12.0


def test_normalize_still_rejects_non_positive_base_fcf() -> None:
    """Test the expected behavior."""
    adapter = ConversationAdapter()

    try:
        adapter.normalize_for_ticker(
            "NVDA",
            {
                "base_fcf_per_share": 0.0,
                "growth_rate_pct": 12.0,
                "discount_rate_pct": 10.0,
                "terminal_multiple": 18.0,
                "projection_years": 5,
            },
        )
    except ValueError as exc:
        assert "base_fcf_per_share" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-positive base_fcf_per_share")
