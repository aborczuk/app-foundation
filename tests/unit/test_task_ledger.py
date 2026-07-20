"""Unit tests for scripts/task_ledger.py registration and start gating."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

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


def _write_tasks_file(path: Path, *, task_lines: list[str] | None = None) -> None:
    """Write a minimal tasks file with optional custom task lines."""
    path.write_text(
        "\n".join(
            task_lines
            or [
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
    verification_method: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "timestamp_utc": timestamp_utc,
        "feature_id": "023",
        "task_id": task_id,
        "attempt": attempt,
        "event": event,
        "actor": actor,
    }
    if verification_method is not None:
        payload["verification_method"] = verification_method
    return payload


def test_register_tasks_appends_missing_tasks_and_returns_next_registered_task(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / ".speckit" / "task-ledger.jsonl"
    tasks_file = tmp_path / "specs" / "023-deterministic-phase-orchestration" / "tasks.md"
    tasks_file.parent.mkdir(parents=True)
    _write_tasks_file(tasks_file)

    summary = task_ledger.register_tasks(ledger_path, tasks_file, "023", actor="codex")

    assert summary["newly_registered_task_ids"] == ["T001", "T002"]


def test_explicit_task_start_gate_returns_non_mutating_summary(tmp_path: Path) -> None:
    """Explicit task gates should report eligibility without appending start events."""
    ledger_path = tmp_path / ".speckit" / "task-ledger.jsonl"
    tasks_file = tmp_path / "specs" / "023-deterministic-phase-orchestration" / "tasks.md"
    tasks_file.parent.mkdir(parents=True)
    _write_tasks_file(
        tasks_file,
        task_lines=[
            "## implement",
            "- [ ] T001 first task",
            "- [ ] T002 [P] second task",
        ],
    )

    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        "\n".join(
            [
                json.dumps(_task_event("task_registered"), sort_keys=True),
                json.dumps(_task_event("task_registered", task_id="T002"), sort_keys=True),
                json.dumps(_task_event("task_started"), sort_keys=True),
                json.dumps(
                    _task_event("human_action_verified", verification_method="manual-review"),
                    sort_keys=True,
                ),
                json.dumps(_task_event("task_closed"), sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = task_ledger.explicit_task_start_gate(
        ledger_path,
        tasks_file,
        "023",
        "T002",
        actor="agent-b",
    )

    assert summary["task_id"] == "T002"
    assert summary["parallel"] is True
    assert summary["blocking_reason"] is None
    assert summary["task_started"] is False
    assert len(task_ledger.read_events(ledger_path)) == 5


def test_parse_task_definitions_preserves_breakdown_suffix_ids(tmp_path: Path) -> None:
    """Task registration must retain the mandated a/b/c breakdown task ids."""
    tasks_file = tmp_path / "tasks.md"
    _write_tasks_file(
        tasks_file,
        task_lines=[
            "## implement",
            "- [ ] T009a first split task",
            "- [ ] T009b second split task",
            "- [ ] T010 next task",
        ],
    )

    assert task_ledger.ordered_tasks_from_markdown(tasks_file) == ["T009a", "T009b", "T010"]


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


def test_cmd_validate_counts_registered_tasks_as_open(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The validator summary should count registered-not-closed tasks as open work."""
    ledger_path = tmp_path / ".speckit" / "task-ledger.jsonl"
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        "\n".join(
            [
                json.dumps(_task_event("task_registered"), sort_keys=True),
                json.dumps(_task_event("task_registered", task_id="T002"), sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    task_ledger.cmd_validate(SimpleNamespace(file=str(ledger_path)))

    output = capsys.readouterr().out
    assert "feature 023: closed=0 open=2 active=none" in output


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


def test_assert_can_start_task_allows_parallel_sibling_when_prior_serial_work_is_closed(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / ".speckit" / "task-ledger.jsonl"
    tasks_file = tmp_path / "specs" / "023-deterministic-phase-orchestration" / "tasks.md"
    tasks_file.parent.mkdir(parents=True)
    _write_tasks_file(
        tasks_file,
        task_lines=[
            "## implement",
            "- [ ] T001 setup task",
            "- [ ] T002 [P] parallel task one",
            "- [ ] T003 [P] parallel task two",
        ],
    )

    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        "\n".join(
            [
                json.dumps(_task_event("task_registered"), sort_keys=True),
                json.dumps(_task_event("task_registered", task_id="T002"), sort_keys=True),
                json.dumps(_task_event("task_registered", task_id="T003"), sort_keys=True),
                json.dumps(_task_event("task_started"), sort_keys=True),
                json.dumps(
                    _task_event("human_action_verified", verification_method="manual-review"),
                    sort_keys=True,
                ),
                json.dumps(_task_event("task_closed"), sort_keys=True),
                json.dumps(_task_event("task_started", task_id="T002", actor="agent-a"), sort_keys=True),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = task_ledger.assert_can_start_task(
        ledger_path,
        tasks_file,
        "023",
        "T003",
        actor="agent-b",
    )

    assert summary["task_id"] == "T003"
    assert summary["parallel"] is True
