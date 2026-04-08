"""Startup reconciliation for stale/orphaned active-run locks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .state_store import ActiveTaskRun, StateStore


class ClickUpRunStateProbe(Protocol):
    """Source-of-truth probe for deciding whether a task run is still active."""

    async def is_task_run_active(self, *, task_id: str, run_id: str) -> bool:
        """Return True when ClickUp still indicates this run is active."""
        ...


@dataclass(frozen=True)
class ReconciliationResult:
    """Summary of startup reconciliation outcomes."""

    total_running: int
    confirmed_active: tuple[str, ...] = ()
    released_stale: tuple[str, ...] = ()
    probe_failures: tuple[str, ...] = ()
    release_failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ReconciliationCheckpointError(RuntimeError):
    """Raised when pre-dispatch reconciliation still has unresolved drift."""

    def __init__(self, message: str, *, result: ReconciliationResult) -> None:
        """Attach reconciliation details to a checkpoint failure."""
        super().__init__(message)
        self.result = result


class ReconciliationService:
    """Detect and clear stale local running locks against ClickUp source-of-truth."""

    def __init__(
        self,
        *,
        state_store: StateStore,
        run_state_probe: ClickUpRunStateProbe,
    ) -> None:
        """Initialize reconciliation dependencies for lock probing and release."""
        self._state_store = state_store
        self._run_state_probe = run_state_probe

    async def reconcile_stale_active_runs(self) -> ReconciliationResult:
        """Mark orphaned local running locks as stale when ClickUp says they are inactive."""
        running = await self._state_store.list_running_runs()

        confirmed_active: list[str] = []
        released_stale: list[str] = []
        probe_failures: list[str] = []
        release_failures: list[str] = []
        warnings: list[str] = []

        for active_run in running:
            label = _run_label(active_run)
            try:
                is_active = await self._run_state_probe.is_task_run_active(
                    task_id=active_run.task_id,
                    run_id=active_run.run_id,
                )
            except Exception as exc:
                probe_failures.append(label)
                warnings.append(
                    f"Probe failed for {label}; keeping lock to avoid unsafe release ({exc})."
                )
                continue

            if is_active:
                confirmed_active.append(label)
                continue

            released = await self._state_store.release_active_run(
                task_id=active_run.task_id,
                run_id=active_run.run_id,
                final_state="stale",
            )
            if released:
                released_stale.append(label)
            else:
                release_failures.append(label)
                warnings.append(
                    f"Could not release stale lock for {label}; lock changed during reconciliation."
                )

        return ReconciliationResult(
            total_running=len(running),
            confirmed_active=tuple(confirmed_active),
            released_stale=tuple(released_stale),
            probe_failures=tuple(probe_failures),
            release_failures=tuple(release_failures),
            warnings=tuple(warnings),
        )

    async def enforce_pre_dispatch_checkpoint(self) -> ReconciliationResult:
        """Run reconciliation and fail closed when unresolved drift remains."""
        result = await self.reconcile_stale_active_runs()
        if result.probe_failures or result.release_failures:
            unresolved = ", ".join((*result.probe_failures, *result.release_failures))
            raise ReconciliationCheckpointError(
                f"Reconciliation checkpoint failed; unresolved drift: {unresolved}",
                result=result,
            )
        return result


def _run_label(run: ActiveTaskRun) -> str:
    return f"{run.task_id}:{run.run_id}"


__all__ = [
    "ClickUpRunStateProbe",
    "ReconciliationCheckpointError",
    "ReconciliationResult",
    "ReconciliationService",
]
