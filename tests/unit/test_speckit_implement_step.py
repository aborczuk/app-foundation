"""Unit tests for scripts/speckit_implement_step.py."""

from __future__ import annotations

import importlib.util
import json
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


speckit_implement_step = _load_script_module(
    "speckit_implement_step",
    "speckit_implement_step.py",
)


def _prepare_feature(repo_root: Path) -> Path:
    """Create a minimal feature directory for deterministic implement step tests."""
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True, exist_ok=True)
    return feature_dir


def test_main_blocks_when_feature_not_found(tmp_path: Path, capsys) -> None:
    exit_code = speckit_implement_step.main(
        [
            "--repo-root",
            str(tmp_path),
            "--feature-id",
            "023",
            "--correlation-id",
            "run-test:speckit.implement",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    assert payload["gate"] == "implement_execution"
    assert payload["reasons"] == ["feature_not_found"]
    assert isinstance(payload["debug_path"], str) and payload["debug_path"]
    assert Path(payload["debug_path"]).exists()


def test_main_passes_with_gate_and_phase_success(tmp_path: Path, monkeypatch, capsys) -> None:
    _prepare_feature(tmp_path)

    def _fake_run_command(command, *, cwd, timeout_seconds, input_payload=None):  # noqa: ANN001
        command_text = " ".join(str(part) for part in command)
        if "speckit_gate_status.py" in command_text:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps({"ok": True}),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if "speckit_implement_gate.py" in command_text:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps({"ok": True, "reasons": []}),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        raise AssertionError(f"unexpected command: {command_text}")

    monkeypatch.setattr(speckit_implement_step, "_run_command", _fake_run_command)

    exit_code = speckit_implement_step.main(
        [
            "--repo-root",
            str(tmp_path),
            "--feature-id",
            "023",
            "--correlation-id",
            "run-test:speckit.implement",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["next_phase"] == "closed"
    assert isinstance(payload["debug_path"], str) and payload["debug_path"]

    debug_payload = json.loads(Path(payload["debug_path"]).read_text(encoding="utf-8"))
    stage_names = [stage["name"] for stage in debug_payload["stages"]]
    assert stage_names == ["resolve_feature_dir", "gate_status", "llm_handoff", "phase_gate"]
    statuses = {stage["name"]: stage["status"] for stage in debug_payload["stages"]}
    assert statuses["gate_status"] == "pass"
    assert statuses["llm_handoff"] == "skipped"
    assert statuses["phase_gate"] == "pass"


def test_main_blocks_when_handoff_required_but_runner_missing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _prepare_feature(tmp_path)

    def _fake_run_command(command, *, cwd, timeout_seconds, input_payload=None):  # noqa: ANN001
        command_text = " ".join(str(part) for part in command)
        if "speckit_gate_status.py" in command_text:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=json.dumps({"ok": True}),
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        raise AssertionError(f"unexpected command: {command_text}")

    monkeypatch.setattr(speckit_implement_step, "_run_command", _fake_run_command)

    exit_code = speckit_implement_step.main(
        [
            "--repo-root",
            str(tmp_path),
            "--feature-id",
            "023",
            "--correlation-id",
            "run-test:speckit.implement",
            "--require-handoff",
        ]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    assert payload["gate"] == "implement_execution"
    assert payload["reasons"] == ["llm_runner_not_configured"]
    assert Path(payload["debug_path"]).exists()
