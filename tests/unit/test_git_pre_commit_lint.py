"""Unit tests for the Git pre-commit lint wrapper."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts import git_pre_commit_lint as hook


def _completed(code: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a subprocess result for pre-commit hook tests."""
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr=stderr)


def test_staged_paths_resolve_repo_relative_entries(monkeypatch, tmp_path: Path) -> None:
    """Staged git paths should resolve under the repo root."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    target = repo_root / "sample.py"
    target.write_text("print('ok')\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("print('nope')\n", encoding="utf-8")

    monkeypatch.setattr(hook, "REPO_ROOT", repo_root)

    def fake_run(command, **kwargs):
        return _completed(0, stdout="sample.py\n../outside.py\n")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook._staged_paths() == [target.resolve()]


def test_run_pre_commit_lint_skips_when_no_staged_python(monkeypatch) -> None:
    """No staged Python files should skip lint entirely."""
    commands: list[list[str]] = []

    monkeypatch.setattr(hook, "_staged_paths", lambda: [])

    def fake_run(command, **kwargs):
        commands.append(list(command))
        return _completed(0)

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.run_pre_commit_lint() == 0
    assert commands == []


def test_run_pre_commit_lint_executes_ruff_guard(monkeypatch, tmp_path: Path) -> None:
    """Staged Python files should run through the guarded Ruff wrapper."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    target = repo_root / "sample.py"
    target.write_text("def sample() -> str:\n    return 'ok'\n", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(hook, "REPO_ROOT", repo_root)
    monkeypatch.setattr(hook, "_staged_paths", lambda: [target])

    def fake_run(command, **kwargs):
        commands.append(list(command))
        return _completed(0)

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.run_pre_commit_lint() == 0
    assert commands == [[sys.executable, str(repo_root / "scripts" / "ruff_guard.py"), str(target)]]


def test_run_pre_commit_lint_returns_nonzero_on_lint_failure(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """Lint failures should stop the commit and emit a compact summary."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    target = repo_root / "sample.py"
    target.write_text("def sample() -> str:\n    return 'ok'\n", encoding="utf-8")

    monkeypatch.setattr(hook, "REPO_ROOT", repo_root)
    monkeypatch.setattr(hook, "_staged_paths", lambda: [target])
    monkeypatch.setattr(hook.subprocess, "run", lambda command, **kwargs: _completed(1))

    assert hook.run_pre_commit_lint() == 1
    assert "[pre-commit-lint] lint failed" in capsys.readouterr().err
