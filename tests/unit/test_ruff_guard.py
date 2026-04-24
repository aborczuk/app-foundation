"""Unit tests for deterministic ruff_guard behavior."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_module(module_name: str, script_name: str):
    """Load a helper script module from the scripts directory for unit tests."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module spec for {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ruff_guard = _load_module("ruff_guard_tests", "ruff_guard.py")


def _completed(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a completed-process payload for subprocess monkeypatching."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_main_rejects_non_python_paths(tmp_path: Path, capsys) -> None:
    """ruff_guard should fail fast when non-python file paths are provided."""
    shell_script = tmp_path / "script.sh"
    shell_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    rc = ruff_guard.main([str(shell_script)])
    stderr = capsys.readouterr().err

    assert rc == 2
    assert "unsupported suffix" in stderr


def test_main_runs_ruff_for_python_paths(monkeypatch, tmp_path: Path) -> None:
    """ruff_guard should invoke ruff for valid python paths only."""
    target = tmp_path / "sample.py"
    target.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")
    calls: list[list[str]] = []
    seen_envs: list[dict[str, str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        seen_envs.append(_kwargs["env"])
        return _completed(0)

    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.setattr(ruff_guard.subprocess, "run", fake_run)
    rc = ruff_guard.main([str(target)])

    assert rc == 0
    assert calls == [["uv", "run", "--no-sync", "ruff", "check", str(target)]]
    assert seen_envs
    assert seen_envs[0]["UV_CACHE_DIR"] == str(Path(__file__).resolve().parents[2] / ".codegraphcontext" / ".uv-cache")


def test_main_truncates_long_failure_output(monkeypatch, tmp_path: Path, capsys) -> None:
    """ruff_guard should truncate oversized ruff stderr to the configured cap."""
    target = tmp_path / "sample.py"
    target.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")
    long_output = "\n".join(f"line {idx}" for idx in range(1, 11))

    monkeypatch.setenv(ruff_guard.MAX_OUTPUT_LINES_ENV, "4")
    monkeypatch.setattr(
        ruff_guard.subprocess,
        "run",
        lambda *_args, **_kwargs: _completed(1, stderr=long_output),
    )

    rc = ruff_guard.main([str(target)])
    stderr = capsys.readouterr().err

    assert rc == 1
    assert "line 1" in stderr
    assert "line 4" in stderr
    assert "line 5" not in stderr
    assert "output truncated by ruff_guard" in stderr
