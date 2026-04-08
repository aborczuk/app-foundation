"""Unit tests for atomic watchlist backup/write/restore behavior."""

from __future__ import annotations

from pathlib import Path

import yaml
from ib_valuation.valuation.watchlist_gateway import WatchlistGateway


def _seed_watchlist(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {"watchlist": [{"ticker": "NVDA", "target_price": 110.0, "themes": ["ai"]}]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_backup_and_write_atomic_creates_backup_and_replaces_payload(tmp_path: Path) -> None:
    """Test the expected behavior."""
    watchlist_path = tmp_path / "watchlist.yaml"
    _seed_watchlist(watchlist_path)
    gateway = WatchlistGateway(watchlist_path)

    result = gateway.backup_and_write_atomic(
        {"watchlist": [{"ticker": "MSFT", "target_price": 380.0, "themes": ["software"]}]}
    )

    assert result["watchlist_path"] == str(watchlist_path)
    assert Path(result["backup_path"]).exists()
    payload = gateway.load_yaml()
    assert [entry["ticker"] for entry in payload["watchlist"]] == ["MSFT"]


def test_rollback_action_restores_previous_payload(tmp_path: Path) -> None:
    """Test the expected behavior."""
    watchlist_path = tmp_path / "watchlist.yaml"
    _seed_watchlist(watchlist_path)
    gateway = WatchlistGateway(watchlist_path)

    apply_response = gateway.apply_curation_action(
        {
            "action_id": "push-1",
            "action_type": "push",
            "ticker": "AAPL",
            "target_price": 210.0,
            "scoring_attributes": {"tier_1_fundamental_value": 81.0},
            "themes": ["platform"],
            "high_debt_flag": False,
            "valuation_version_id": "ver-1",
            "approved_by": "trader",
            "approved_at": "2026-03-15T00:00:00Z",
        }
    )

    payload_after_apply = gateway.load_yaml()
    assert "AAPL" in [entry["ticker"] for entry in payload_after_apply["watchlist"]]

    rollback_response = gateway.rollback_action(
        action_id="push-1",
        backup_path=apply_response["backup_path"],
        reason="unit_test_restore",
    )
    assert rollback_response["status"] == "rolled_back"

    restored = gateway.load_yaml()
    tickers = [entry["ticker"] for entry in restored["watchlist"]]
    assert "NVDA" in tickers
    assert "AAPL" not in tickers
