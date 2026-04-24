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


def _completed(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


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
            "--all-paths",
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
        "python",
        "scripts/ruff_guard.py",
        "scripts/read_code.py",
    ]
    assert calls[2]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/pyright_guard.py",
        "scripts/read_code.py",
    ]


def test_refresh_routes_through_hook_refresh_indexes(monkeypatch) -> None:
    calls: list[_RunCall] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return _completed(0, stdout=" M scripts/read_code.py\n")
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
        "git",
        "status",
        "--porcelain",
        "--untracked-files=normal",
        "--",
        "scripts/read_code.py",
        "AGENTS.md",
    ]
    assert calls[1]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/hook_refresh_indexes.py",
    ]
    payload = json.loads(str(calls[1]["input"]))
    assert payload == {"tool_input": {"paths": ["scripts/read_code.py", "AGENTS.md"]}}


def test_sync_runs_validate_refresh_and_git_without_push_when_disabled(monkeypatch) -> None:
    calls: list[_RunCall] = []

    status_calls = {"count": 0}

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        if cmd[:3] == ["git", "status", "--porcelain"]:
            status_calls["count"] += 1
            return _completed(0, stdout=" M scripts/read_code.py\n")
        if cmd[:3] == ["git", "diff", "--cached"]:
            return _completed(0, stdout="scripts/read_code.py\n")
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
    assert calls[0]["cmd"] == [
        "git",
        "status",
        "--porcelain",
        "--untracked-files=normal",
    ]
    assert calls[1]["cmd"][:7] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/pytest_guard.py",
        "run",
        "--",
    ]
    assert calls[2]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/hook_refresh_indexes.py",
    ]
    sync_payload = json.loads(str(calls[2]["input"]))
    assert sync_payload == {"tool_input": {"paths": ["scripts/read_code.py"]}}
    assert calls[3]["cmd"] == ["git", "add", "scripts/read_code.py"]
    assert calls[4]["cmd"] == [
        "git",
        "diff",
        "--cached",
        "--name-only",
        "--",
        "scripts/read_code.py",
    ]
    assert calls[5]["cmd"] == ["git", "commit", "-m", "test commit"]
    assert len(calls) == 6
    assert status_calls["count"] == 1


def test_refresh_skips_when_paths_are_clean(monkeypatch, capsys) -> None:
    calls: list[_RunCall] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return _completed(0, stdout="")
        return _completed(0)

    monkeypatch.setattr(edit_code.subprocess, "run", fake_run)

    exit_code = edit_code.main(["refresh", "--paths", "scripts/read_code.py"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "refresh_indexes skipped" in captured.out
    assert calls == [
        {
            "cmd": [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=normal",
                "--",
                "scripts/read_code.py",
            ],
            "input": None,
        }
    ]


def test_sync_skips_when_paths_are_clean(monkeypatch, capsys) -> None:
    calls: list[_RunCall] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return _completed(0, stdout="")
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
            "noop",
            "--no-push",
            "--skip-ruff",
            "--skip-pyright",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "sync skipped: nothing changed in requested paths" in captured.out
    assert calls[0]["cmd"] == [
        "git",
        "status",
        "--porcelain",
        "--untracked-files=normal",
    ]
    assert len(calls) == 1


def test_sync_retries_git_add_on_index_lock(monkeypatch) -> None:
    calls: list[_RunCall] = []
    add_attempts = {"count": 0}

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return _completed(0, stdout=" M scripts/read_code.py\n")
        if cmd[:2] == ["git", "add"]:
            add_attempts["count"] += 1
            if add_attempts["count"] == 1:
                return _completed(128, stderr="fatal: Unable to create '.git/index.lock': Operation not permitted")
            return _completed(0)
        if cmd[:3] == ["git", "diff", "--cached"]:
            return _completed(0, stdout="scripts/read_code.py\n")
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
            "retry add",
            "--no-push",
            "--skip-ruff",
            "--skip-pyright",
        ]
    )

    assert exit_code == 0
    assert add_attempts["count"] == 2


