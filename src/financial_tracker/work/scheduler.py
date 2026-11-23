"""Scheduled discovery registration and feature-flag enforcement."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

SEC_SCHEDULE_ENABLED = "SEC_SCHEDULE_ENABLED"
_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class DiscoverySchedule:
    """Immutable registration metadata for one scheduled discovery."""

    schedule_id: str
    cadence: timedelta
    trigger_owner: str
    next_run_at: datetime


@dataclass(frozen=True, slots=True)
class DiscoveryTrigger:
    """Bounded trigger payload returned when a registration becomes due."""

    schedule_id: str
    trigger_owner: str
    scheduled_for: datetime
    next_run_at: datetime


class DiscoveryScheduler:
    """Register SEC discovery cadences and emit owner-routed due triggers."""

    def __init__(self, *, enabled: bool | None = None) -> None:
        """Create an empty scheduler with a fail-closed environment default."""
        self._enabled = _environment_enabled() if enabled is None else enabled
        self._registrations: dict[str, DiscoverySchedule] = {}

    @classmethod
    def from_environment(cls) -> DiscoveryScheduler:
        """Build a scheduler from the explicit SEC schedule feature flag."""
        return cls(enabled=_environment_enabled())

    @property
    def enabled(self) -> bool:
        """Return whether due registrations are currently allowed to trigger."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enable or safely disable trigger emission without deleting registrations."""
        self._enabled = enabled

    def register(
        self,
        schedule_id: str,
        *,
        cadence: timedelta,
        trigger_owner: str,
        start_at: datetime | None = None,
    ) -> DiscoverySchedule:
        """Register one unique, positive-cadence, UTC-aware discovery schedule."""
        normalized_id = _required_text(schedule_id, "schedule_id")
        normalized_owner = _required_text(trigger_owner, "trigger_owner")
        if cadence <= timedelta(0):
            raise ValueError("cadence must be positive")
        if normalized_id in self._registrations:
            raise ValueError(f"schedule already registered: {normalized_id}")
        anchor = _aware_datetime(start_at or datetime.now(timezone.utc), "start_at")
        next_run_at = anchor + cadence
        schedule = DiscoverySchedule(normalized_id, cadence, normalized_owner, next_run_at)
        self._registrations[normalized_id] = schedule
        return schedule

    def due(self, now: datetime | None = None) -> tuple[DiscoveryTrigger, ...]:
        """Emit due triggers once per poll and advance each cadence deterministically."""
        if not self._enabled:
            return ()
        current = _aware_datetime(now or datetime.now(timezone.utc), "now")
        triggers: list[DiscoveryTrigger] = []
        for schedule_id in sorted(self._registrations):
            schedule = self._registrations[schedule_id]
            if schedule.next_run_at > current:
                continue
            next_run_at = _next_occurrence(schedule.next_run_at, schedule.cadence, current)
            self._registrations[schedule_id] = replace(schedule, next_run_at=next_run_at)
            triggers.append(
                DiscoveryTrigger(
                    schedule_id=schedule.schedule_id,
                    trigger_owner=schedule.trigger_owner,
                    scheduled_for=schedule.next_run_at,
                    next_run_at=next_run_at,
                )
            )
        return tuple(triggers)


def _environment_enabled() -> bool:
    """Parse the SEC schedule flag while treating missing or invalid values as disabled."""
    return os.getenv(SEC_SCHEDULE_ENABLED, "false").strip().lower() in _ENABLED_VALUES


def _required_text(value: str, field_name: str) -> str:
    """Normalize and validate one required scheduler identifier."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    """Normalize aware timestamps to UTC so cadence comparisons remain unambiguous."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _next_occurrence(scheduled_for: datetime, cadence: timedelta, now: datetime) -> datetime:
    """Advance past all elapsed slots without emitting an unbounded catch-up burst."""
    elapsed_slots = (now - scheduled_for) // cadence
    return scheduled_for + cadence * (elapsed_slots + 1)
