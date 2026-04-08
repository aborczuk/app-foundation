"""Test module."""

from __future__ import annotations

import math
from time import perf_counter

import pytest

from clickup_control_plane.state_store import StateStore


@pytest.mark.asyncio
async def test_duplicate_event_is_idempotent(tmp_path) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-dup.db"
    store = StateStore(db_path)
    await store.initialize()

    first = await store.record_event_and_acquire_lock(
        task_id="task-1",
        event_id="evt-1",
        run_id="run-1",
    )
    second = await store.record_event_and_acquire_lock(
        task_id="task-1",
        event_id="evt-1",
        run_id="run-2",
    )

    assert first.decision == "dispatch"
    assert second.decision == "skip_duplicate"
    active = await store.get_active_run(task_id="task-1")
    assert active is not None
    assert active.run_id == "run-1"


@pytest.mark.asyncio
async def test_mid_transaction_failure_rolls_back_without_partial_writes(tmp_path, monkeypatch) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-rollback.db"
    store = StateStore(db_path)
    await store.initialize()

    async def explode() -> None:
        raise RuntimeError("forced failure after dedupe insert")

    monkeypatch.setattr(store, "_after_dedupe_insert_hook", explode)

    with pytest.raises(RuntimeError, match="forced failure"):
        await store.record_event_and_acquire_lock(
            task_id="task-1",
            event_id="evt-rollback",
            run_id="run-rollback",
        )

    processed = await store.get_processed_event(event_id="evt-rollback")
    active = await store.get_active_run(task_id="task-1")
    assert processed is None
    assert active is None


@pytest.mark.asyncio
async def test_active_run_conflict_keeps_original_lock_and_records_rejection(tmp_path) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-conflict.db"
    store = StateStore(db_path)
    await store.initialize()

    first = await store.record_event_and_acquire_lock(
        task_id="task-1",
        event_id="evt-1",
        run_id="run-1",
    )
    conflict = await store.record_event_and_acquire_lock(
        task_id="task-1",
        event_id="evt-2",
        run_id="run-2",
    )

    active = await store.get_active_run(task_id="task-1")
    processed = await store.get_processed_event(event_id="evt-2")

    assert first.decision == "dispatch"
    assert conflict.decision == "reject_active_run"
    assert conflict.conflicting_run_id == "run-1"
    assert active is not None
    assert active.run_id == "run-1"
    assert processed is not None
    assert processed.decision == "reject_active_run"


@pytest.mark.asyncio
async def test_set_active_run_id_updates_provisional_running_lock(tmp_path) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-run-id.db"
    store = StateStore(db_path)
    await store.initialize()

    await store.record_event_and_acquire_lock(
        task_id="task-1",
        event_id="evt-1",
        run_id="run_pending_evt-1",
    )
    updated = await store.set_active_run_id(
        task_id="task-1",
        current_run_id="run_pending_evt-1",
        new_run_id="run-123",
    )

    active = await store.get_active_run(task_id="task-1")
    assert updated is True
    assert active is not None
    assert active.run_id == "run-123"


@pytest.mark.asyncio
async def test_persist_terminal_decision_releases_matching_running_lock_atomically(tmp_path) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-terminal.db"
    store = StateStore(db_path)
    await store.initialize()

    await store.record_event_and_acquire_lock(
        task_id="task-1",
        event_id="evt-1",
        run_id="run-1",
    )
    persisted = await store.persist_terminal_decision(
        task_id="task-1",
        event_id="evt-1",
        decision="dispatch_failed",
        active_run_id="run-1",
        release_lock=True,
        final_state="released",
    )

    processed = await store.get_processed_event(event_id="evt-1")
    active = await store.get_active_run(task_id="task-1")
    assert persisted is True
    assert processed is not None
    assert processed.decision == "dispatch_failed"
    assert active is None