def test_validate_changed_only_limits_lint_and_type_checks(monkeypatch, capsys) -> None:
    calls: list[_RunCall] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return _completed(
                0,
                stdout=(
                    " M scripts/read_code.py\n"
                    " M AGENTS.md\n"
                ),
            )
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
            "--changed-only",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "2 changed path(s)" in captured.out
    assert calls[0]["cmd"] == [
        "git",
        "status",
        "--porcelain",
        "--untracked-files=normal",
        "--",
        "scripts/read_code.py",
        "AGENTS.md",
    ]
    assert calls[1]["cmd"] == [
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
    assert calls[2]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/ruff_guard.py",
        "scripts/read_code.py",
    ]
    assert calls[3]["cmd"] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/pyright_guard.py",
        "scripts/read_code.py",
    ]


def test_validate_skips_pytest_for_non_runtime_paths(monkeypatch, capsys) -> None:
    calls: list[_RunCall] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        return _completed(0)

    monkeypatch.setattr(edit_code.subprocess, "run", fake_run)

    exit_code = edit_code.main(
        [
            "validate",
            "--paths",
            "README.md",
            "constitution.md",
            "--tests",
            "tests/unit/test_read_code_index_refresh.py",
            "--all-paths",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "pytest_guard skipped" in captured.out
    assert calls == []


def test_sync_warns_for_unrelated_dirty_paths(monkeypatch, capsys) -> None:
    calls: list[_RunCall] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "input": kwargs.get("input")})
        if cmd[:3] == ["git", "status", "--porcelain"]:
            if "--" in cmd:
                return _completed(0, stdout=" M scripts/read_code.py\n")
            return _completed(0, stdout=" M scripts/read_code.py\n M README.md\n")
        if cmd[:3] == ["git", "diff", "--cached"]:
            return _completed(0, stdout="scripts/read_code.py\n")
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
            "warn unrelated",
            "--no-push",
            "--skip-ruff",
            "--skip-pyright",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "unrelated dirty paths detected outside requested scope" in captured.err
    assert "README.md" in captured.err


def test_run_command_defaults_repo_local_uv_cache(monkeypatch) -> None:
    seen_env: dict[str, str] = {}

    def fake_run(cmd, **kwargs):
        nonlocal seen_env
        env = kwargs.get("env")
        if isinstance(env, dict):
            seen_env = dict(env)
        return _completed(0)

    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.setattr(edit_code.subprocess, "run", fake_run)

    exit_code = edit_code._run_command(["uv", "run", "--no-sync", "python", "--version"], label="probe")

    assert exit_code == 0
    assert seen_env["UV_CACHE_DIR"] == str(edit_code.REPO_ROOT / ".codegraphcontext" / ".uv-cache")


def test_run_command_hides_full_command_by_default(monkeypatch, capsys) -> None:
    monkeypatch.delenv(edit_code.EDIT_CODE_VERBOSE_ENV, raising=False)
    monkeypatch.setattr(edit_code.subprocess, "run", lambda *args, **kwargs: _completed(0))

    exit_code = edit_code._run_command(["uv", "run", "--no-sync", "python", "--version"], label="probe")
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "[edit-code] probe" in captured.out
    assert "[edit-code] cmd:" not in captured.out


def test_run_command_shows_full_command_in_verbose_mode(monkeypatch, capsys) -> None:
    monkeypatch.setenv(edit_code.EDIT_CODE_VERBOSE_ENV, "1")
    monkeypatch.setattr(edit_code.subprocess, "run", lambda *args, **kwargs: _completed(0))

    exit_code = edit_code._run_command(["uv", "run", "--no-sync", "python", "--version"], label="probe")
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "[edit-code] cmd: uv run --no-sync python --version" in captured.out


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
