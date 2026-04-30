"""Unit tests for scripts/task_ledger.py registration and start gating."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_script_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


task_ledger = _load_script_module("task_ledger", "task_ledger.py")


def _write_tasks_file(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "## implement",
                "- [ ] T001 first task",
                "- [ ] T002 second task",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _task_event(
    event: str,
    *,
    task_id: str = "T001",
    attempt: int = 0,
    timestamp_utc: str = "2026-04-29T00:00:00Z",
    actor: str = "codex",
) -> dict[str, object]:
    return {
        "timestamp_utc": timestamp_utc,
        "feature_id": "023",
        "task_id": task_id,
        "attempt": attempt,
        "event": event,
        "actor": actor,
    }


def test_register_tasks_appends_missing_tasks_and_returns_next_registered_task(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / ".speckit" / "task-ledger.jsonl"
    tasks_file = tmp_path / "specs" / "023-deterministic-phase-orchestration" / "tasks.md"
    tasks_file.parent.mkdir(parents=True)
    _write_tasks_file(tasks_file)

    summary = task_ledger.register_tasks(ledger_path, tasks_file, "023", actor="codex")

    assert summary["newly_registered_task_ids"] == ["T001", "T002"]
    assert summary["skipped_task_ids"] == []
    assert summary["next_task_id"] == "T001"

    events = task_ledger.read_events(ledger_path)
    assert [event["event"] for event in events] == ["task_registered", "task_registered"]

    errors, states = task_ledger.validate_sequence(events)
    assert errors == []
    assert states["023"].tasks["T001"].registered is True
    assert states["023"].tasks["T002"].registered is True


def test_next_registered_task_requires_registration() -> None:
    feature_state = task_ledger.FeatureState(
        tasks={
            "T001": task_ledger.TaskState(),
            "T002": task_ledger.TaskState(registered=True),
        }
    )

    assert task_ledger.next_registered_task(feature_state) == ("T002", feature_state.tasks["T002"])
    assert task_ledger.next_registered_task(task_ledger.FeatureState(tasks={"T001": task_ledger.TaskState()})) is None


def test_validate_sequence_allows_task_registered_before_task_started() -> None:
    events = [
        _task_event("task_registered"),
        _task_event("task_started"),
    ]

    errors, states = task_ledger.validate_sequence(events)

    assert errors == []
    assert states["023"].tasks["T001"].registered is True
    assert states["023"].tasks["T001"].started is True


def test_validate_sequence_rejects_task_registered_after_task_started() -> None:
    events = [
        _task_event("task_started"),
        _task_event("task_registered"),
    ]

    errors, _ = task_ledger.validate_sequence(events)

    assert any("cannot register already started task T001" in error for error in errors)


def test_assert_can_start_task_rejects_open_prior_task(tmp_path: Path) -> None:
    ledger_path = tmp_path / ".speckit" / "task-ledger.jsonl"
    tasks_file = tmp_path / "specs" / "023-deterministic-phase-orchestration" / "tasks.md"
    tasks_file.parent.mkdir(parents=True)
    _write_tasks_file(tasks_file)

    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        "\n".join(
            [
                json.dumps(_task_event("task_registered"), sort_keys=True),
                json.dumps(_task_event("task_started"), sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        task_ledger.assert_can_start_task(ledger_path, tasks_file, "023", "T002", actor="codex")
