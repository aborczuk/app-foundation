"""SQLite-backed dedupe and active-run guard state for control-plane dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

import aiosqlite

ActiveRunState = Literal["running", "released", "stale"]
LockDecision = Literal["dispatch", "skip_duplicate", "stale_event", "reject_active_run"]


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LockAcquisitionResult:
    """Result from the atomic dedupe + lock acquisition transaction."""

    decision: LockDecision
    reason_code: str
    task_id: str
    event_id: str
    run_id: str | None = None
    conflicting_run_id: str | None = None


@dataclass(frozen=True)
class ActiveTaskRun:
    """Persisted active-run record used for one-workflow-at-a-time enforcement."""

    task_id: str
    run_id: str
    event_id: str
    state: ActiveRunState
    acquired_at_utc: str
    released_at_utc: str | None


@dataclass(frozen=True)
class ProcessedEvent:
    """Persisted dedupe record for already-processed webhook events."""

    event_id: str
    task_id: str
    decision: str
    processed_at_utc: str


@dataclass(frozen=True)
class PausedTaskRun:
    """Persisted paused-run record used for HITL pause/resume flow control."""

    task_id: str
    run_id: str
    workflow_type: str
    context_ref: str
    execution_policy: str
    requested_at_utc: str
    timeout_at_utc: str | None
    prompt: str


class StateStore:
    """State layer with explicit transaction boundaries for dedupe + lock safety."""

    def __init__(self, db_path: str | Path) -> None:
        """Bind the SQLite state database path used by this store."""
        self._db_path = Path(db_path)

    async def initialize(self) -> None:
        """Create parent directory and migrate required state tables."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await self._connect()
        try:
            await self._run_migrations(conn)
        finally:
            await conn.close()

    async def record_event_and_acquire_lock(
        self,
        *,
        task_id: str,
        event_id: str,
        run_id: str,
        processed_at_utc: str | None = None,
    ) -> LockAcquisitionResult:
        """Atomically dedupe incoming event and acquire one-active-run lock."""
        timestamp = processed_at_utc or utc_now_iso()
        conn = await self._connect()
        try:
            await conn.execute("BEGIN IMMEDIATE")

            try:
                await conn.execute(
                    """
                    INSERT INTO processed_events (event_id, task_id, decision, processed_at_utc)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event_id, task_id, "pending", timestamp),
                )
            except aiosqlite.IntegrityError:
                await conn.execute("ROLLBACK")
                return LockAcquisitionResult(
                    decision="skip_duplicate",
                    reason_code="duplicate_event",
                    task_id=task_id,
                    event_id=event_id,
                )

            await self._after_dedupe_insert_hook()

            if await self._is_stale_event(
                conn=conn,
                task_id=task_id,
                event_id=event_id,
                event_timestamp=timestamp,
            ):
                await conn.execute(
                    "UPDATE processed_events SET decision = ? WHERE event_id = ?",
                    ("stale_event", event_id),
                )
                await conn.execute("COMMIT")
                return LockAcquisitionResult(
                    decision="stale_event",
                    reason_code="stale_event",
                    task_id=task_id,
                    event_id=event_id,
                )

            async with conn.execute(
                """
                SELECT run_id
                FROM active_task_runs
                WHERE task_id = ? AND state = 'running'
                """,
                (task_id,),
            ) as cur:
                row = await cur.fetchone()

            if row is not None:
                conflict_run_id = str(row["run_id"])
                await conn.execute(
                    "UPDATE processed_events SET decision = ? WHERE event_id = ?",
                    ("reject_active_run", event_id),
                )
                await conn.execute("COMMIT")
                return LockAcquisitionResult(
                    decision="reject_active_run",
                    reason_code="active_run_exists",
                    task_id=task_id,
                    event_id=event_id,
                    conflicting_run_id=conflict_run_id,
                )

            await conn.execute(
                """
                INSERT INTO active_task_runs (
                    task_id,
                    run_id,
                    event_id,
                    state,
                    acquired_at_utc,
                    released_at_utc
                )
                VALUES (?, ?, ?, 'running', ?, NULL)
                ON CONFLICT(task_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    event_id = excluded.event_id,
                    state = excluded.state,
                    acquired_at_utc = excluded.acquired_at_utc,
                    released_at_utc = NULL
                """,
                (task_id, run_id, event_id, timestamp),
            )
            await conn.execute(
                "UPDATE processed_events SET decision = ? WHERE event_id = ?",
                ("dispatch", event_id),
            )
            await conn.execute("COMMIT")

            return LockAcquisitionResult(
                decision="dispatch",
                reason_code="lock_acquired",
                task_id=task_id,
                event_id=event_id,
                run_id=run_id,
            )
        except Exception:
            await self._rollback_quietly(conn)
            raise
        finally:
            await conn.close()

    async def update_processed_event_decision(self, *, event_id: str, decision: str) -> None:
        """Update persisted event decision with a terminal outcome."""
        conn = await self._connect()
        try:
            await conn.execute(
                "UPDATE processed_events SET decision = ? WHERE event_id = ?",
                (decision, event_id),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def record_processed_event(
        self,
        *,
        task_id: str,
        event_id: str,
        decision: str,
        processed_at_utc: str | None = None,
    ) -> bool:
        """Insert a processed event row for non-dispatch paths; return False on duplicate."""
        timestamp = processed_at_utc or utc_now_iso()
        conn = await self._connect()
        try:
            try:
                await conn.execute(
                    """
                    INSERT INTO processed_events (event_id, task_id, decision, processed_at_utc)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event_id, task_id, decision, timestamp),
                )
            except aiosqlite.IntegrityError:
                return False
            await conn.commit()
            return True
        finally:
            await conn.close()

    async def set_active_run_id(
        self,
        *,
        task_id: str,
        current_run_id: str,
        new_run_id: str,
    ) -> bool:
        """Update a running lock row from provisional run id to resolved run id."""
        conn = await self._connect()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            async with conn.execute(
                "SELECT run_id, state FROM active_task_runs WHERE task_id = ?",
                (task_id,),
            ) as cur:
                row = await cur.fetchone()

            if (
                row is None
                or str(row["run_id"]) != current_run_id
                or str(row["state"]) != "running"
            ):
                await conn.execute("ROLLBACK")
                return False

            await conn.execute(
                "UPDATE active_task_runs SET run_id = ? WHERE task_id = ?",
                (new_run_id, task_id),
            )
            await conn.execute("COMMIT")
            return True
        except Exception:
            await self._rollback_quietly(conn)
            raise
        finally:
            await conn.close()

    async def persist_terminal_decision(
        self,
        *,
        task_id: str,
        event_id: str,
        decision: str,
        active_run_id: str | None = None,
        release_lock: bool = False,
        final_state: Literal["released", "stale"] = "released",
        released_at_utc: str | None = None,
    ) -> bool:
        """Persist terminal decision and optionally release lock in one transaction."""
        timestamp = released_at_utc or utc_now_iso()
        conn = await self._connect()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            await conn.execute(
                "UPDATE processed_events SET decision = ? WHERE event_id = ?",
                (decision, event_id),
            )

            if not release_lock:
                await conn.execute("COMMIT")
                return True

            if active_run_id is None:
                await conn.execute("ROLLBACK")
                return False

            async with conn.execute(
                "SELECT run_id, state FROM active_task_runs WHERE task_id = ?",
                (task_id,),
            ) as cur:
                row = await cur.fetchone()

            if (
                row is None
                or str(row["run_id"]) != active_run_id
                or str(row["state"]) != "running"
            ):
                await conn.execute("ROLLBACK")
                return False

            await conn.execute(
                """
                UPDATE active_task_runs
                SET state = ?, released_at_utc = ?
                WHERE task_id = ?
                """,
                (final_state, timestamp, task_id),
            )
            await conn.execute("COMMIT")
            return True
        except Exception:
            await self._rollback_quietly(conn)
            raise
        finally:
            await conn.close()

    async def release_active_run(
        self,
        *,
        task_id: str,
        run_id: str,
        final_state: Literal["released", "stale"] = "released",
        released_at_utc: str | None = None,
    ) -> bool:
        """Release a running lock only when the run id still matches."""
        timestamp = released_at_utc or utc_now_iso()
        conn = await self._connect()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            async with conn.execute(
                "SELECT run_id, state FROM active_task_runs WHERE task_id = ?",
                (task_id,),
            ) as cur:
                row = await cur.fetchone()

            if row is None or str(row["run_id"]) != run_id or str(row["state"]) != "running":
                await conn.execute("ROLLBACK")
                return False

            await conn.execute(
                """
                UPDATE active_task_runs
                SET state = ?, released_at_utc = ?
                WHERE task_id = ?
                """,
                (final_state, timestamp, task_id),
            )
            await conn.execute("COMMIT")
            return True
        except Exception:
            await self._rollback_quietly(conn)
            raise
        finally:
            await conn.close()

    async def get_active_run(self, *, task_id: str) -> ActiveTaskRun | None:
        """Return current active run row for task if one exists."""
        conn = await self._connect()
        try:
            async with conn.execute(
                """
                SELECT task_id, run_id, event_id, state, acquired_at_utc, released_at_utc
                FROM active_task_runs
                WHERE task_id = ? AND state = 'running'
                """,
                (task_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            return self._row_to_active_run(row)
        finally:
            await conn.close()

    async def list_running_runs(self) -> list[ActiveTaskRun]:
        """Return all currently running task locks for reconciliation checks."""
        conn = await self._connect()
        try:
            async with conn.execute(
                """
                SELECT task_id, run_id, event_id, state, acquired_at_utc, released_at_utc
                FROM active_task_runs
                WHERE state = 'running'
                ORDER BY acquired_at_utc ASC
                """
            ) as cur:
                rows = await cur.fetchall()
            return [self._row_to_active_run(row) for row in rows]
        finally:
            await conn.close()

    async def get_processed_event(self, *, event_id: str) -> ProcessedEvent | None:
        """Return processed event row for dedupe/debug use."""
        conn = await self._connect()
        try:
            async with conn.execute(
                """
                SELECT event_id, task_id, decision, processed_at_utc
                FROM processed_events
                WHERE event_id = ?
                """,
                (event_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            return ProcessedEvent(
                event_id=str(row["event_id"]),
                task_id=str(row["task_id"]),
                decision=str(row["decision"]),
                processed_at_utc=str(row["processed_at_utc"]),
            )
        finally:
            await conn.close()

    async def upsert_paused_run(
        self,
        *,
        task_id: str,
        run_id: str,
        workflow_type: str,
        context_ref: str,
        execution_policy: str,
        requested_at_utc: str | None = None,
        timeout_at_utc: str | None = None,
        prompt: str,
    ) -> None:
        """Persist or replace paused-run metadata for one task."""
        timestamp = requested_at_utc or utc_now_iso()
        conn = await self._connect()
        try:
            await conn.execute(
                """
                INSERT INTO paused_task_runs (
                    task_id,
                    run_id,
                    workflow_type,
                    context_ref,
                    execution_policy,
                    requested_at_utc,
                    timeout_at_utc,
                    prompt
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    workflow_type = excluded.workflow_type,
                    context_ref = excluded.context_ref,
                    execution_policy = excluded.execution_policy,
                    requested_at_utc = excluded.requested_at_utc,
                    timeout_at_utc = excluded.timeout_at_utc,
                    prompt = excluded.prompt
                """,
                (
                    task_id,
                    run_id,
                    workflow_type,
                    context_ref,
                    execution_policy,
                    timestamp,
                    timeout_at_utc,
                    prompt,
                ),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get_paused_run(self, *, task_id: str) -> PausedTaskRun | None:
        """Return paused-run metadata for task when workflow is awaiting operator input."""
        conn = await self._connect()
        try:
            async with conn.execute(
                """
                SELECT
                    task_id,
                    run_id,
                    workflow_type,
                    context_ref,
                    execution_policy,
                    requested_at_utc,
                    timeout_at_utc,
                    prompt
                FROM paused_task_runs
                WHERE task_id = ?
                """,
                (task_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                return None
            return PausedTaskRun(
                task_id=str(row["task_id"]),
                run_id=str(row["run_id"]),
                workflow_type=str(row["workflow_type"]),
                context_ref=str(row["context_ref"]),
                execution_policy=str(row["execution_policy"]),
                requested_at_utc=str(row["requested_at_utc"]),
                timeout_at_utc=row["timeout_at_utc"],
                prompt=str(row["prompt"]),
            )
        finally:
            await conn.close()

    async def clear_paused_run(self, *, task_id: str, run_id: str | None = None) -> bool:
        """Clear paused-run metadata; optionally require run-id match."""
        conn = await self._connect()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            if run_id is None:
                cursor = await conn.execute(
                    "DELETE FROM paused_task_runs WHERE task_id = ?",
                    (task_id,),
                )
            else:
                cursor = await conn.execute(
                    "DELETE FROM paused_task_runs WHERE task_id = ? AND run_id = ?",
                    (task_id, run_id),
                )
            deleted = cursor.rowcount > 0
            await conn.execute("COMMIT")
            return deleted
        except Exception:
            await self._rollback_quietly(conn)
            raise
        finally:
            await conn.close()

    async def _after_dedupe_insert_hook(self) -> None:
        """Test hook used by rollback regression tests to force mid-transaction failures."""
        return

    async def _is_stale_event(
        self,
        *,
        conn: aiosqlite.Connection,
        task_id: str,
        event_id: str,
        event_timestamp: str,
    ) -> bool:
        incoming = self._parse_iso_utc(event_timestamp)
        if incoming is None:
            return False

        async with conn.execute(
            """
            SELECT processed_at_utc
            FROM processed_events
            WHERE task_id = ? AND event_id <> ?
            ORDER BY processed_at_utc DESC
            LIMIT 1
            """,
            (task_id, event_id),
        ) as cur:
            row = await cur.fetchone()

        if row is None:
            return False

        latest = self._parse_iso_utc(str(row["processed_at_utc"]))
        if latest is None:
            return False
        return incoming < latest

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def _run_migrations(self, conn: aiosqlite.Connection) -> None:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id          TEXT PRIMARY KEY,
                task_id           TEXT NOT NULL,
                decision          TEXT NOT NULL,
                processed_at_utc  TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS active_task_runs (
                task_id           TEXT PRIMARY KEY,
                run_id            TEXT NOT NULL,
                event_id          TEXT NOT NULL,
                state             TEXT NOT NULL CHECK (state IN ('running', 'released', 'stale')),
                acquired_at_utc   TEXT NOT NULL,
                released_at_utc   TEXT
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_processed_events_task_id ON processed_events(task_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_active_task_runs_state ON active_task_runs(state)"
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paused_task_runs (
                task_id            TEXT PRIMARY KEY,
                run_id             TEXT NOT NULL,
                workflow_type      TEXT NOT NULL,
                context_ref        TEXT NOT NULL,
                execution_policy   TEXT NOT NULL,
                requested_at_utc   TEXT NOT NULL,
                timeout_at_utc     TEXT,
                prompt             TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_paused_task_runs_run_id ON paused_task_runs(run_id)"
        )
        await conn.commit()

    async def _rollback_quietly(self, conn: aiosqlite.Connection) -> None:
        try:
            await conn.execute("ROLLBACK")
        except Exception:
            return

    @staticmethod
    def _row_to_active_run(row: aiosqlite.Row) -> ActiveTaskRun:
        state_raw = str(row["state"])
        if state_raw not in {"running", "released", "stale"}:
            raise ValueError(f"Invalid active_task_runs.state value: {state_raw!r}")
        return ActiveTaskRun(
            task_id=str(row["task_id"]),
            run_id=str(row["run_id"]),
            event_id=str(row["event_id"]),
            state=cast(ActiveRunState, state_raw),
            acquired_at_utc=str(row["acquired_at_utc"]),
            released_at_utc=row["released_at_utc"],
        )

    @staticmethod
    def _parse_iso_utc(raw_value: str) -> datetime | None:
        value = raw_value.strip()
        if not value:
            return None
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


__all__ = [
    "ActiveRunState",
    "ActiveTaskRun",
    "LockAcquisitionResult",
    "LockDecision",
    "PausedTaskRun",
    "ProcessedEvent",
    "StateStore",
    "utc_now_iso",
]
