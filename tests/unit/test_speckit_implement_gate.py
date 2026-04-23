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


def _preflight_args(
    feature_dir: Path, tasks_file: Path, hud_path: Path | None
) -> argparse.Namespace:
    return argparse.Namespace(
        feature_dir=str(feature_dir),
        task_id="T048",
        tasks_file=str(tasks_file),
        hud_path=str(hud_path) if hud_path else None,
        json=True,
    )


def test_task_preflight_returns_feature_branch_stale_when_task_exists_on_main(
    tmp_path: Path, monkeypatch
) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [X] T047 previous task\n", encoding="utf-8")
    hud_path = feature_dir / "huds" / "T048.md"
    hud_path.parent.mkdir(parents=True)
    hud_path.write_text("# HUD T048\n", encoding="utf-8")

    monkeypatch.setattr(speckit_implement_gate, "_task_exists_on_main", lambda *_: True)

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file, hud_path)
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
    hud_path = feature_dir / "huds" / "T048.md"
    hud_path.parent.mkdir(parents=True)
    hud_path.write_text("# HUD T048\n", encoding="utf-8")

    monkeypatch.setattr(speckit_implement_gate, "_task_exists_on_main", lambda *_: False)

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file, hud_path)
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
    hud_path = feature_dir / "huds" / "T048.md"
    hud_path.parent.mkdir(parents=True)
    hud_path.write_text("# HUD T048\n", encoding="utf-8")

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file, hud_path)
    )
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["reasons"] == []
    assert payload["task_present_in_tasks_file"] is True
    assert payload["task_present_in_main"] is None


def test_task_preflight_defaults_hud_to_feature_local_path(tmp_path: Path) -> None:
    feature_dir = tmp_path / "specs" / "019-token-efficiency-docs"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("- [ ] T048 new task\n", encoding="utf-8")
    default_hud_path = feature_dir / "huds" / "T048.md"
    default_hud_path.parent.mkdir(parents=True)
    default_hud_path.write_text("# HUD T048\n", encoding="utf-8")

    exit_code, payload = speckit_implement_gate._task_preflight(
        _preflight_args(feature_dir, tasks_file, None)
    )
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["hud_path"] == str(default_hud_path.resolve())


def test_phase_gate_emits_implementation_completed_once(tmp_path: Path, monkeypatch) -> None:
    feature_dir = tmp_path / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("## implement\n- [X] T046 gate task\n", encoding="utf-8")

    state = {"implementation_completed_emitted": False}
    calls: list[tuple[str, ...]] = []

    def fake_run(cmd, capture_output=False, text=False):  # noqa: ANN001
        calls.append(tuple(str(part) for part in cmd))
        command = tuple(str(part) for part in cmd)
        if any(part.endswith("task_ledger.py") for part in command) and "validate" in command:
            stdout = "Task ledger validation passed (1 events).\n- feature 023: closed=1 open=0 active=none\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        if any(part.endswith("pipeline_ledger.py") for part in command) and "assert-phase-complete" in command:
            if state["implementation_completed_emitted"]:
                stdout = "Phase gate PASSED: implementation_completed found for feature 023 (recorded at 2026-04-23T00:00:00Z).\n"
                return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
            stderr = "Phase gate FAILED: no 'implementation_completed' event found for feature 023 in .speckit/pipeline-ledger.jsonl.\n"
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=stderr)
        if any(part.endswith("pipeline_ledger.py") for part in command) and "append" in command:
            state["implementation_completed_emitted"] = True
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected subprocess invocation: {command}")

    monkeypatch.setattr(speckit_implement_gate.subprocess, "run", fake_run)

    args = argparse.Namespace(
        feature_dir=str(feature_dir),
        phase_name="implement",
        phase_type="polish",
        layer1="pass",
        layer2="pass",
        layer3="na",
        json=True,
    )

    exit_code, payload = speckit_implement_gate._phase_gate(args)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["implementation_completed_state"] == "emitted"

    second_exit_code, second_payload = speckit_implement_gate._phase_gate(args)
    assert second_exit_code == 0
    assert second_payload["ok"] is True
    assert second_payload["implementation_completed_state"] == "already_recorded"
    assert sum(1 for command in calls if "append" in command and any(part.endswith("pipeline_ledger.py") for part in command)) == 1


def test_phase_gate_blocks_when_task_ledger_still_open(tmp_path: Path, monkeypatch) -> None:
    feature_dir = tmp_path / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("## implement\n- [X] T046 gate task\n", encoding="utf-8")

    def fake_run(cmd, capture_output=False, text=False):  # noqa: ANN001
        command = tuple(str(part) for part in cmd)
        if any(part.endswith("task_ledger.py") for part in command) and "validate" in command:
            stdout = "Task ledger validation passed (2 events).\n- feature 023: closed=0 open=1 active=T046\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        raise AssertionError(f"unexpected subprocess invocation: {command}")

    monkeypatch.setattr(speckit_implement_gate.subprocess, "run", fake_run)

    args = argparse.Namespace(
        feature_dir=str(feature_dir),
        phase_name="implement",
        phase_type="polish",
        layer1="pass",
        layer2="pass",
        layer3="na",
        json=True,
    )

    exit_code, payload = speckit_implement_gate._phase_gate(args)
    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["reasons"] == ["task_ledger_open_tasks"]
    assert payload["implementation_completed_state"] == "blocked_task_ledger"
