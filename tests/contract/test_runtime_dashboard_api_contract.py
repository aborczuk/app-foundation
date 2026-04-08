"""Contract tests for runtime dashboard API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from csp_trader.state.db import get_db_connection, run_migrations
from csp_trader.state.positions import create_order, persist_sto_fill


def _build_temp_config(tmp_path: Path, db_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    base_cfg_path = repo_root / "config" / "e2e.yaml"
    cfg = yaml.safe_load(base_cfg_path.read_text(encoding="utf-8"))
    cfg["storage"]["db_path"] = str(db_path)
    cfg["storage"]["log_root_dir"] = str(tmp_path / "logs")
    cfg_path = tmp_path / "dashboard_contract.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return cfg_path


async def _seed_runtime_state(db_path: Path) -> None:
    async with get_db_connection(str(db_path)) as conn:
        await run_migrations(conn)
        position, _filled_sto = await persist_sto_fill(
            conn,
            ticker="NVDA",
            strike=100.0,
            expiry="2026-04-17",
            qty=1,
            fill_price=1.2,
            ibkr_conid=111,
            ibkr_order_id=222,
        )
        await create_order(
            conn,
            {
                "position_id": position["id"],
                "order_type": "BTC",
                "ibkr_order_id": 333,
                "qty_requested": 1,
                "qty_filled": 0,
                "limit_price_initial": 0.75,
                "status": "submitted",
            },
        )


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def _seed_timeline_state(db_path: Path) -> None:
    now = datetime.now(UTC)
    stale_opened = now - timedelta(hours=36)
    recent_opened = now - timedelta(hours=4)
    cancel_submitted = now - timedelta(hours=3)
    cancelled_at = now - timedelta(hours=2, minutes=30)

    async with get_db_connection(str(db_path)) as conn:
        await run_migrations(conn)

        await persist_sto_fill(
            conn,
            ticker="AAPL",
            strike=90.0,
            expiry="2026-04-17",
            qty=1,
            fill_price=1.05,
            ibkr_conid=5001,
            ibkr_order_id=5002,
            submitted_at=_iso(stale_opened - timedelta(minutes=2)),
            filled_at=_iso(stale_opened),
        )

        recent_position, _ = await persist_sto_fill(
            conn,
            ticker="MSFT",
            strike=120.0,
            expiry="2026-04-17",
            qty=1,
            fill_price=1.35,
            ibkr_conid=6001,
            ibkr_order_id=6002,
            submitted_at=_iso(recent_opened - timedelta(minutes=1)),
            filled_at=_iso(recent_opened),
        )
        await create_order(
            conn,
            {
                "position_id": recent_position["id"],
                "order_type": "BTC",
                "ibkr_order_id": 7001,
                "qty_requested": 1,
                "qty_filled": 0,
                "limit_price_initial": 0.65,
                "status": "cancelled",
                "submitted_at": _iso(cancel_submitted),
                "cancelled_at": _iso(cancelled_at),
                "cancel_reason": "risk_limit_breached",
            },
        )


@pytest.mark.asyncio
async def test_runtime_snapshot_contract_shape_and_freshness_metadata(tmp_path: Path) -> None:
    """Test the expected behavior."""
    from csp_trader.dashboard.app import create_dashboard_app

    db_path = tmp_path / "dashboard_contract.db"
    config_path = _build_temp_config(tmp_path, db_path)
    await _seed_runtime_state(db_path)

    app = create_dashboard_app(config_path=str(config_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/dashboard/runtime-snapshot")
    assert response.status_code == 200

    payload = response.json()
    assert payload["snapshot_id"]
    assert payload["captured_at"]
    assert isinstance(payload["snapshot_age_seconds"], int)
    assert payload["snapshot_age_seconds"] >= 0
    assert payload["stale_threshold_seconds"] == 10
    assert payload["max_last_known_age_seconds"] == 86400
    assert isinstance(payload["is_last_known_snapshot"], bool)

    assert isinstance(payload["watchlist_items"], list)
    assert isinstance(payload["active_orders"], list)
    assert isinstance(payload["open_positions"], list)
    assert isinstance(payload["reconciliation_statuses"], list)
    assert isinstance(payload["data_source_health"], dict)

    first_watch = payload["watchlist_items"][0]
    assert {"ticker", "status", "themes_summary", "last_updated_at"} <= set(first_watch.keys())

    first_order = payload["active_orders"][0]
    assert {
        "order_id",
        "ticker",
        "order_type",
        "price",
        "annualized_return",
        "lifecycle_state",
        "latest_transition_at",
        "latest_reason",
    } <= set(first_order.keys())
    assert first_order["price"] is None or isinstance(first_order["price"], float)
    assert first_order["annualized_return"] is None or isinstance(first_order["annualized_return"], float)

    first_pos = payload["open_positions"][0]
    assert {
        "position_id",
        "ticker",
        "position_state",
        "price",
        "annualized_return",
        "latest_transition_at",
        "latest_reason",
    } <= set(first_pos.keys())
    assert first_pos["price"] is None or isinstance(first_pos["price"], float)
    assert first_pos["annualized_return"] is None or isinstance(first_pos["annualized_return"], float)


@pytest.mark.asyncio
async def test_health_contract_shape_includes_freshness_metadata(tmp_path: Path) -> None:
    """Test the expected behavior."""
    from csp_trader.dashboard.app import create_dashboard_app

    db_path = tmp_path / "dashboard_health.db"
    config_path = _build_temp_config(tmp_path, db_path)
    await _seed_runtime_state(db_path)

    app = create_dashboard_app(config_path=str(config_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/dashboard/health")
    assert response.status_code == 200

    payload = response.json()
    assert {"service_status", "runtime_source_status", "broker_source_status"} <= set(payload.keys())
    assert "last_successful_live_sync_at" in payload

    # Contract requires explicit freshness/cadence metadata on health endpoint.
    assert payload["refresh_interval_seconds"] == 5
    assert payload["refresh_timeout_seconds"] == 3
    assert payload["stale_threshold_seconds"] == 10
    assert payload["unavailable_after_failures"] == 3


@pytest.mark.asyncio
async def test_runtime_snapshot_error_envelope_when_source_unavailable(tmp_path: Path) -> None:
    """Test the expected behavior."""
    from csp_trader.dashboard.app import create_dashboard_app

    db_path = tmp_path / "dashboard_unavailable.db"
    config_path = _build_temp_config(tmp_path, db_path)
    # Intentionally skip migrations to force read failure / unavailable envelope.

    app = create_dashboard_app(config_path=str(config_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/dashboard/runtime-snapshot")
    assert response.status_code == 503

    payload = response.json()
    assert payload["error_code"] == "RUNTIME_SOURCE_UNAVAILABLE"
    assert payload["source"] == "runtime"
    assert payload["retryable"] is True
    assert isinstance(payload["error_message"], str) and payload["error_message"]


@pytest.mark.asyncio
async def test_events_query_parameter_validation_and_filter_contract(tmp_path: Path) -> None:
    """Test the expected behavior."""
    from csp_trader.dashboard.app import create_dashboard_app

    db_path = tmp_path / "dashboard_events_query.db"
    config_path = _build_temp_config(tmp_path, db_path)
    await _seed_timeline_state(db_path)

    app = create_dashboard_app(config_path=str(config_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        invalid_cases = [
            "/dashboard/events?limit=0",
            "/dashboard/events?limit=201",
            "/dashboard/events?entity_type=invalid",
            "/dashboard/events?from_ts=not-a-date",
            "/dashboard/events?cursor=not-base64",
        ]
        for route in invalid_cases:
            response = await client.get(route)
            assert response.status_code == 400
            payload = response.json()
            assert payload["error_code"] == "INVALID_QUERY"
            assert payload["retryable"] is False
            assert payload["source"] == "dashboard"
            assert isinstance(payload["error_message"], str) and payload["error_message"]

        filtered = await client.get("/dashboard/events?entity_type=order&outcome_status=failed&limit=10")
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert isinstance(filtered_payload["events"], list)
    for event in filtered_payload["events"]:
        assert event["entity_type"] == "order"
        assert event["outcome_status"] == "failed"
        assert isinstance(event["reason"], str) and event["reason"]


@pytest.mark.asyncio
async def test_events_pagination_metadata_and_default_window_contract(tmp_path: Path) -> None:
    """Test the expected behavior."""
    from csp_trader.dashboard.app import create_dashboard_app

    db_path = tmp_path / "dashboard_events_pagination.db"
    config_path = _build_temp_config(tmp_path, db_path)
    await _seed_timeline_state(db_path)

    app = create_dashboard_app(config_path=str(config_path))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        default_window = await client.get("/dashboard/events")
        assert default_window.status_code == 200
        default_payload = default_window.json()
        assert isinstance(default_payload["events"], list)
        assert "next_cursor" in default_payload

        now = datetime.now(UTC)
        for event in default_payload["events"]:
            occurred_at = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))
            assert now - occurred_at <= timedelta(hours=24)

        first_page = await client.get("/dashboard/events?limit=2")
        assert first_page.status_code == 200
        first_payload = first_page.json()
        assert len(first_payload["events"]) <= 2
        assert "next_cursor" in first_payload

        if first_payload["next_cursor"]:
            second_page = await client.get(f"/dashboard/events?limit=2&cursor={first_payload['next_cursor']}")
            assert second_page.status_code == 200
            second_payload = second_page.json()
            if first_payload["events"] and second_payload["events"]:
                first_last = datetime.fromisoformat(
                    first_payload["events"][-1]["occurred_at"].replace("Z", "+00:00")
                )
                second_first = datetime.fromisoformat(
                    second_payload["events"][0]["occurred_at"].replace("Z", "+00:00")
                )
                assert second_first > first_last

        older_than_max_window = now - timedelta(days=31)
        over_window = await client.get(
            f"/dashboard/events?from_ts={_iso(older_than_max_window)}&to_ts={_iso(now)}"
        )
    assert over_window.status_code == 400
    over_window_payload = over_window.json()
    assert over_window_payload["error_code"] == "INVALID_QUERY"
    assert over_window_payload["retryable"] is False
    assert over_window_payload["source"] == "dashboard"
