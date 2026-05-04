"""Unit tests for the github guard helper."""

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


github_guard = _load_module("github_guard", "github_guard.py")


def _completed(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a synthetic subprocess completion result."""
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_invokes_gh_and_writes_full_log(monkeypatch, tmp_path, capsys) -> None:
    """Run gh with the forwarded command and persist the complete output."""
    seen_commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        """Capture the command and return a successful synthetic result."""
        seen_commands.append(list(cmd))
        return _completed(0, stdout="line 1\nline 2\n", stderr="")

    monkeypatch.setattr(github_guard.subprocess, "run", fake_run)

    exit_code = github_guard.main(
        [
            "run",
            "--log-dir",
            str(tmp_path),
            "--run-id",
            "abc123",
            "--",
            "gh",
            "run",
            "view",
            "42",
            "--log-failed",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert seen_commands == [["gh", "run", "view", "42", "--log-failed"]]
    assert "github_guard: exit_code=0" in captured.out
    assert "summary: line 2" in captured.out

    log_file = next(tmp_path.glob("*.log"))
    assert log_file.read_text(encoding="utf-8") == "line 1\nline 2\n"
    assert "log_file:" in captured.out


def test_run_prints_first_failure_block_on_failure(monkeypatch, tmp_path, capsys) -> None:
    """Surface a compact failure block while still writing the full gh log."""

    def fake_run(cmd, **kwargs):
        """Return a synthetic failing gh result with a compact error excerpt."""
        return _completed(1, stdout="step ok\nError: boom\nmore details\n\ntrailing\n", stderr="")

    monkeypatch.setattr(github_guard.subprocess, "run", fake_run)

    exit_code = github_guard.main(
        [
            "run",
            "--log-dir",
            str(tmp_path),
            "--",
            "gh",
            "run",
            "view",
            "42",
            "--log-failed",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "--- first_failure ---" in captured.out
    assert "Error: boom" in captured.out
    assert "more details" in captured.out


def test_show_returns_full_log_when_requested(tmp_path, capsys) -> None:
    """Replay a stored gh log in full when requested."""
    log_file = tmp_path / "github-20260504T010203Z.log"
    log_file.write_text("summary line\nError: boom\n", encoding="utf-8")

    exit_code = github_guard.main(["show", "--log", str(log_file), "--full"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "summary line\nError: boom\n"


def test_show_returns_compact_log_summary(tmp_path, capsys) -> None:
    """Replay a stored gh log in compact form by default."""
    log_file = tmp_path / "github-20260504T010203Z.log"
    log_file.write_text("summary line\nError: boom\nmore details\n", encoding="utf-8")

    exit_code = github_guard.main(["show", "--log", str(log_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "summary: more details" in captured.out
    assert "--- first_failure ---" in captured.out
    assert "Error: boom" in captured.out
