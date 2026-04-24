"""Unit tests for the pyright guard helper."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


def _load_module(module_name: str, script_name: str):
    """Load a script from scripts/ as an importable test module."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec for {script_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pyright_guard = _load_module("pyright_guard", "pyright_guard.py")


def _completed(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a synthetic subprocess completion result."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_main_invokes_pyright_for_valid_repo_paths(monkeypatch, capsys) -> None:
    """Run pyright for valid Python targets and preserve success stdout."""
    seen_commands: list[list[str]] = []
    seen_envs: list[dict[str, str]] = []

    def fake_run(cmd, **kwargs):
        seen_commands.append(list(cmd))
        seen_envs.append(kwargs["env"])
        return _completed(0, stdout="Success: no issues found in 1 source file\n")

    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.setattr(pyright_guard.subprocess, "run", fake_run)

    exit_code = pyright_guard.main(["scripts/edit_code.py"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert seen_commands == [["uv", "run", "--no-sync", "pyright", "scripts/edit_code.py"]]
    assert seen_envs
    assert seen_envs[0]["UV_CACHE_DIR"] == str(Path(__file__).resolve().parents[2] / ".codegraphcontext" / ".uv-cache")
    assert "Success: no issues found in 1 source file" in captured.out


def test_main_rejects_invalid_inputs_without_running_pyright(monkeypatch, capsys) -> None:
    """Fail early when non-Python or missing inputs are provided."""
    run_invoked = {"called": False}

    def fake_run(cmd, **kwargs):
        run_invoked["called"] = True
        return _completed(0)

    monkeypatch.setattr(pyright_guard.subprocess, "run", fake_run)

    exit_code = pyright_guard.main(["README.md", "scripts/does_not_exist.py"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert run_invoked["called"] is False
    assert "pyright_guard rejected one or more inputs" in captured.err
    assert "README.md: unsupported suffix .md; expected .py or .pyi" in captured.err
    assert "scripts/does_not_exist.py: path does not exist" in captured.err


def test_main_truncates_large_pyright_failure_output(monkeypatch, capsys) -> None:
    """Cap failing pyright output and emit a deterministic truncation notice."""
    failure_lines = "\n".join(f"line {index}" for index in range(1, 7))

    def fake_run(cmd, **kwargs):
        return _completed(1, stdout=failure_lines)

    monkeypatch.setattr(pyright_guard.subprocess, "run", fake_run)
    monkeypatch.setenv("PYRIGHT_GUARD_MAX_OUTPUT_LINES", "3")

    exit_code = pyright_guard.main(["scripts/edit_code.py"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "line 1" in captured.err
    assert "line 3" in captured.err
    assert "line 4" not in captured.err
    assert "output truncated by pyright_guard" in captured.err
