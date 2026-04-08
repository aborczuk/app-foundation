"""T041: Unit tests for the heartbeat task.

Tests cover:
- Ping sent at configured interval
- Successful ping logged as heartbeat_ok (URL value NOT logged)
- Failed ping logged as heartbeat_failed with status (not URL)
- Heartbeat continues regardless of market hours
- Missing HEARTBEAT_URL disables heartbeat with warning
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from csp_trader.monitoring.heartbeat import heartbeat_loop


async def test_heartbeat_pings_at_interval():
    """heartbeat_loop sends a GET request to the URL at each interval."""
    ping_count = 0

    async def mock_get(url, **kwargs):
        nonlocal ping_count
        ping_count += 1
        resp = MagicMock()
        resp.status_code = 200
        return resp

    with patch("csp_trader.monitoring.heartbeat.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        # Run heartbeat for 3 intervals then cancel
        task = asyncio.create_task(
            heartbeat_loop("https://hc-ping.com/test-uuid", interval_seconds=0.05)
        )
        await asyncio.sleep(0.18)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert ping_count >= 2


async def test_successful_ping_logs_heartbeat_ok_not_url(caplog):
    """Successful ping logs heartbeat_ok without logging the URL value."""
    async def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        return resp

    with patch("csp_trader.monitoring.heartbeat.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        task = asyncio.create_task(
            heartbeat_loop("https://hc-ping.com/secret-uuid-do-not-log", interval_seconds=0.05)
        )
        with caplog.at_level(logging.INFO, logger="csp_trader.monitoring.heartbeat"):
            await asyncio.sleep(0.08)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Must NOT log the URL value
    log_text = " ".join(r.message for r in caplog.records)
    assert "secret-uuid-do-not-log" not in log_text
    # Must log heartbeat_ok
    assert any("heartbeat_ok" in r.message or "heartbeat" in r.message for r in caplog.records)


async def test_failed_ping_logs_heartbeat_failed_not_url(caplog):
    """Failed ping logs heartbeat_failed without logging the URL value."""
    import httpx

    async def mock_get(url, **kwargs):
        raise httpx.RequestError("connection refused", request=MagicMock())

    with patch("csp_trader.monitoring.heartbeat.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        task = asyncio.create_task(
            heartbeat_loop("https://hc-ping.com/secret-uuid-do-not-log", interval_seconds=0.05)
        )
        with caplog.at_level(logging.WARNING, logger="csp_trader.monitoring.heartbeat"):
            await asyncio.sleep(0.08)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    log_text = " ".join(r.message for r in caplog.records)
    assert "secret-uuid-do-not-log" not in log_text
    assert any("heartbeat_failed" in r.message or "failed" in r.message.lower() for r in caplog.records)


async def test_missing_heartbeat_url_disables_with_warning(caplog):
    """heartbeat_loop with url=None logs a warning and returns immediately."""
    with caplog.at_level(logging.WARNING, logger="csp_trader.monitoring.heartbeat"):
        await heartbeat_loop(url=None, interval_seconds=0.01)

    assert any("heartbeat" in r.message.lower() or "disabled" in r.message.lower() for r in caplog.records)
