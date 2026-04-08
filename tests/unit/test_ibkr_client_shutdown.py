"""Unit tests for IBKR client intentional shutdown behavior."""

from __future__ import annotations

import asyncio

import pytest

from csp_trader.ibkr.client import IBKRClient


class _DummyLoop:
    def __init__(self) -> None:
        self.scheduled = False

    def create_task(self, coro):
        self.scheduled = True
        coro.close()  # avoid "coroutine was never awaited" warnings
        return None


@pytest.mark.asyncio
async def test_disconnect_suppresses_watchdog_reconnect_on_intentional_shutdown(monkeypatch) -> None:
    """Intentional disconnect must not schedule reconnect via disconnected callback."""
    ibkr_client = IBKRClient()
    await ibkr_client.start_watchdog("127.0.0.1", 4001, 12)

    loop = _DummyLoop()
    monkeypatch.setattr(asyncio, "get_event_loop", lambda: loop)
    monkeypatch.setattr(ibkr_client._ib, "isConnected", lambda: True)

    # Simulate ib_async emitting disconnectedEvent during disconnect().
    monkeypatch.setattr(ibkr_client._ib, "disconnect", lambda: ibkr_client._on_disconnected())

    await ibkr_client.disconnect()

    assert ibkr_client._shutdown_in_progress is True
    assert ibkr_client._watchdog_registered is False
    assert ibkr_client._order_pause is False
    assert loop.scheduled is False


@pytest.mark.asyncio
async def test_disconnect_cancels_active_watchdog_task(monkeypatch) -> None:
    """Disconnect should cancel and clear an in-flight watchdog reconnect task."""
    ibkr_client = IBKRClient()
    await ibkr_client.start_watchdog("127.0.0.1", 4001, 12)

    async def _blocked() -> None:
        await asyncio.sleep(3600)

    task = asyncio.create_task(_blocked())
    ibkr_client._watchdog_task = task

    monkeypatch.setattr(ibkr_client._ib, "isConnected", lambda: False)

    await ibkr_client.disconnect()

    assert task.cancelled()
    assert ibkr_client._watchdog_task is None
    assert ibkr_client._watchdog_registered is False
