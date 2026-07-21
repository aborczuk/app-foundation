"""PostgreSQL-backed worker leasing and coordinator-owned state transitions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from .state import (
    CoordinatorOwnershipError,
    InvalidWorkTransition,
    WorkItem,
    WorkState,
    complete_work_item,
    lease_work_item,
    start_work_item,
)


class PostgresWorkCoordinator:
    """Claim and transition durable work items under one coordinator identity."""

    def __init__(self, connection: Any, coordinator_id: str) -> None:
        """Bind a caller-owned PostgreSQL connection and normalized coordinator ID."""
        normalized = coordinator_id.strip()
        if not normalized:
            raise CoordinatorOwnershipError("coordinator_id must be non-empty")
        self._connection = connection
        self._coordinator_id = normalized

    def lease_next(
        self,
        tenant_id: str,
        *,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> WorkItem | None:
        """Atomically lease the oldest available item for this coordinator."""
        normalized_tenant = _require_tenant(tenant_id)
        effective_now = _utc_now(now)
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, tenant_id, idempotency_key, kind, state, lease_owner, "
                    "lease_expires_at, attempts FROM financial_tracker.work_items "
                    "WHERE tenant_id = %s AND state IN (%s, %s) "
                    "ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1",
                    (normalized_tenant, WorkState.QUEUED.value, WorkState.RETRY_WAIT.value),
                )
                row = cursor.fetchone()
                if row is None:
                    self._connection.commit()
                    return None
                item = lease_work_item(
                    _row_to_item(row),
                    self._coordinator_id,
                    now=effective_now,
                    lease_seconds=lease_seconds,
                )
                _persist_item(cursor, item)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return item

    def start(self, work_item_id: UUID, *, now: datetime | None = None) -> WorkItem:
        """Move one leased item to running only under its current owner."""
        return self._transition(work_item_id, "start", now=now)

    def complete(self, work_item_id: UUID, *, now: datetime | None = None) -> WorkItem:
        """Complete one running item and clear its coordinator lease."""
        return self._transition(work_item_id, "complete", now=now)

    def renew(
        self,
        work_item_id: UUID,
        *,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> WorkItem:
        """Extend an unexpired leased or running item owned by this coordinator."""
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        effective_now = _utc_now(now)
        try:
            with self._connection.cursor() as cursor:
                item = _load_item(cursor, work_item_id)
                _require_live_owner(item, self._coordinator_id, effective_now)
                if item.state not in {WorkState.LEASED, WorkState.RUNNING}:
                    raise InvalidWorkTransition(f"cannot renew work in state {item.state}")
                item.lease_expires_at = effective_now + timedelta(seconds=lease_seconds)
                _persist_item(cursor, item)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return item

    def _transition(
        self,
        work_item_id: UUID,
        action: str,
        *,
        now: datetime | None,
    ) -> WorkItem:
        """Apply one ownership-checked pure state transition in PostgreSQL."""
        effective_now = _utc_now(now)
        try:
            with self._connection.cursor() as cursor:
                item = _load_item(cursor, work_item_id)
                if action == "start":
                    item = start_work_item(item, self._coordinator_id, now=effective_now)
                elif action == "complete":
                    item = complete_work_item(item, self._coordinator_id, now=effective_now)
                else:
                    raise ValueError(f"unsupported work transition: {action}")
                _persist_item(cursor, item)
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return item


def _require_tenant(tenant_id: str) -> str:
    """Normalize and validate the tenant scope used by a lease query."""
    normalized = tenant_id.strip()
    if not normalized:
        raise ValueError("tenant_id must be non-empty")
    return normalized


def _utc_now(value: datetime | None) -> datetime:
    """Return an aware UTC timestamp for deterministic lease operations."""
    resolved = value or datetime.now(timezone.utc)
    if resolved.tzinfo is None:
        raise ValueError("transition timestamps must be timezone-aware")
    return resolved.astimezone(timezone.utc)


def _load_item(cursor: Any, work_item_id: UUID) -> WorkItem:
    """Load one work item under row lock for an ownership transition."""
    cursor.execute(
        "SELECT id, tenant_id, idempotency_key, kind, state, lease_owner, "
        "lease_expires_at, attempts FROM financial_tracker.work_items "
        "WHERE id = %s FOR UPDATE",
        (work_item_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise InvalidWorkTransition("work item does not exist")
    return _row_to_item(row)


def _row_to_item(row: tuple[Any, ...]) -> WorkItem:
    """Convert one PostgreSQL work-item row to the shared state projection."""
    return WorkItem(
        id=_as_uuid(row[0]),
        tenant_id=str(row[1]),
        idempotency_key=str(row[2]),
        kind=str(row[3]),
        state=WorkState(str(row[4])),
        lease_owner=str(row[5]) if row[5] is not None else None,
        lease_expires_at=row[6],
        attempts=int(row[7]),
    )


def _persist_item(cursor: Any, item: WorkItem) -> None:
    """Persist the complete coordinator-owned work projection."""
    cursor.execute(
        "UPDATE financial_tracker.work_items SET state = %s, lease_owner = %s, "
        "lease_expires_at = %s, attempts = %s WHERE id = %s",
        (
            item.state.value,
            item.lease_owner,
            item.lease_expires_at,
            item.attempts,
            item.id,
        ),
    )


def _require_live_owner(item: WorkItem, coordinator_id: str, now: datetime) -> None:
    """Reject transitions from another or expired coordinator lease."""
    if (
        item.lease_owner != coordinator_id
        or item.lease_expires_at is None
        or item.lease_expires_at <= now
    ):
        raise CoordinatorOwnershipError("coordinator does not hold a valid work-item lease")


def _as_uuid(value: Any) -> UUID:
    """Normalize a PostgreSQL UUID value for the work-item projection."""
    return value if isinstance(value, UUID) else UUID(str(value))
