"""Unit tests for the edit-code deterministic workflow helper."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict


class _RunCall(TypedDict):
    cmd: list[str]
    input: str | None


def _load_module(module_name: str, script_name: str):
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


edit_code = _load_module("edit_code", "edit_code.py")


def _completed(returncode: int) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr="")


def test_validate_runs_pytest_guard_ruff_and_pyright(monkeypatch) -> None:
    calls: list[_RunCall] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        return _completed(0)

    monkeypatch.setattr(edit_code.subprocess, "run", fake_run)

    exit_code = edit_code.main(
        [
            "validate",
            "--paths",
            "scripts/read_code.py",
            "AGENTS.md",
            "--tests",
            "tests/unit/test_read_code_index_refresh.py",
        ]
    )

    assert exit_code == 0
    assert calls[0]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/pytest_guard.py",
        "run",
        "--",
        "-q",
        "--maxfail=1",
        "--tb=short",
        "tests/unit/test_read_code_index_refresh.py",
    ]
    assert calls[1]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "ruff",
        "check",
        "scripts/read_code.py",
    ]
    assert calls[2]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "pyright",
        "scripts/read_code.py",
    ]


def test_refresh_routes_through_hook_refresh_indexes(monkeypatch) -> None:
    calls: list[_RunCall] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        return _completed(0)

    monkeypatch.setattr(edit_code.subprocess, "run", fake_run)

    exit_code = edit_code.main(
        [
            "refresh",
            "--paths",
            "scripts/read_code.py",
            "AGENTS.md",
        ]
    )

    assert exit_code == 0
    assert calls[0]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/hook_refresh_indexes.py",
    ]
    payload = json.loads(str(calls[0]["input"]))
    assert payload == {"tool_input": {"paths": ["scripts/read_code.py", "AGENTS.md"]}}


def test_sync_runs_validate_refresh_and_git_without_push_when_disabled(monkeypatch) -> None:
    calls: list[_RunCall] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        return _completed(0)

    monkeypatch.setattr(edit_code.subprocess, "run", fake_run)

    exit_code = edit_code.main(
        [
            "sync",
            "--paths",
            "scripts/read_code.py",
            "--tests",
            "tests/unit/test_read_code_index_refresh.py",
            "--commit-message",
            "test commit",
            "--no-push",
            "--skip-ruff",
            "--skip-pyright",
        ]
    )

    assert exit_code == 0
    assert calls[0]["cmd"][:7] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/pytest_guard.py",
        "run",
        "--",
    ]
    assert calls[1]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/hook_refresh_indexes.py",
    ]
    assert calls[2]["cmd"] == ["git", "add", "scripts/read_code.py"]
    assert calls[3]["cmd"] == ["git", "commit", "-m", "test commit"]
    assert len(calls) == 4


def test_paths_outside_repo_are_rejected(tmp_path: Path, capsys) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("print('x')\n", encoding="utf-8")

    exit_code = edit_code.main(
        [
            "refresh",
            "--paths",
            str(outside),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "outside repo root" in captured.err
