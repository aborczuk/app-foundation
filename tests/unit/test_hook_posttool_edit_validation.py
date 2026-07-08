"""Unit tests for the PostToolUse edit validation and refresh hook."""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

from scripts import hook_posttool_edit_validation as hook


def _completed(code: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    """Build a subprocess result for hook command tests."""
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=stdout, stderr=stderr)


def test_run_posttool_request_validates_python_then_refreshes(monkeypatch, tmp_path: Path) -> None:
    """Changed Python files should run all checks before refresh dispatch."""
    payload = {"tool_input": {"file_path": str(tmp_path / "sample.py")}}
    target = tmp_path / "sample.py"
    target.write_text("def sample() -> str:\n    return 'ok'\n", encoding="utf-8")
    commands: list[list[str]] = []
    refreshed_payloads: list[dict] = []

    monkeypatch.setattr(hook.hook_refresh_indexes, "_collect_changed_paths", lambda payload: [target])
    monkeypatch.setattr(
        hook.hook_refresh_indexes,
        "run_refresh_request",
        lambda payload: refreshed_payloads.append(payload) or [],
    )

    def fake_run(command, **kwargs):
        commands.append(list(command))
        return _completed(0)

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.run_posttool_request(payload) == []
    assert commands == [
        [sys.executable, "scripts/ruff_guard.py", str(target)],
        [sys.executable, "scripts/pyright_guard.py", str(target)],
        [sys.executable, "scripts/validate_python_docstrings.py", str(target)],
    ]
    assert refreshed_payloads == [payload]


def test_run_posttool_request_skips_python_checks_for_non_python_files(monkeypatch, tmp_path: Path) -> None:
    """Non-Python edits should bypass lint and type checks but still refresh."""
    payload = {"tool_input": {"file_path": str(tmp_path / "notes.md")}}
    target = tmp_path / "notes.md"
    target.write_text("# Notes\n", encoding="utf-8")
    commands: list[list[str]] = []

    monkeypatch.setattr(hook.hook_refresh_indexes, "_collect_changed_paths", lambda payload: [target])
    monkeypatch.setattr(hook.hook_refresh_indexes, "run_refresh_request", lambda payload: [])

    def fake_run(command, **kwargs):
        commands.append(list(command))
        return _completed(0)

    monkeypatch.setattr(hook.subprocess, "run", fake_run)

    assert hook.run_posttool_request(payload) == []
    assert commands == []


def test_run_posttool_request_stops_on_validation_failure(monkeypatch, tmp_path: Path) -> None:
    """Refresh should not run when any required validation step fails."""
    payload = {"tool_input": {"file_path": str(tmp_path / "sample.py")}}
    target = tmp_path / "sample.py"
    target.write_text("def sample() -> str:\n    return 'ok'\n", encoding="utf-8")
    refreshed = False

    monkeypatch.setattr(hook.hook_refresh_indexes, "_collect_changed_paths", lambda payload: [target])

    def fake_refresh(payload):
        nonlocal refreshed
        refreshed = True
        return []

    monkeypatch.setattr(hook.hook_refresh_indexes, "run_refresh_request", fake_refresh)

    results = iter(
        [
            _completed(1, stderr="ruff failed"),
            _completed(0),
            _completed(0),
        ]
    )

    monkeypatch.setattr(hook.subprocess, "run", lambda command, **kwargs: next(results))

    failures = hook.run_posttool_request(payload)
    assert failures == ["ruff check failed: ruff failed"]
    assert refreshed is False


def test_main_emits_failures_and_exits_non_zero(monkeypatch, capsys) -> None:
    """CLI mode should surface hook failures on stderr."""
    monkeypatch.setattr(hook, "run_posttool_request", lambda payload: ["ruff check failed: bad import"])
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO('{"tool_input":{"file_path":"scripts/sample.py"}}'))

    assert hook.main() == 1
    captured = capsys.readouterr()
    assert "ERROR: ruff check failed: bad import" in captured.err


def test_settings_route_edit_hooks_through_unified_script() -> None:
    """Codex settings should use the unified post-edit validation hook."""
    settings = Path(".claude/settings.json").read_text(encoding="utf-8")

    assert '"command": "python3 scripts/hook_posttool_edit_validation.py"' in settings
    assert "Running post-edit validation and scoped refresh..." in settings


def test_repo_local_codex_hooks_register_guard_entrypoints() -> None:
    """Repo-local Codex hooks should own session, pre-tool, and post-tool registration."""
    hooks = Path(".codex/hooks.json").read_text(encoding="utf-8")

    assert '"SessionStart"' in hooks
    assert '"matcher": "startup|resume"' in hooks
    assert '"PreToolUse"' in hooks
    assert '"matcher": "Bash"' in hooks
    assert '"command": "python3 /Users/andreborczuk/app-foundation/scripts/hook_pretool_dispatch.py"' in hooks
    assert '"PostToolUse"' in hooks
    assert '"matcher": "Edit|Write"' in hooks
    assert '"command": "python3 /Users/andreborczuk/app-foundation/scripts/hook_posttool_edit_validation.py"' in hooks
