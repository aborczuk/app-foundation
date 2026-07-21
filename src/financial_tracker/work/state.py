"""Durable work-item lifecycle rules and coordinator lease ownership."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import UUID


class WorkState(StrEnum):
    """Persisted work-item states supported by the coordinator."""

    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class InvalidWorkTransition(ValueError):
    """Raised when a work item attempts an illegal lifecycle transition."""


class CoordinatorOwnershipError(PermissionError):
    """Raised when a coordinator does not own a valid work-item lease."""


@dataclass(slots=True)
class WorkItem:
    """Mutable state projection for one durable, retry-safe work item."""

    id: UUID
    tenant_id: str
    idempotency_key: str
    kind: str
    state: WorkState = WorkState.QUEUED
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    attempts: int = 0

    def __post_init__(self) -> None:
        """Normalize durable identity and reject invalid projected state."""
        for field_name in ("tenant_id", "idempotency_key", "kind"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
            setattr(self, field_name, value.strip())
        if isinstance(self.attempts, bool) or self.attempts < 0:
            raise ValueError("attempts must be non-negative")


def _utc_now(value: datetime | None) -> datetime:
    """Return an aware UTC timestamp for deterministic transition checks."""
    resolved = value or datetime.now(timezone.utc)
    if resolved.tzinfo is None:
        raise ValueError("transition timestamps must be timezone-aware")
    return resolved.astimezone(timezone.utc)


def _require_coordinator(coordinator_id: str) -> str:
    """Normalize a coordinator identifier and reject anonymous ownership."""
    normalized = coordinator_id.strip()
    if not normalized:
        raise CoordinatorOwnershipError("coordinator_id must be non-empty")
    return normalized


def _require_owner(item: WorkItem, coordinator_id: str, now: datetime) -> str:
    """Require the named coordinator to hold an unexpired lease."""
    coordinator = _require_coordinator(coordinator_id)
    if item.lease_owner != coordinator or item.lease_expires_at is None or item.lease_expires_at <= now:
        raise CoordinatorOwnershipError("coordinator does not hold a valid work-item lease")
    return coordinator


def lease_work_item(
    item: WorkItem,
    coordinator_id: str,
    *,
    now: datetime | None = None,
    lease_seconds: int = 300,
) -> WorkItem:
    """Lease queued or retry-wait work for one coordinator and increment attempts."""
    if item.state not in {WorkState.QUEUED, WorkState.RETRY_WAIT}:
        raise InvalidWorkTransition(f"cannot lease work in state {item.state}")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    effective_now = _utc_now(now)
    coordinator = _require_coordinator(coordinator_id)
    item.state = WorkState.LEASED
    item.lease_owner = coordinator
    item.lease_expires_at = effective_now + timedelta(seconds=lease_seconds)
    item.attempts += 1
    return item


def start_work_item(item: WorkItem, coordinator_id: str, *, now: datetime | None = None) -> WorkItem:
    """Start a leased work item only when its coordinator lease remains valid."""
    if item.state is not WorkState.LEASED:
        raise InvalidWorkTransition(f"cannot start work in state {item.state}")
    _require_owner(item, coordinator_id, _utc_now(now))
    item.state = WorkState.RUNNING
    return item


def complete_work_item(item: WorkItem, coordinator_id: str, *, now: datetime | None = None) -> WorkItem:
    """Complete running work and clear its lease ownership."""
    if item.state is not WorkState.RUNNING:
        raise InvalidWorkTransition(f"cannot complete work in state {item.state}")
    _require_owner(item, coordinator_id, _utc_now(now))
    item.state = WorkState.SUCCEEDED
    item.lease_owner = None
    item.lease_expires_at = None
    return item


def retry_work_item(item: WorkItem, coordinator_id: str, *, now: datetime | None = None) -> WorkItem:
    """Return running work to retry wait after a recoverable failure."""
    if item.state is not WorkState.RUNNING:
        raise InvalidWorkTransition(f"cannot retry work in state {item.state}")
    _require_owner(item, coordinator_id, _utc_now(now))
    item.state = WorkState.RETRY_WAIT
    item.lease_owner = None
    item.lease_expires_at = None
    return item


def dead_letter_work_item(item: WorkItem, coordinator_id: str, *, now: datetime | None = None) -> WorkItem:
    """Move running work to terminal dead-letter state after exhausted retries."""
    if item.state is not WorkState.RUNNING:
        raise InvalidWorkTransition(f"cannot dead-letter work in state {item.state}")
    _require_owner(item, coordinator_id, _utc_now(now))
    item.state = WorkState.DEAD_LETTER
    item.lease_owner = None
    item.lease_expires_at = None
    return item


def cancel_work_item(item: WorkItem, coordinator_id: str, *, now: datetime | None = None) -> WorkItem:
    """Cancel queued, leased, or running work under coordinator ownership."""
    effective_now = _utc_now(now)
    _require_coordinator(coordinator_id)
    if item.state is WorkState.QUEUED:
        item.state = WorkState.CANCELLED
    elif item.state in {WorkState.LEASED, WorkState.RUNNING}:
        _require_owner(item, coordinator_id, effective_now)
        item.state = WorkState.CANCELLED
    else:
        raise InvalidWorkTransition(f"cannot cancel work in state {item.state}")
    item.lease_owner = None
    item.lease_expires_at = None
    return item


def recover_expired_lease(item: WorkItem, *, now: datetime | None = None) -> WorkItem:
    """Return an expired leased or running item to retry wait for another coordinator."""
    effective_now = _utc_now(now)
    if item.state not in {WorkState.LEASED, WorkState.RUNNING}:
        raise InvalidWorkTransition(f"cannot recover work in state {item.state}")
    if item.lease_expires_at is None or item.lease_expires_at > effective_now:
        raise InvalidWorkTransition("work-item lease has not expired")
    item.state = WorkState.RETRY_WAIT
    item.lease_owner = None
    item.lease_expires_at = None
    return item
