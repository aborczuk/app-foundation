"""Unit tests for pytest_guard wrapper behavior."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_module():
    """Load the pytest_guard script as an importable module."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "pytest_guard.py"
    spec = importlib.util.spec_from_file_location("pytest_guard", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_pytest_command_strips_override_flags(monkeypatch) -> None:
    guard = _load_module()
    monkeypatch.setattr(guard.shutil, "which", lambda name: "/usr/bin/uv")

    command = guard._build_pytest_command(
        ["--", "-vv", "--tb=long", "--maxfail=5", "tests/unit/test_hook_enforce_code_reads.py"]
    )

    assert command[:4] == ["uv", "run", "--no-sync", "pytest"]
    assert "-q" in command
    assert "--tb=short" in command
    assert "--maxfail=1" in command
    assert "--tb=long" not in command
    assert "--maxfail=5" not in command
    assert "-vv" not in command


def test_run_writes_full_log_and_prints_first_failure(monkeypatch, tmp_path: Path, capsys) -> None:
    guard = _load_module()
    failure_output = "\n".join(
        [
            "============================= test session starts =============================",
            "FAILURES",
            "________________________ test_first ________________________",
            "E   AssertionError: boom",
            "________________________ test_second ________________________",
            "E   AssertionError: second",
            "=========================== short test summary info ============================",
            "FAILED tests/unit/test_sample.py::test_first - AssertionError: boom",
            "============================== 1 failed in 0.10s ==============================",
        ]
    )

    monkeypatch.setattr(guard, "_build_pytest_command", lambda args: ["pytest", "dummy"])
    monkeypatch.setattr(
        guard.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=["pytest"], returncode=1, stdout=failure_output, stderr=""),
    )

    exit_code = guard.main(
        [
            "run",
            "--log-dir",
            str(tmp_path),
            "--run-id",
            "abc",
            "--",
            "tests/unit/test_sample.py",
        ]
    )
    stdout = capsys.readouterr().out

    assert exit_code == 1
    logs = sorted(tmp_path.glob("*.log"))
    assert len(logs) == 1
    assert logs[0].read_text(encoding="utf-8") == failure_output
    assert "pytest_guard: exit_code=1" in stdout
    assert "summary:" in stdout
    assert "--- first_failure ---" in stdout
    assert "test_first" in stdout
    assert "test_second" not in stdout


def test_show_latest_prints_full_log(tmp_path: Path, capsys) -> None:
    guard = _load_module()
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pytest-20260101T000000Z-sample.log"
    log_file.write_text("full output line\n", encoding="utf-8")

    exit_code = guard.main(["show", "--log-dir", str(log_dir), "--latest"])
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert stdout == "full output line\n"
