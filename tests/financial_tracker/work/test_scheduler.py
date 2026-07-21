"""Contract coverage for scheduled discovery registration and feature flags."""

from datetime import datetime, timedelta, timezone

import pytest

START = datetime(2025, 5, 1, tzinfo=timezone.utc)


def test_registration_emits_owned_triggers_at_the_configured_cadence() -> None:
    """A registered discovery emits one bounded trigger per elapsed cadence."""
    from financial_tracker.work.scheduler import DiscoveryScheduler

    scheduler = DiscoveryScheduler(enabled=True)
    scheduler.register(
        "sec-discovery",
        cadence=timedelta(hours=1),
        trigger_owner="sec-worker",
        start_at=START,
    )

    assert scheduler.due(START + timedelta(minutes=59)) == ()
    triggers = scheduler.due(START + timedelta(hours=1))

    assert len(triggers) == 1
    assert triggers[0].schedule_id == "sec-discovery"
    assert triggers[0].trigger_owner == "sec-worker"
    assert triggers[0].scheduled_for == START + timedelta(hours=1)
    assert triggers[0].next_run_at == START + timedelta(hours=2)
    assert scheduler.due(START + timedelta(hours=1, minutes=30)) == ()


def test_environment_flag_defaults_to_disabled_and_blocks_triggers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing or false SEC schedule flags leave registrations inert."""
    from financial_tracker.work.scheduler import DiscoveryScheduler

    monkeypatch.delenv("SEC_SCHEDULE_ENABLED", raising=False)
    scheduler = DiscoveryScheduler.from_environment()
    scheduler.register(
        "sec-discovery",
        cadence=timedelta(hours=1),
        trigger_owner="sec-worker",
        start_at=START,
    )

    assert scheduler.enabled is False
    assert scheduler.due(START + timedelta(days=1)) == ()


def test_true_environment_flag_enables_and_runtime_disable_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """The explicit enable flag permits triggers while runtime disablement suppresses them."""
    from financial_tracker.work.scheduler import DiscoveryScheduler

    monkeypatch.setenv("SEC_SCHEDULE_ENABLED", "true")
    scheduler = DiscoveryScheduler.from_environment()
    scheduler.register(
        "sec-discovery",
        cadence=timedelta(hours=1),
        trigger_owner="sec-worker",
        start_at=START,
    )

    assert scheduler.enabled is True
    assert len(scheduler.due(START + timedelta(hours=1))) == 1
    scheduler.set_enabled(False)
    assert scheduler.due(START + timedelta(hours=2)) == ()
    scheduler.set_enabled(True)
    assert len(scheduler.due(START + timedelta(hours=2))) == 1


def test_offset_inputs_normalize_to_utc_and_long_gaps_emit_one_trigger() -> None:
    """Offset timestamps are normalized and stale schedules do not burst catch-up work."""
    from financial_tracker.work.scheduler import DiscoveryScheduler

    scheduler = DiscoveryScheduler(enabled=True)
    local_anchor = datetime(2025, 4, 30, 19, tzinfo=timezone(timedelta(hours=-5)))
    schedule = scheduler.register(
        "sec-discovery",
        cadence=timedelta(hours=1),
        trigger_owner="sec-worker",
        start_at=local_anchor,
    )

    assert schedule.next_run_at == START + timedelta(hours=1)
    assert schedule.next_run_at.tzinfo == timezone.utc
    triggers = scheduler.due(START + timedelta(days=1))

    assert len(triggers) == 1
    assert triggers[0].next_run_at == START + timedelta(days=1, hours=1)
    assert scheduler.due(START + timedelta(days=1)) == ()


def test_invalid_registration_and_duplicates_are_rejected() -> None:
    """Invalid cadence, ownership, and duplicate IDs cannot create schedules."""
    from financial_tracker.work.scheduler import DiscoveryScheduler

    scheduler = DiscoveryScheduler(enabled=True)

    with pytest.raises(ValueError, match="cadence"):
        scheduler.register("sec-discovery", cadence=timedelta(0), trigger_owner="sec-worker", start_at=START)
    with pytest.raises(ValueError, match="trigger_owner"):
        scheduler.register("sec-discovery", cadence=timedelta(hours=1), trigger_owner=" ", start_at=START)

    scheduler.register(
        "sec-discovery",
        cadence=timedelta(hours=1),
        trigger_owner="sec-worker",
        start_at=START,
    )
    with pytest.raises(ValueError, match="already registered"):
        scheduler.register(
            "sec-discovery",
            cadence=timedelta(hours=1),
            trigger_owner="sec-worker",
            start_at=START,
        )
