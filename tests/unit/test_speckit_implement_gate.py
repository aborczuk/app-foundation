"""Unit tests for scripts/speckit_implement_gate.py."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


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


speckit_implement_gate = _load_script_module(
    "speckit_implement_gate", "speckit_implement_gate.py"
)


def _preflight_args(feature_dir: Path, tasks_file: Path) -> argparse.Namespace:
    return argparse.Namespace(
        feature_dir=str(feature_dir),
        task_id="T048",
        tasks_file=str(tasks_file),
        hud_path=None,
        json=True,
    )


def test_task_preflight_returns_feature_branch_stale_when_task_exists_on_main(
    tmp_path: Path, monkeypatch
) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [X] T047 previous task\n", encoding="utf-8")
    monkeypatch.setattr(speckit_implement_gate, "_task_exists_on_main", lambda *_: True)

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file)
    )
    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["reasons"] == ["feature_branch_stale"]
    assert payload["task_present_in_tasks_file"] is False
    assert payload["task_present_in_main"] is True


def test_task_preflight_returns_task_not_found_when_task_missing_everywhere(
    tmp_path: Path, monkeypatch
) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [X] T047 previous task\n", encoding="utf-8")
    monkeypatch.setattr(speckit_implement_gate, "_task_exists_on_main", lambda *_: False)

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file)
    )
    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["reasons"] == ["task_not_found_in_tasks_md"]
    assert payload["task_present_in_tasks_file"] is False
    assert payload["task_present_in_main"] is False


def test_task_preflight_passes_when_task_exists_locally(tmp_path: Path) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [ ] T048 new task\n", encoding="utf-8")
    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file)
    )
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["reasons"] == []
    assert payload["task_present_in_tasks_file"] is True
    assert payload["task_present_in_main"] is None


def test_task_preflight_reports_tasks_file_without_hud_path(tmp_path: Path) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [ ] T048 new task\n", encoding="utf-8")

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file)
    )
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["tasks_file"] == str(tasks_file.resolve())


def test_task_gate_emits_implementation_completed_once(tmp_path: Path, monkeypatch) -> None:
    feature_dir = tmp_path / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)

    feature_state = speckit_implement_gate.task_ledger.FeatureState()
    feature_state.tasks["T046"] = speckit_implement_gate.task_ledger.TaskState(
        registered=True,
        started=True,
        closed=True,
    )

    state = {"implementation_completed_emitted": False}
    calls: list[tuple[str, ...]] = []

    def fake_run(cmd, capture_output=False, text=False):  # noqa: ANN001
        calls.append(tuple(str(part) for part in cmd))
        command = tuple(str(part) for part in cmd)
        if any(part.endswith("pipeline_ledger.py") for part in command) and "assert-phase-complete" in command:
            if state["implementation_completed_emitted"]:
                stdout = "Task gate PASSED: implementation_completed found for feature 023 (recorded at 2026-04-23T00:00:00Z).\n"
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
            stderr = "Task gate FAILED: no 'implementation_completed' event found for feature 023 in .speckit/pipeline-ledger.jsonl.\n"
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=stderr)
        if any(part.endswith("pipeline_ledger.py") for part in command) and "append" in command:
            state["implementation_completed_emitted"] = True
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected subprocess invocation: {command}")

    monkeypatch.setattr(speckit_implement_gate.task_ledger, "read_events", lambda _path: [])
    monkeypatch.setattr(
        speckit_implement_gate.task_ledger,
        "validate_sequence",
        lambda _events: ([], {"023": feature_state}),
    )
    monkeypatch.setattr(speckit_implement_gate.subprocess, "run", fake_run)

    args = argparse.Namespace(
        feature_dir=str(feature_dir),
        json=True,
    )

    exit_code, payload = speckit_implement_gate._phase_gate(args)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["mode"] == "task_gate"
    assert payload["implementation_completed_state"] == "emitted"
    assert payload["open_task_ids"] == []
    assert payload["closed_task_ids"] == ["T046"]

    second_exit_code, second_payload = speckit_implement_gate._phase_gate(args)
    assert second_exit_code == 0
    assert second_payload["ok"] is True
    assert second_payload["implementation_completed_state"] == "already_recorded"
    assert sum(1 for command in calls if "append" in command and any(part.endswith("pipeline_ledger.py") for part in command)) == 1


def test_task_gate_points_to_open_task(tmp_path: Path, monkeypatch) -> None:
    feature_dir = tmp_path / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)

    feature_state = speckit_implement_gate.task_ledger.FeatureState()
    feature_state.tasks["T046"] = speckit_implement_gate.task_ledger.TaskState(
        registered=True,
        started=True,
        closed=False,
        owner_actor="codex",
    )

    monkeypatch.setattr(
        speckit_implement_gate.task_ledger,
        "read_events",
        lambda _path: [],
    )
    monkeypatch.setattr(
        speckit_implement_gate.task_ledger,
        "validate_sequence",
        lambda _events: ([], {"023": feature_state}),
    )
    monkeypatch.setattr(
        speckit_implement_gate.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected subprocess invocation")),
    )

    args = argparse.Namespace(
        feature_dir=str(feature_dir),
        json=True,
    )

    exit_code, payload = speckit_implement_gate._phase_gate(args)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["mode"] == "task_gate"
    assert payload["reasons"] == []
    assert payload["implementation_completed_state"] == "continue_open_tasks"
    assert payload["open_task_ids"] == ["T046"]
    assert payload["continuation_task_id"] == "T046"


def test_task_gate_filters_stale_ledger_tasks_to_current_tasks_file(
    tmp_path: Path, monkeypatch
) -> None:
    feature_dir = tmp_path / "specs" / "029-make-tetris"
    feature_dir.mkdir(parents=True)
    (feature_dir / "tasks.md").write_text(
        "\n".join(
            [
                "# Tasks",
                "",
                "## Phase 1",
                "",
                "- [ ] T001 Current task one",
                "- [ ] T002 Current task two",
            ]
        ),
        encoding="utf-8",
    )

    feature_state = speckit_implement_gate.task_ledger.FeatureState()
    feature_state.tasks["T000"] = speckit_implement_gate.task_ledger.TaskState(
        registered=True,
        started=True,
        closed=False,
        owner_actor="codex",
    )
    feature_state.tasks["T001"] = speckit_implement_gate.task_ledger.TaskState(
        registered=True,
        started=True,
        closed=True,
        owner_actor="codex",
    )
    feature_state.tasks["T002"] = speckit_implement_gate.task_ledger.TaskState(
        registered=True,
        started=False,
        closed=False,
        owner_actor="codex",
    )

    monkeypatch.setattr(
        speckit_implement_gate.task_ledger,
        "read_events",
        lambda _path: [],
    )
    monkeypatch.setattr(
        speckit_implement_gate.task_ledger,
        "validate_sequence",
        lambda _events: ([], {"029": feature_state}),
    )
    monkeypatch.setattr(
        speckit_implement_gate.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected subprocess invocation")),
    )

    args = argparse.Namespace(
        feature_dir=str(feature_dir),
        json=True,
    )

    exit_code, payload = speckit_implement_gate._phase_gate(args)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["closed_task_ids"] == ["T001"]
    assert payload["open_task_ids"] == ["T002"]
    assert payload["continuation_task_id"] == "T002"
