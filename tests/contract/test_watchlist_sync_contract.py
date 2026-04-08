"""Contract tests for Part 1 watchlist sync apply/error/rollback behavior."""

from __future__ import annotations

from pathlib import Path

import yaml
from ib_valuation.valuation.watchlist_gateway import WatchlistGateway


def _seed_watchlist(path: Path) -> None:
    payload = {
        "watchlist": [
            {"ticker": "MSFT", "target_price": 380.0, "themes": ["software"]},
            {"ticker": "NVDA", "target_price": 110.0, "themes": ["ai"]},
        ]
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_watchlist_sync_push_apply_returns_contract_shape(tmp_path: Path) -> None:
    """Test the expected behavior."""
    watchlist_path = tmp_path / "config.yaml"
    _seed_watchlist(watchlist_path)
    gateway = WatchlistGateway(watchlist_path)

    response = gateway.apply_curation_action(
        {
            "action_id": "a-1",
            "action_type": "push",
            "ticker": "AAPL",
            "target_price": 210.0,
            "scoring_attributes": {"tier_1_fundamental_value": 80.0},
            "themes": ["platform"],
            "high_debt_flag": False,
            "valuation_version_id": "v-1",
            "approved_by": "trader",
            "approved_at": "2026-03-15T00:00:00Z",
        }
    )

    assert response["action_id"] == "a-1"
    assert response["status"] == "applied"
    assert response["watchlist_path"] == str(watchlist_path)
    assert response["backup_path"].startswith(str(watchlist_path) + ".bak.")
    assert response["applied_at"].endswith("Z")


def test_watchlist_sync_failed_apply_returns_error_contract(tmp_path: Path) -> None:
    """Test the expected behavior."""
    watchlist_path = tmp_path / "config.yaml"
    _seed_watchlist(watchlist_path)
    gateway = WatchlistGateway(watchlist_path)

    response = gateway.apply_curation_action(
        {
            "action_id": "a-2",
            "action_type": "push",
            "ticker": "AAPL",
            "approved_by": "trader",
            "approved_at": "2026-03-15T00:00:00Z",
        }
    )

    assert response["action_id"] == "a-2"
    assert response["status"] == "failed"
    assert response["error_code"] == "WATCHLIST_PAYLOAD_INVALID"
    assert isinstance(response["error_reason"], str)
    assert response["retryable"] is False
    assert response["failed_at"].endswith("Z")


def test_watchlist_sync_rollback_restores_backup_and_reports_contract(tmp_path: Path) -> None:
    """Test the expected behavior."""
    watchlist_path = tmp_path / "config.yaml"
    _seed_watchlist(watchlist_path)
    gateway = WatchlistGateway(watchlist_path)

    apply_response = gateway.apply_curation_action(
        {
            "action_id": "a-3",
            "action_type": "pull",
            "ticker": "NVDA",
            "approved_by": "trader",
            "approved_at": "2026-03-15T00:00:00Z",
        }
    )
    backup_path = apply_response["backup_path"]

    rollback = gateway.rollback_action(
        action_id="a-3",
        backup_path=backup_path,
        reason="operator_requested",
    )

    assert rollback["action_id"] == "a-3"
    assert rollback["status"] == "rolled_back"
    assert rollback["watchlist_path"] == str(watchlist_path)
    assert rollback["backup_path"] == backup_path
    assert rollback["rolled_back_at"].endswith("Z")

    payload = gateway.load_yaml()
    tickers = [entry["ticker"] for entry in payload.get("watchlist", [])]
    assert "NVDA" in tickers
