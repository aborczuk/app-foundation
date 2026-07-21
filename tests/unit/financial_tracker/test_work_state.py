"""Unit coverage for work-item transitions and lease ownership."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from financial_tracker.work import (
    CoordinatorOwnershipError,
    InvalidWorkTransition,
    WorkItem,
    WorkState,
    cancel_work_item,
    complete_work_item,
    dead_letter_work_item,
    lease_work_item,
    recover_expired_lease,
    retry_work_item,
    start_work_item,
)


def test_work_item_requires_lease_owner_for_completion() -> None:
    """A different coordinator cannot complete another coordinator's work."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = lease_work_item(WorkItem(uuid4(), "tenant-a", "work-1", "refresh"), "worker-a", now=now)
    with pytest.raises(CoordinatorOwnershipError):
        start_work_item(item, "worker-b", now=now)
    start_work_item(item, "worker-a", now=now)
    complete_work_item(item, "worker-a", now=now)
    assert item.state is WorkState.SUCCEEDED


def test_expired_lease_returns_to_retry_wait() -> None:
    """Expired work becomes recoverable without replaying a completed result."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = lease_work_item(WorkItem(uuid4(), "tenant-a", "work-1", "refresh"), "worker-a", now=now, lease_seconds=10)
    recover_expired_lease(item, now=now + timedelta(seconds=11))
    assert item.state is WorkState.RETRY_WAIT
    assert item.lease_owner is None


def test_terminal_work_rejects_new_lease() -> None:
    """Succeeded work cannot be replayed through the state machine."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = lease_work_item(WorkItem(uuid4(), "tenant-a", "work-1", "refresh"), "worker-a", now=now)
    start_work_item(item, "worker-a", now=now)
    complete_work_item(item, "worker-a", now=now)
    with pytest.raises(InvalidWorkTransition):
        lease_work_item(item, "worker-b", now=now)


def test_invalid_identity_and_attempts_are_rejected() -> None:
    """A projected work item must have durable identity and valid attempt count."""
    with pytest.raises(ValueError):
        WorkItem(uuid4(), "tenant-a", " ", "refresh")
    with pytest.raises(ValueError):
        WorkItem(uuid4(), "tenant-a", "work-1", "refresh", attempts=-1)


def test_lease_validation_does_not_mutate_work_item() -> None:
    """Invalid coordinator input leaves queued work available for another lease."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = WorkItem(uuid4(), "tenant-a", "work-1", "refresh")
    with pytest.raises(CoordinatorOwnershipError):
        lease_work_item(item, " ", now=now)
    assert item.state is WorkState.QUEUED
    assert item.attempts == 0


def test_retry_can_be_released_and_released_again() -> None:
    """Recoverable failures clear ownership and increment attempts on relaunch."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = lease_work_item(WorkItem(uuid4(), "tenant-a", "work-1", "refresh"), "worker-a", now=now)
    start_work_item(item, "worker-a", now=now)
    retry_work_item(item, "worker-a", now=now)
    assert item.state is WorkState.RETRY_WAIT
    assert item.attempts == 1
    lease_work_item(item, "worker-b", now=now + timedelta(seconds=1))
    assert item.attempts == 2


def test_dead_letter_and_cancellation_require_ownership() -> None:
    """Terminal failure and cancellation cannot bypass coordinator ownership."""
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = lease_work_item(WorkItem(uuid4(), "tenant-a", "work-1", "refresh"), "worker-a", now=now)
    start_work_item(item, "worker-a", now=now)
    with pytest.raises(CoordinatorOwnershipError):
        dead_letter_work_item(item, "worker-b", now=now)
    dead_letter_work_item(item, "worker-a", now=now)
    assert item.state is WorkState.DEAD_LETTER

    queued = WorkItem(uuid4(), "tenant-a", "work-2", "refresh")
    with pytest.raises(CoordinatorOwnershipError):
        cancel_work_item(queued, " ", now=now)
    cancel_work_item(queued, "operator", now=now)
    assert queued.state is WorkState.CANCELLED
