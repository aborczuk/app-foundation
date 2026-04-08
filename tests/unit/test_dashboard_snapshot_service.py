"""T005: refresh-worker lifecycle tests for dashboard snapshot service."""

from __future__ import annotations

import asyncio

import pytest

from csp_trader.dashboard.snapshot_service import SnapshotService


@pytest.mark.asyncio
async def test_snapshot_service_defaults_use_required_intervals() -> None:
    """Test the expected behavior."""
    service = SnapshotService(snapshot_loader=lambda: {"captured_at": "2026-03-19T00:00:00Z"})
    assert service.refresh_interval_seconds == 5.0
    assert service.refresh_timeout_seconds == 3.0
    assert service.shutdown_grace_seconds == 5.0


@pytest.mark.asyncio
async def test_snapshot_service_start_ticks_and_stop_cancels_worker() -> None:
    """Test the expected behavior."""
    calls = 0

    async def _loader() -> dict:
        nonlocal calls
        calls += 1
        return {"captured_at": "2026-03-19T00:00:00Z"}

    service = SnapshotService(
        snapshot_loader=_loader,
        refresh_interval_seconds=0.05,
        refresh_timeout_seconds=0.03,
        shutdown_grace_seconds=0.05,
    )

    await service.start()
    await asyncio.sleep(0.12)
    await service.stop()

    assert calls >= 2
    assert service.worker_task is None


@pytest.mark.asyncio
async def test_snapshot_service_timeout_transitions_to_unavailable_after_three_failures() -> None:
    """Test the expected behavior."""
    async def _loader() -> dict:
        await asyncio.sleep(0.05)
        return {"captured_at": "2026-03-19T00:00:00Z"}

    service = SnapshotService(
        snapshot_loader=_loader,
        refresh_interval_seconds=0.01,
        refresh_timeout_seconds=0.005,
        shutdown_grace_seconds=0.05,
    )

    await service.start()
    await asyncio.sleep(0.06)
    await service.stop()

    assert service.consecutive_refresh_failures >= 3
    assert service.runtime_source_status == "unavailable"


@pytest.mark.asyncio
async def test_snapshot_service_force_stop_fallback_after_shutdown_grace() -> None:
    """Test the expected behavior."""
    started = asyncio.Event()

    async def _loader() -> dict:
        started.set()
        await asyncio.Event().wait()
        return {"captured_at": "2026-03-19T00:00:00Z"}

    service = SnapshotService(
        snapshot_loader=_loader,
        refresh_interval_seconds=0.01,
        refresh_timeout_seconds=0.5,
        shutdown_grace_seconds=0.01,
    )

    await service.start()
    await started.wait()
    await service.stop()

    assert service.worker_task is None
