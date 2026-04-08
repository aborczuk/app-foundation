"""Unit tests for graceful background-task shutdown helpers."""

from __future__ import annotations

import asyncio

import pytest

from csp_trader.main import _cancel_background_tasks


@pytest.mark.asyncio
async def test_cancel_background_tasks_cancels_pending_tasks() -> None:
    """Test the expected behavior."""
    started = asyncio.Event()

    async def _worker() -> None:
        started.set()
        await asyncio.sleep(3600)

    task = asyncio.create_task(_worker())
    await started.wait()
    tasks = {"NVDA": task}

    await _cancel_background_tasks(tasks, "sto")

    assert task.cancelled() is True
    assert tasks == {}


@pytest.mark.asyncio
async def test_cancel_background_tasks_clears_done_tasks() -> None:
    """Test the expected behavior."""
    async def _done() -> str:
        return "ok"

    task = asyncio.create_task(_done())
    await task
    tasks = {"done": task}

    await _cancel_background_tasks(tasks, "sto")

    assert tasks == {}


@pytest.mark.asyncio
async def test_cancel_background_tasks_swallows_task_errors() -> None:
    """Test the expected behavior."""
    started = asyncio.Event()

    async def _worker_with_error() -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise RuntimeError("cleanup failed") from None

    task = asyncio.create_task(_worker_with_error())
    await started.wait()
    tasks = {"ERR": task}

    await _cancel_background_tasks(tasks, "btc")

    assert tasks == {}
    assert task.done() is True
    assert isinstance(task.exception(), RuntimeError)