@pytest.mark.asyncio
async def test_persist_terminal_decision_with_missing_run_id_rolls_back_without_partial_writes(
    tmp_path,
) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-terminal-missing-run-id.db"
    store = StateStore(db_path)
    await store.initialize()

    await store.record_event_and_acquire_lock(
        task_id="task-1",
        event_id="evt-1",
        run_id="run-1",
    )
    persisted = await store.persist_terminal_decision(
        task_id="task-1",
        event_id="evt-1",
        decision="dispatch_failed",
        active_run_id=None,
        release_lock=True,
    )

    processed = await store.get_processed_event(event_id="evt-1")
    active = await store.get_active_run(task_id="task-1")
    assert persisted is False
    assert processed is not None
    assert processed.decision == "dispatch"
    assert active is not None
    assert active.run_id == "run-1"


@pytest.mark.asyncio
async def test_persist_terminal_decision_with_mismatched_run_id_rolls_back_without_partial_writes(
    tmp_path,
) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-terminal-mismatched-run-id.db"
    store = StateStore(db_path)
    await store.initialize()

    await store.record_event_and_acquire_lock(
        task_id="task-1",
        event_id="evt-1",
        run_id="run-1",
    )
    persisted = await store.persist_terminal_decision(
        task_id="task-1",
        event_id="evt-1",
        decision="dispatch_failed",
        active_run_id="run-other",
        release_lock=True,
    )

    processed = await store.get_processed_event(event_id="evt-1")
    active = await store.get_active_run(task_id="task-1")
    assert persisted is False
    assert processed is not None
    assert processed.decision == "dispatch"
    assert active is not None
    assert active.run_id == "run-1"


@pytest.mark.asyncio
async def test_record_event_and_acquire_lock_p95_under_50ms(tmp_path) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-latency.db"
    store = StateStore(db_path)
    await store.initialize()

    # Warm the connection and WAL pages so the benchmark reflects steady-state work.
    for idx in range(3):
        await store.record_event_and_acquire_lock(
            task_id=f"warmup-task-{idx}",
            event_id=f"warmup-evt-{idx}",
            run_id=f"warmup-run-{idx}",
        )

    latencies: list[float] = []
    for idx in range(20):
        started = perf_counter()
        result = await store.record_event_and_acquire_lock(
            task_id=f"task-{idx}",
            event_id=f"evt-{idx}",
            run_id=f"run-{idx}",
        )
        elapsed = perf_counter() - started
        latencies.append(elapsed)
        assert result.decision == "dispatch"

    ordered = sorted(latencies)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    p95_seconds = ordered[p95_index]

    assert p95_seconds < 0.05


@pytest.mark.asyncio
async def test_record_processed_event_is_idempotent_for_non_dispatch_paths(tmp_path) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-processed-event.db"
    store = StateStore(db_path)
    await store.initialize()

    inserted = await store.record_processed_event(
        task_id="task-1",
        event_id="evt-cancel-1",
        decision="pending",
    )
    duplicate = await store.record_processed_event(
        task_id="task-1",
        event_id="evt-cancel-1",
        decision="pending",
    )
    row = await store.get_processed_event(event_id="evt-cancel-1")

    assert inserted is True
    assert duplicate is False
    assert row is not None
    assert row.decision == "pending"


@pytest.mark.asyncio
async def test_paused_run_upsert_fetch_and_clear_flow(tmp_path) -> None:
    """Test the expected behavior."""
    db_path = tmp_path / "state-store-paused-run.db"
    store = StateStore(db_path)
    await store.initialize()

    await store.upsert_paused_run(
        task_id="task-1",
        run_id="run-1",
        workflow_type="build_spec",
        context_ref="specs/017/spec.md",
        execution_policy="manual-test",
        timeout_at_utc="2026-04-04T12:00:00+00:00",
        prompt="Need operator approval",
    )
    paused = await store.get_paused_run(task_id="task-1")
    assert paused is not None
    assert paused.run_id == "run-1"
    assert paused.workflow_type == "build_spec"
    assert paused.prompt == "Need operator approval"

    cleared_wrong = await store.clear_paused_run(task_id="task-1", run_id="run-other")
    still_paused = await store.get_paused_run(task_id="task-1")
    assert cleared_wrong is False
    assert still_paused is not None

    cleared = await store.clear_paused_run(task_id="task-1", run_id="run-1")
    assert cleared is True
    assert await store.get_paused_run(task_id="task-1") is None
