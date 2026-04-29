"""Unit tests for scripts/speckit_implement_step.py."""

from __future__ import annotations

import importlib.util
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


speckit_implement_step = _load_script_module("speckit_implement_step", "speckit_implement_step.py")


def test_ensure_implement_branch_creates_branch_from_main(monkeypatch, tmp_path: Path) -> None:
    """Implement should create the feature branch from local main when needed."""
    repo_root = tmp_path
    feature_dir = repo_root / "specs" / "023-demo-branch"
    feature_dir.mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_run_command(command, *, cwd, timeout_seconds, input_payload=None):
        del cwd, input_payload
        calls.append([str(part) for part in command])
        if command == ["git", "branch", "--show-current"]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout="main\n",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if command == ["git", "branch", "--list", feature_dir.name]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout="",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if command == ["git", "switch", "-c", feature_dir.name]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout=f"Switched to a new branch '{feature_dir.name}'\n",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(speckit_implement_step, "_run_command", fake_run_command)

    details = speckit_implement_step._ensure_implement_branch(repo_root, feature_dir, timeout_seconds=30)

    assert details["branch_name"] == feature_dir.name
    assert details["status"] == "created"
    assert calls == [
        ["git", "branch", "--show-current"],
        ["git", "branch", "--list", feature_dir.name],
        ["git", "switch", "-c", feature_dir.name],
    ]


def test_ensure_implement_branch_requires_main(monkeypatch, tmp_path: Path) -> None:
    """Implement should refuse to create a new branch off a non-main checkout."""
    repo_root = tmp_path
    feature_dir = repo_root / "specs" / "023-demo-branch"
    feature_dir.mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_run_command(command, *, cwd, timeout_seconds, input_payload=None):
        del cwd, input_payload
        calls.append([str(part) for part in command])
        if command == ["git", "branch", "--show-current"]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout="scratch\n",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        if command == ["git", "branch", "--list", feature_dir.name]:
            return speckit_implement_step.CommandResult(
                exit_code=0,
                stdout="",
                stderr="",
                timed_out=False,
                command=[str(part) for part in command],
                timeout_seconds=timeout_seconds,
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(speckit_implement_step, "_run_command", fake_run_command)

    with pytest.raises(ValueError, match="implement_branch_requires_main"):
        speckit_implement_step._ensure_implement_branch(repo_root, feature_dir, timeout_seconds=30)

    assert calls == [
        ["git", "branch", "--show-current"],
        ["git", "branch", "--list", feature_dir.name],
    ]
